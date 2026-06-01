from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.common.io.encoding import decode_text, dump_json_file, load_json_file

from .s3_loader import S3Loader


class TextAnalysisMediaStoreMixin:
    def _initialize_media_store_state(self) -> None:
        self._preview_cache_dir = self.project_root / ".cache" / "text_analysis_preview_images"
        self._preview_cache_dir.mkdir(parents=True, exist_ok=True)
        self._json_cache_dir = self.project_root / ".cache" / "text_analysis_preview_json"
        self._json_cache_dir.mkdir(parents=True, exist_ok=True)
        self._preview_image_cache: Dict[str, str] = {}
        self._preview_json_cache: Dict[str, str] = {}
        self._json_payload_cache: Dict[str, Dict[str, Any]] = {}
        self._media_row_index: Dict[tuple[str, str, str], Dict[str, Any]] = {}

    def _set_current_s3_rows(self, rows: list[Dict[str, Any]]) -> None:
        normalized_rows = [dict(row) for row in rows]
        self.current_s3_rows = normalized_rows
        self._rebuild_media_row_index(normalized_rows)

    def _rebuild_media_row_index(self, rows: list[Dict[str, Any]]) -> None:
        index: Dict[tuple[str, str, str], Dict[str, Any]] = {}
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

    def _resolve_image_row(self, book_id: str, page_name: str) -> Optional[Dict[str, Any]]:
        image_row = self._resolve_media_row(book_id, page_name, {".png", ".jpg", ".jpeg"})
        if image_row is not None:
            return image_row

        page_number = self._extract_page_no(page_name)
        candidates = [
            row
            for row in self.current_s3_rows
            if str(row.get("book_id", "")).strip() == str(book_id).strip()
            and Path(str(row.get("page_no", ""))).suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
        if not candidates:
            return None

        number_matches = [
            dict(row)
            for row in candidates
            if self._extract_page_no(str(row.get("page_no", ""))) == page_number
        ]
        if number_matches:
            return number_matches[0]
        return dict(candidates[0])

    def _resolve_json_row(self, book_id: str, page_name: str) -> Optional[Dict[str, Any]]:
        return self._resolve_media_row(book_id, page_name, {".json"})

    def _resolve_media_row(
        self,
        book_id: str,
        page_name: str,
        extensions: set[str],
    ) -> Optional[Dict[str, Any]]:
        if not book_id or not page_name:
            return None
        stem = Path(str(page_name)).stem
        preferred_extensions = (".png", ".jpg", ".jpeg", ".json")
        for preferred_ext in preferred_extensions:
            if preferred_ext not in extensions:
                continue
            candidate = self._media_row_index.get((str(book_id).strip(), stem, preferred_ext))
            if isinstance(candidate, dict):
                return dict(candidate)
        return None

    def _load_page_json_payload(self, json_row: Dict[str, Any]) -> Dict[str, Any]:
        cache_key = self._json_cache_key(json_row)
        if cache_key and cache_key in self._json_payload_cache:
            return copy.deepcopy(self._json_payload_cache[cache_key])

        local_path = self._download_preview_json(json_row)
        if not local_path:
            return {}

        payload = load_json_file(local_path)
        if isinstance(payload, dict) and cache_key:
            self._json_payload_cache[cache_key] = payload
            return copy.deepcopy(payload)
        return payload if isinstance(payload, dict) else {}

    def _load_page_json_payload_fresh(
        self,
        json_row: Dict[str, Any],
        *,
        loader: Optional[S3Loader] = None,
    ) -> Dict[str, Any]:
        bucket = str(json_row.get("bucket", "")).strip()
        s3_key = str(json_row.get("s3_key", "")).strip()
        if not bucket or not s3_key:
            return {}

        active_loader = loader or S3Loader(self.config.get("aws", {}))
        response = active_loader.client.get_object(Bucket=bucket, Key=s3_key)
        body = response.get("Body")
        if body is None:
            return {}
        payload = json.loads(decode_text(body.read()))
        return payload if isinstance(payload, dict) else {}

    def _download_preview_json(
        self,
        json_row: Dict[str, Any],
        *,
        loader: Optional[S3Loader] = None,
    ) -> str:
        bucket = str(json_row.get("bucket", "")).strip()
        s3_key = str(json_row.get("s3_key", "")).strip()
        if not bucket or not s3_key:
            return ""

        cache_key = self._json_cache_key(json_row)
        cached_path = self._preview_json_cache.get(cache_key)
        if cached_path and Path(cached_path).exists():
            return cached_path

        local_path = self._json_cache_dir / f"{hashlib.md5(cache_key.encode('utf-8')).hexdigest()}.json"
        if local_path.exists():
            self._preview_json_cache[cache_key] = str(local_path)
            return str(local_path)

        active_loader = loader or S3Loader(self.config.get("aws", {}))
        response = active_loader.client.get_object(Bucket=bucket, Key=s3_key)
        body = response.get("Body")
        if body is None:
            return ""
        dump_json_file(local_path, json.loads(decode_text(body.read())))
        self._preview_json_cache[cache_key] = str(local_path)
        return str(local_path)

    def _json_cache_key(self, json_row: Dict[str, Any]) -> str:
        s3_key = str(json_row.get("s3_key", "")).strip()
        etag = str(json_row.get("etag", "")).strip()
        return f"{s3_key}|{etag}" if etag else s3_key

    def _find_json_row(self, book_id: str, page_name: str) -> Optional[Dict[str, Any]]:
        return self._resolve_json_row(book_id, page_name)

    def _download_preview_image(self, image_row: Dict[str, Any]) -> str:
        bucket = str(image_row.get("bucket", "")).strip()
        s3_key = str(image_row.get("s3_key", "")).strip()
        page_name = str(image_row.get("page_no", "")).strip()
        if not bucket or not s3_key:
            return ""

        cached_path = self._preview_image_cache.get(s3_key)
        if cached_path and Path(cached_path).exists():
            return cached_path

        suffix = Path(page_name).suffix.lower() or ".png"
        local_path = self._preview_cache_dir / f"{hashlib.md5(s3_key.encode('utf-8')).hexdigest()}{suffix}"
        if local_path.exists():
            self._preview_image_cache[s3_key] = str(local_path)
            return str(local_path)

        try:
            loader = S3Loader(self.config.get("aws", {}))
            loader.client.download_file(bucket, s3_key, str(local_path))
            self._preview_image_cache[s3_key] = str(local_path)
            return str(local_path)
        except Exception as exc:
            self._set_recent_log(f"미리보기 이미지 로드 실패: {exc}")
            return ""

    def _save_page_json_payload(
        self,
        json_row: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        loader: Optional[S3Loader] = None,
    ) -> None:
        self._write_page_json_payload_remote(json_row, payload, loader=loader)
        self._cache_page_json_payload(json_row, payload)

    def _write_page_json_payload_remote(
        self,
        json_row: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        loader: Optional[S3Loader] = None,
    ) -> None:
        bucket = str(json_row.get("bucket", "")).strip()
        s3_key = str(json_row.get("s3_key", "")).strip()
        if not bucket or not s3_key:
            return
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        active_loader = loader or S3Loader(self.config.get("aws", {}))
        active_loader.client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=body,
            ContentType="application/json; charset=utf-8",
        )

    def _cache_page_json_payload(
        self,
        json_row: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> None:
        cache_key = self._json_cache_key(json_row)
        if cache_key:
            local_path = self._json_cache_dir / f"{hashlib.md5(cache_key.encode('utf-8')).hexdigest()}.json"
            local_path.parent.mkdir(parents=True, exist_ok=True)
            dump_json_file(local_path, payload, ensure_ascii=False, indent=2)
            self._preview_json_cache[cache_key] = str(local_path)
            self._json_payload_cache[cache_key] = copy.deepcopy(payload)
