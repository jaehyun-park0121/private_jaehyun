from __future__ import annotations

import copy
import hashlib
import json
import threading
import traceback
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from app.common.io.encoding import decode_text, dump_json_file
from app.tabs.text_analysis.features.s3_loader import S3Loader
from app.tabs.text_analysis.tools.replace import compile_pattern, format_replace_row_label, normalize_compare_payload, replace_text


def _safe_int(value: Any, default: int = -1) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except Exception:
        return default


def _json_cache_key(json_row: Dict[str, Any]) -> str:
    s3_key = str(json_row.get("s3_key", "")).strip()
    etag = str(json_row.get("etag", "")).strip()
    return f"{s3_key}|{etag}" if etag else s3_key


def _local_json_cache_path(cache_dir: str, json_row: Dict[str, Any]) -> Path:
    cache_key = _json_cache_key(json_row)
    return Path(cache_dir) / f"{hashlib.md5(cache_key.encode('utf-8')).hexdigest()}.json"


def _load_payload_from_s3(aws_config: Dict[str, Any], json_row: Dict[str, Any]) -> Dict[str, Any]:
    bucket = str(json_row.get("bucket", "")).strip()
    s3_key = str(json_row.get("s3_key", "")).strip()
    if not bucket or not s3_key:
        return {}

    loader = S3Loader(dict(aws_config or {}))
    response = loader.client.get_object(Bucket=bucket, Key=s3_key)
    body = response.get("Body")
    if body is None:
        return {}
    payload = json.loads(decode_text(body.read()))
    return payload if isinstance(payload, dict) else {}


def _save_payload_to_s3_and_cache(
    aws_config: Dict[str, Any],
    cache_dir: str,
    json_row: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    bucket = str(json_row.get("bucket", "")).strip()
    s3_key = str(json_row.get("s3_key", "")).strip()
    if not bucket or not s3_key:
        raise ValueError("S3 경로가 없어 JSON을 저장할 수 없습니다.")

    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    loader = S3Loader(dict(aws_config or {}))
    loader.client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=body,
        ContentType="application/json; charset=utf-8",
    )

    local_path = _local_json_cache_path(cache_dir, json_row)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json_file(local_path, payload, ensure_ascii=False, indent=2)


def _display_spans_from_segments(segments: List[Dict[str, Any]]) -> List[List[Any]]:
    display_spans: List[List[Any]] = []
    offset = 0
    for segment in sorted(segments, key=lambda item: _safe_int(item.get("start", -1), -1)):
        start = _safe_int(segment.get("start", -1), -1)
        end = _safe_int(segment.get("end", -1), -1)
        replacement = str(segment.get("replacement", "") or "")
        if start < 0 or end <= start:
            continue
        display_start = start + offset
        display_end = display_start + len(replacement)
        if display_end > display_start:
            display_spans.append([display_start, display_end, replacement])
        offset += len(replacement) - (end - start)
    return display_spans


def _apply_nfkc_segments(text: str, segments: List[Dict[str, Any]]) -> tuple[str, List[str], List[List[Any]], int, str]:
    ordered: List[Dict[str, Any]] = []
    last_end = 0
    for segment in sorted(segments, key=lambda item: _safe_int(item.get("start", -1), -1)):
        start = _safe_int(segment.get("start", -1), -1)
        end = _safe_int(segment.get("end", -1), -1)
        expected = str(segment.get("original", "") or "")
        if start < 0 or end <= start or end > len(text):
            return text, [], [], 0, "NFKC 정규화 구간 범위가 올바르지 않습니다."
        if start < last_end:
            return text, [], [], 0, "NFKC 정규화 구간이 서로 겹칩니다."
        original = text[start:end]
        if expected and original != expected:
            return text, [], [], 0, "현재 S3 flags.text의 대상 구간이 조회 시점 값과 다릅니다."
        normalized = unicodedata.normalize("NFKC", original)
        if normalized != original:
            ordered.append({"start": start, "end": end, "original": original, "replacement": normalized})
        last_end = end

    if not ordered:
        return text, [], [], 0, ""

    parts: List[str] = []
    cursor = 0
    matched_values: List[str] = []
    for segment in ordered:
        start = int(segment["start"])
        end = int(segment["end"])
        parts.append(text[cursor:start])
        parts.append(str(segment["replacement"]))
        matched_values.append(str(segment["original"]))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), matched_values, _display_spans_from_segments(ordered), len(ordered), ""


class TextAnalysisReplaceWorker(QThread):
    finished_ok = pyqtSignal(object)
    cancelled = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)

    def __init__(
        self,
        *,
        aws_config: Dict[str, Any],
        cache_dir: str,
        page_tasks: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> None:
        super().__init__()
        self.aws_config = dict(aws_config or {})
        self.cache_dir = str(cache_dir or "")
        self.page_tasks = [copy.deepcopy(task) for task in page_tasks]
        self.context = copy.deepcopy(context or {})
        self._stop_requested = False
        self._stop_lock = threading.Lock()

    def request_stop(self) -> None:
        with self._stop_lock:
            self._stop_requested = True

    def _is_stop_requested(self) -> bool:
        with self._stop_lock:
            return self._stop_requested

    def run(self) -> None:
        try:
            bundle = self._run_replace_flow()
            if self._is_stop_requested():
                self.cancelled.emit(bundle)
                return
            self.finished_ok.emit(bundle)
        except Exception as exc:
            self.failed.emit("".join(traceback.format_exception(exc)))

    def _run_replace_flow(self) -> Dict[str, Any]:
        operation = str(self.context.get("operation", "replace") or "replace").strip()
        is_nfkc = operation == "nfkc"
        operation_label = "NFKC 정규화" if is_nfkc else "치환"
        source_text = str(self.context.get("source_text", "") or "")
        target_text = str(self.context.get("target_text", "") or "")
        use_regex = bool(self.context.get("use_regex", False))
        case_sensitive = bool(self.context.get("case_sensitive", False))
        replacement_uses_groups = bool(self.context.get("replacement_uses_groups", False))
        regex = compile_pattern(
            source_text,
            use_regex=use_regex,
            case_sensitive=case_sensitive,
        )

        snapshot_mismatch_pages: List[str] = []
        prepared_tasks: List[Dict[str, Any]] = []
        total_pages = len(self.page_tasks)
        for index, page_task in enumerate(self.page_tasks, start=1):
            if self._is_stop_requested():
                break
            self.progress.emit(f"{operation_label} 대상 확인", index, total_pages)

            json_row = dict(page_task.get("json_row", {}) or {})
            snapshot_payload = dict(page_task.get("snapshot_payload", {}) or {})
            latest_payload = _load_payload_from_s3(self.aws_config, json_row)
            if normalize_compare_payload(snapshot_payload) != normalize_compare_payload(latest_payload):
                page_label = str(page_task.get("page_label", "")).strip()
                if page_label:
                    snapshot_mismatch_pages.append(page_label)
                continue
            prepared_task = dict(page_task)
            prepared_task["latest_payload"] = latest_payload
            prepared_tasks.append(prepared_task)

        if snapshot_mismatch_pages or self._is_stop_requested():
            return {
                "snapshot_mismatch_pages": snapshot_mismatch_pages,
                "updated_pages": 0,
                "updated_labels": 0,
                "failed_rows": [],
                "applied_updates": [],
                "updated_payloads": {},
                "fatal_error": "",
            }

        failed_rows: List[str] = []
        applied_updates: List[Dict[str, Any]] = []
        updated_payloads: Dict[str, Dict[str, Any]] = {}
        updated_pages = 0
        updated_labels = 0
        fatal_error = ""

        total_prepared = len(prepared_tasks)
        for index, page_task in enumerate(prepared_tasks, start=1):
            if self._is_stop_requested():
                break
            self.progress.emit(f"{operation_label} 실행", index, total_prepared)

            json_row = dict(page_task.get("json_row", {}) or {})
            payload = copy.deepcopy(page_task.get("latest_payload", {}) or {})
            shapes = payload.get("shapes", [])
            if not isinstance(shapes, list):
                fatal_error = f"{operation_label} 중 S3 JSON shapes 구조를 읽을 수 없습니다."
                break

            page_changed = False
            page_updates: List[Dict[str, Any]] = []
            for row in list(page_task.get("rows", []) or []):
                shape_index = _safe_int(row.get("shape_index", -1), -1)
                if shape_index < 0 or shape_index >= len(shapes):
                    failed_rows.append(f"{format_replace_row_label(row)}: shape 인덱스를 찾을 수 없습니다.")
                    continue

                shape = shapes[shape_index]
                if not isinstance(shape, dict):
                    failed_rows.append(f"{format_replace_row_label(row)}: shape 구조가 올바르지 않습니다.")
                    continue

                flags = shape.get("flags")
                if not isinstance(flags, dict):
                    flags = {}
                    shape["flags"] = flags

                current_text = str(flags.get("text", "") or "")
                if current_text == "":
                    failed_rows.append(f"{format_replace_row_label(row)}: flags.text가 비어 있어 {operation_label}할 수 없습니다.")
                    continue

                changed_segment_count = 0
                display_spans: List[List[Any]] = []
                if is_nfkc:
                    replaced_text, matched_values, display_spans, changed_segment_count, segment_error = _apply_nfkc_segments(
                        current_text,
                        list(row.get("nfkc_segments", []) or []),
                    )
                    if segment_error:
                        failed_rows.append(f"{format_replace_row_label(row)}: {segment_error}")
                        continue
                else:
                    replaced_text, matched_values, replace_segments = replace_text(
                        current_text,
                        source_text,
                        target_text,
                        use_regex=use_regex,
                        case_sensitive=case_sensitive,
                        regex=regex,
                        replacement_uses_groups=replacement_uses_groups,
                    )
                    changed_segment_count = len(matched_values)
                    display_spans = _display_spans_from_segments(list(replace_segments or []))
                if not matched_values or replaced_text == current_text:
                    failed_rows.append(
                        f"{format_replace_row_label(row)}: 현재 S3 flags.text에서 {operation_label}할 대상이 없습니다."
                    )
                    continue

                flags["text"] = replaced_text
                page_updates.append(
                    {
                        "row_key": str(row.get("row_key", "")).strip(),
                        "current_text": current_text,
                        "replaced_text": replaced_text,
                        "matched_values": list(matched_values),
                        "changed_segment_count": changed_segment_count,
                        "display_spans": list(display_spans),
                    }
                )
                page_changed = True

            if not page_changed:
                continue

            try:
                _save_payload_to_s3_and_cache(self.aws_config, self.cache_dir, json_row, payload)
                verified_payload = _load_payload_from_s3(self.aws_config, json_row)
                verified_shapes = verified_payload.get("shapes", [])
                if not isinstance(verified_shapes, list):
                    raise ValueError(f"{operation_label} 후 S3 검증에 실패했습니다. shapes 구조를 읽을 수 없습니다.")

                for update in page_updates:
                    row_key = str(update.get("row_key", "")).strip()
                    row_info = next(
                        (row for row in list(page_task.get("rows", []) or []) if str(row.get("row_key", "")).strip() == row_key),
                        None,
                    )
                    shape_index = _safe_int(row_info.get("shape_index", -1), -1) if isinstance(row_info, dict) else -1
                    if shape_index < 0 or shape_index >= len(verified_shapes):
                        raise ValueError(f"{operation_label} 후 S3 검증에 실패했습니다. shape 인덱스를 찾을 수 없습니다.")
                    verified_shape = verified_shapes[shape_index]
                    verified_flags = verified_shape.get("flags")
                    verified_text = (
                        str(verified_flags.get("text", "") or "")
                        if isinstance(verified_flags, dict)
                        else ""
                    )
                    if verified_text != str(update["replaced_text"]):
                        raise ValueError(f"{operation_label} 후 S3 검증에 실패했습니다. flags.text 값이 반영되지 않았습니다.")
            except Exception as exc:
                fatal_error = str(exc)
                break

            page_label = str(page_task.get("page_label", "")).strip()
            if page_label:
                updated_payloads[page_label] = copy.deepcopy(payload)
            applied_updates.extend(page_updates)
            updated_pages += 1
            updated_labels += len(page_updates)

        return {
            "snapshot_mismatch_pages": snapshot_mismatch_pages,
            "updated_pages": updated_pages,
            "updated_labels": updated_labels,
            "failed_rows": failed_rows,
            "applied_updates": applied_updates,
            "updated_payloads": updated_payloads,
            "fatal_error": fatal_error,
        }
