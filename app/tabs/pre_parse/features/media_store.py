from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.common.io.encoding import decode_text, dump_json_file, load_json_file
from app.tabs.pre_parse.features.s3.s3_loader import S3Loader


class PreParseMediaStoreMixin:
    def _set_current_s3_pages(self, rows: List[dict]) -> None:
        normalized_rows = [dict(row) for row in rows]
        self.current_s3_pages = normalized_rows
        self._rebuild_media_row_index(normalized_rows)

    def _rebuild_media_row_index(self, rows: List[dict]) -> None:
        index: Dict[Tuple[str, str, str], dict] = {}
        for row in rows:
            book_id = str(row.get("book_id", "")).strip()
            page_name = str(row.get("page_no", "")).strip()
            if not book_id or not page_name:
                continue
            path = Path(page_name)
            stem = path.stem
            suffix = path.suffix.lower()
            if not stem or not suffix:
                continue
            index.setdefault((book_id, stem, suffix), dict(row))
        self._media_row_index = index

    def _resolve_image_row(self, book_id: str, page_token: str) -> Optional[dict]:
        return self._resolve_media_row(book_id, page_token, {".png", ".jpg", ".jpeg"})

    def _resolve_json_row(self, book_id: str, page_token: str) -> Optional[dict]:
        return self._resolve_media_row(book_id, page_token, {".json"})

    def _resolve_media_row(self, book_id: str, page_token: str, extensions: set[str]) -> Optional[dict]:
        if not book_id:
            return None
        stem = page_token.rsplit(".", 1)[0]
        preferred_extensions = (".png", ".jpg", ".jpeg", ".json")
        for preferred_ext in preferred_extensions:
            if preferred_ext not in extensions:
                continue
            candidate = self._media_row_index.get((str(book_id).strip(), stem, preferred_ext))
            if isinstance(candidate, dict):
                return dict(candidate)
        return None

    def _download_preview_image(self, image_row: dict) -> str:
        bucket = str(image_row.get("bucket", "")).strip()
        s3_key = str(image_row.get("s3_key", "")).strip()
        page_no = str(image_row.get("page_no", "")).strip()
        if not bucket or not s3_key:
            return ""

        cached = self._preview_image_cache.get(s3_key)
        if cached and Path(cached).exists():
            return cached

        suffix = Path(page_no).suffix.lower() or ".png"
        safe_name = hashlib.md5(s3_key.encode("utf-8")).hexdigest() + suffix
        local_path = self._preview_cache_dir / safe_name
        if local_path.exists():
            self._preview_image_cache[s3_key] = str(local_path)
            return str(local_path)

        try:
            loader = S3Loader(self.config.get("aws", {}))
            loader._client.download_file(bucket, s3_key, str(local_path))
            self._preview_image_cache[s3_key] = str(local_path)
            return str(local_path)
        except Exception as exc:
            self._set_recent_log(f"미리보기 이미지 로드 실패: {exc}")
            return ""

    def _download_preview_json(
        self,
        json_row: dict,
        *,
        force_refresh: bool = False,
        loader: Optional[S3Loader] = None,
    ) -> str:
        bucket = str(json_row.get("bucket", "")).strip()
        s3_key = str(json_row.get("s3_key", "")).strip()
        if not bucket or not s3_key:
            return ""

        etag = str(json_row.get("etag", "")).strip()
        cache_key = f"{s3_key}|{etag}"
        cached = self._preview_json_cache.get(cache_key)
        if (not force_refresh) and cached and Path(cached).exists():
            return cached

        local_path = self._local_json_cache_path(json_row)
        if (not force_refresh) and local_path.exists():
            self._preview_json_cache[cache_key] = str(local_path)
            return str(local_path)

        try:
            active_loader = loader if loader is not None else S3Loader(self.config.get("aws", {}))
            response = active_loader._client.get_object(Bucket=bucket, Key=s3_key)
            body = response.get("Body")
            if body is None:
                return ""
            payload = body.read()
            dump_json_file(local_path, json.loads(decode_text(payload)))
            self._preview_json_cache[cache_key] = str(local_path)
            return str(local_path)
        except Exception as exc:
            self._set_recent_log(f"미리보기 JSON 로드 실패: {exc}")
            if local_path.exists():
                self._preview_json_cache[cache_key] = str(local_path)
                return str(local_path)
            if cached and Path(cached).exists():
                return cached
            return ""

    def _local_json_cache_path(self, json_row: dict) -> Path:
        s3_key = str(json_row.get("s3_key", "")).strip()
        etag = str(json_row.get("etag", "")).strip()
        hash_seed = f"{s3_key}|{etag}" if etag else s3_key
        safe_name = hashlib.md5(hash_seed.encode("utf-8")).hexdigest() + ".json"
        return self._json_cache_dir / safe_name

    def _json_cache_key(self, json_row: dict) -> str:
        s3_key = str(json_row.get("s3_key", "")).strip()
        etag = str(json_row.get("etag", "")).strip()
        if not s3_key:
            return ""
        return f"{s3_key}|{etag}" if etag else s3_key

    def _snapshot_json_row_for_page(self, book_id: str, page_token: str) -> Optional[dict]:
        page_key = (str(book_id).strip(), str(page_token).strip())
        json_row = self._pre_parse_snapshot_json_rows.get(page_key)
        if isinstance(json_row, dict):
            return json_row
        return None

    def _snapshot_cache_key_for_page(self, book_id: str, page_token: str) -> str:
        page_key = (str(book_id).strip(), str(page_token).strip())
        return str(self._pre_parse_snapshot_page_cache_keys.get(page_key, "") or "")

    def _load_snapshot_page_json_payload(self, book_id: str, page_token: str) -> Dict:
        cache_key = self._snapshot_cache_key_for_page(book_id, page_token)
        if not cache_key:
            return {}
        payload = self._pre_parse_snapshot_payloads.get(cache_key)
        if not isinstance(payload, dict):
            json_row = self._snapshot_json_row_for_page(book_id, page_token)
            payload = self._load_snapshot_payload_from_cache(cache_key, json_row=json_row)
            if not isinstance(payload, dict):
                return {}
        return payload

    def _load_snapshot_payload_from_cache(
        self,
        cache_key: str,
        *,
        json_row: Optional[dict] = None,
    ) -> Dict:
        cache_key = str(cache_key or "").strip()
        if not cache_key:
            return {}

        cached_payload = self._pre_parse_snapshot_payloads.get(cache_key)
        if isinstance(cached_payload, dict):
            return cached_payload

        cached_payload = self._json_payload_cache.get(cache_key)
        if isinstance(cached_payload, dict):
            self._pre_parse_snapshot_payloads[cache_key] = cached_payload
            return cached_payload

        json_path = str(self._preview_json_cache.get(cache_key, "")).strip()
        if (not json_path) and isinstance(json_row, dict):
            local_path = self._local_json_cache_path(json_row)
            if local_path.exists():
                json_path = str(local_path)
        if not json_path or not Path(json_path).exists():
            return {}

        try:
            payload = load_json_file(json_path)
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}

        self._pre_parse_snapshot_payloads[cache_key] = payload
        self._json_payload_cache[cache_key] = payload
        self._preview_json_cache[cache_key] = json_path
        return payload

    def _json_rows_for_page_rows(self, page_rows: List[dict]) -> List[dict]:
        json_rows: List[dict] = []
        seen_keys: set[str] = set()
        for page in page_rows:
            page_key = str(page.get("page_no", ""))
            if ":" in page_key:
                book_id, page_token = page_key.split(":", 1)
            else:
                book_id = str(page.get("book_id", "")).strip()
                page_token = page_key
            json_row = self._resolve_json_row(book_id, page_token)
            if not json_row:
                continue
            cache_key = self._json_cache_key(json_row) or str(json_row.get("s3_key", "")).strip()
            if cache_key and cache_key in seen_keys:
                continue
            if cache_key:
                seen_keys.add(cache_key)
            json_rows.append(json_row)
        return json_rows

    def _split_issue_page(self, page_key: str) -> Tuple[str, str]:
        text = str(page_key or "").strip()
        if ":" in text:
            return text.split(":", 1)
        return "", text

    def _filter_issues_for_page(self, issues: List[dict], book_id: str, page_token: str) -> List[dict]:
        target_page_no = self._extract_page_no(page_token)
        page_bboxes = []
        for issue in issues:
            issue_book, issue_page = self._split_issue_page(issue.get("page_no", ""))
            if issue_book == book_id and self._extract_page_no(issue_page) == target_page_no:
                page_bboxes.append(dict(issue))
        return page_bboxes

    def _shape_value_from_flags(self, shape: dict) -> str:
        flags = shape.get("flags", {})
        if isinstance(flags, dict):
            for key in ("text", "value", "ocr"):
                value = flags.get(key, "")
                if value not in ("", None):
                    return str(value)
        return ""

    def _load_page_json_payload(
        self,
        book_id: str,
        page_token: str,
        *,
        force_refresh: bool = False,
        loader: Optional[S3Loader] = None,
    ) -> Dict:
        json_row = self._resolve_json_row(book_id, page_token)
        if not json_row:
            return {}
        return self._load_json_payload_from_row(
            json_row,
            force_refresh=force_refresh,
            loader=loader,
        )

    def _load_json_payload_from_row(
        self,
        json_row: dict,
        *,
        force_refresh: bool = False,
        loader: Optional[S3Loader] = None,
    ) -> Dict:
        cache_key = self._json_cache_key(json_row)
        if (not force_refresh) and cache_key:
            cached_payload = self._json_payload_cache.get(cache_key)
            if isinstance(cached_payload, dict):
                return cached_payload
        json_path = self._download_preview_json(
            json_row,
            force_refresh=force_refresh,
            loader=loader,
        )
        if not json_path:
            return {}
        try:
            payload = load_json_file(json_path)
            if isinstance(payload, dict):
                if cache_key:
                    self._json_payload_cache[cache_key] = payload
                return payload
        except Exception:
            return {}
        return {}

    def _load_page_json_payload_fresh(
        self,
        json_row: dict,
        *,
        loader: Optional[S3Loader] = None,
    ) -> Dict:
        bucket = str(json_row.get("bucket", "")).strip()
        s3_key = str(json_row.get("s3_key", "")).strip()
        if not bucket or not s3_key:
            return {}

        active_loader = loader or S3Loader(self.config.get("aws", {}))
        response = active_loader._client.get_object(Bucket=bucket, Key=s3_key)
        body = response.get("Body")
        if body is None:
            return {}
        payload = json.loads(decode_text(body.read()))
        return payload if isinstance(payload, dict) else {}

    def _save_page_json_payload(
        self,
        json_row: dict,
        payload: Dict,
        *,
        loader: Optional[S3Loader] = None,
    ) -> None:
        self._write_page_json_payload_remote(json_row, payload, loader=loader)
        self._cache_page_json_payload(json_row, payload)

    def _write_page_json_payload_remote(
        self,
        json_row: dict,
        payload: Dict,
        *,
        loader: Optional[S3Loader] = None,
    ) -> None:
        bucket = str(json_row.get("bucket", "")).strip()
        s3_key = str(json_row.get("s3_key", "")).strip()
        if not bucket or not s3_key:
            return
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        active_loader = loader or S3Loader(self.config.get("aws", {}))
        active_loader._client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=body,
            ContentType="application/json; charset=utf-8",
        )

    def _cache_page_json_payload(
        self,
        json_row: dict,
        payload: Dict,
    ) -> None:
        cache_key = self._json_cache_key(json_row)
        if cache_key:
            local_path = self._local_json_cache_path(json_row)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            dump_json_file(local_path, payload, ensure_ascii=False, indent=2)
            self._preview_json_cache[cache_key] = str(local_path)
            payload_copy = copy.deepcopy(payload)
            self._json_payload_cache[cache_key] = copy.deepcopy(payload_copy)
            self._pre_parse_snapshot_payloads[cache_key] = payload_copy

    def _load_shapes_from_json_row(self, json_row: Optional[dict]) -> List[dict]:
        if not json_row:
            return []
        payload = self._load_page_json_payload(
            str(json_row.get("book_id", "")),
            str(json_row.get("page_no", "")),
        )
        if not payload:
            return []
        shapes = payload.get("shapes", [])
        if not isinstance(shapes, list):
            return []
        return self._load_shapes_from_payload(payload)
