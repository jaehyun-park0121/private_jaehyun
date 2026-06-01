from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtWidgets import QApplication

from app.tabs.text_analysis.features.base_state import BASE_STATE_ERROR, BASE_STATE_NORMAL
from app.tabs.text_analysis.tools.base import normalize_match_values, render_disallowed_char
from app.tabs.text_analysis.tools.search import build_match_detail, search_matches


_KWIC_CONTEXT_CHARS = 20


def build_kwic_context(
    text: str,
    match_start: int,
    match_end: int,
    *,
    context_chars: int = _KWIC_CONTEXT_CHARS,
) -> Dict[str, Any]:
    if not text or match_start < 0 or match_end <= match_start:
        return {"display_text": text or "", "prefix": "", "match": "", "suffix": "", "match_start": 0, "match_end": 0}

    prefix_start = max(0, match_start - context_chars)
    suffix_end = min(len(text), match_end + context_chars)

    prefix = text[prefix_start:match_start]
    match = text[match_start:match_end]
    suffix = text[match_end:suffix_end]

    ellipsis_before = "\u2026" if prefix_start > 0 else ""
    ellipsis_after = "\u2026" if suffix_end < len(text) else ""

    display_text = f"{ellipsis_before}{prefix}{match}{suffix}{ellipsis_after}"
    prefix_display = f"{ellipsis_before}{prefix}"

    return {
        "display_text": display_text,
        "prefix": prefix_display,
        "match": match,
        "suffix": f"{suffix}{ellipsis_after}",
        "match_start": len(prefix_display),
        "match_end": len(prefix_display) + len(match),
    }


def _make_passthrough_row(row: Dict[str, Any]) -> Dict[str, Any]:
    expanded = dict(row)
    expanded["parent_row_key"] = str(row.get("row_key", ""))
    expanded["match_index"] = -1
    expanded["_kwic_prefix"] = ""
    expanded["_kwic_match"] = ""
    expanded["_kwic_suffix"] = ""
    return expanded


def expand_label_rows_to_display_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    display_rows: List[Dict[str, Any]] = []
    for row in rows:
        tool_id = str(row.get("tool_id", "")).strip()
        text = str(row.get("flags_text", "") or "")
        spans = list(row.get("match_spans", []) or [])

        if not spans or tool_id not in ("special_char_analysis", "search_tool", "replace_tool", "nfkc_normalize_tool") or not text:
            display_rows.append(_make_passthrough_row(row))
            continue

        parsed_spans: List[Tuple[int, int, str]] = []
        for span in spans:
            if not isinstance(span, (list, tuple)) or len(span) < 3:
                continue
            try:
                start, end, group = int(span[0]), int(span[1]), str(span[2])
                if 0 <= start < end <= len(text) and group:
                    parsed_spans.append((start, end, group))
            except (TypeError, ValueError):
                continue

        if not parsed_spans:
            display_rows.append(_make_passthrough_row(row))
            continue

        preview_segments = list(row.get("replace_preview_segments", []) or [])
        segment_by_start: Dict[int, Dict[str, Any]] = {}
        for seg in preview_segments:
            try:
                seg_start = int(seg.get("start", -1))
                if seg_start >= 0:
                    segment_by_start[seg_start] = seg
            except (TypeError, ValueError):
                pass

        for match_idx, (start, end, match_value) in enumerate(parsed_spans):
            kwic = build_kwic_context(text, start, end)
            display_row = dict(row)
            display_row["parent_row_key"] = str(row.get("row_key", ""))
            display_row["match_index"] = match_idx
            display_row["value"] = kwic["display_text"]
            display_row["_kwic_prefix"] = kwic["prefix"]
            display_row["_kwic_match"] = kwic["match"]
            display_row["_kwic_suffix"] = kwic["suffix"]
            display_row["_match_value"] = match_value
            display_row["_match_start"] = start
            display_row["_match_end"] = end
            display_row["tool_error_matches"] = [match_value]
            display_row["highlight_matches"] = [match_value]
            display_row["detail_filter_values"] = [match_value]

            matched_seg = segment_by_start.get(start)
            if matched_seg is not None:
                display_row["replace_preview_segments"] = [matched_seg]
                display_row["_replace_target_text"] = str(matched_seg.get("replacement", "") or "")
            else:
                display_row["replace_preview_segments"] = []
                display_row["_replace_target_text"] = ""

            display_rows.append(display_row)

    return display_rows


def deduplicate_display_rows_to_label_rows(
    display_rows: List[Dict[str, Any]],
    label_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    label_by_key = {
        str(row.get("row_key", "")): row
        for row in label_rows
        if str(row.get("row_key", "")).strip()
    }
    seen: set[str] = set()
    result: List[Dict[str, Any]] = []
    for d_row in display_rows:
        parent_key = str(d_row.get("parent_row_key", d_row.get("row_key", ""))).strip()
        if not parent_key or parent_key in seen:
            continue
        seen.add(parent_key)
        label_row = label_by_key.get(parent_key)
        if label_row is not None:
            result.append(label_row)
    return result


class TextAnalysisRowBuildersMixin:
    def _is_placeholder_data(self) -> bool:
        return any(int(row.get("shape_index", 0) or 0) < 0 for row in self.current_label_rows)

    def _build_page_rows_for_books(self, selected_books: set[str]) -> List[dict]:
        logical_pages: Dict[Tuple[str, str], dict] = {}
        for item in self.current_s3_rows:
            book_id = str(item.get("book_id", "")).strip()
            if selected_books and book_id not in selected_books:
                continue
            page_no = str(item.get("page_no", "")).strip()
            if not page_no or Path(page_no).suffix.lower() != ".json":
                continue

            base_name = page_no.rsplit(".", 1)[0]
            if base_name.startswith(f"{book_id}_"):
                page_display = base_name[len(book_id) + 1 :]
            else:
                page_display = base_name

            logical_pages[(book_id, page_no)] = {
                "page_no": f"{book_id}:{page_no}",
                "book_id": book_id,
                "page_name": page_no,
                "file_name": page_display,
                "status": "PENDING",
                "issue_count": 0,
            }
        return list(logical_pages.values())

    def _build_placeholder_rows_for_pages(self, page_rows: List[dict]) -> List[dict]:
        rows: List[dict] = []
        for index, page in enumerate(page_rows):
            page_key = str(page.get("page_no", "")).strip()
            rows.append(
                {
                    "row_key": f"{page_key}:placeholder:{index}",
                    "book_id": str(page.get("book_id", "")).strip(),
                    "page_no": page_key,
                    "page_name": str(page.get("page_name", "")).strip(),
                    "page": str(page.get("file_name", "")).strip(),
                    "file_name": str(page.get("file_name", "")).strip(),
                    "label_id": "",
                    "shape_index": -1,
                    "label": "",
                    "value": "",
                    "flags_text": "",
                    "detail_filter_tool_id": "",
                    "detail_filter_values": [],
                    "base_state": BASE_STATE_NORMAL,
                    "is_problem": False,
                    "problem_reason": "",
                    "tool_id": "",
                    "tool_error_detail": "",
                    "tool_error_type": "",
                    "tool_error_matches": [],
                    "match_spans": [],
                    "highlight_text": "",
                    "highlight_matches": [],
                    "replace_preview_value": "",
                    "replace_preview_segments": [],
                    "replace_applied": False,
                    "replace_original_value": "",
                    "bbox": [0, 0, 0, 0],
                }
            )
        return rows

    def _load_full_label_data(self) -> bool:
        selected_books = set(self._text_analysis_queried_book_ids)
        json_rows = [
            row
            for row in self.current_s3_rows
            if str(row.get("book_id", "")).strip() in selected_books
            and Path(str(row.get("page_no", "")).strip()).suffix.lower() == ".json"
        ]

        label_rows: List[Dict[str, Any]] = []
        total = len(json_rows)
        for index, json_row in enumerate(json_rows, start=1):
            if self._text_analysis_stop_requested:
                return False
            QApplication.processEvents()
            self._set_progress("페이지 미리보기용 JSON 읽기", index, total)
            try:
                payload = self._load_page_json_payload(json_row)
            except Exception as exc:
                self._set_recent_log(f"페이지 미리보기용 JSON 읽기 실패: {json_row.get('page_no', '')} ({exc})")
                continue

            book_id = str(json_row.get("book_id", "")).strip()
            page_name = str(json_row.get("page_no", "")).strip()
            for shape_index, shape in enumerate(self._extract_shapes(payload)):
                label_rows.append(
                    self._build_label_row(
                        book_id=book_id,
                        page_name=page_name,
                        shape=shape,
                        shape_index=shape_index,
                    )
                )

        if self._text_analysis_stop_requested:
            return False

        self.current_label_rows = label_rows
        self._refresh_special_char_label_options()
        return True

    def _json_rows_for_books(self, selected_books: set[str]) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in self.current_s3_rows
            if str(row.get("book_id", "")).strip() in selected_books
            and Path(str(row.get("page_no", "")).strip()).suffix.lower() == ".json"
        ]

    def _build_label_rows_from_json_rows(self, json_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        label_rows: List[Dict[str, Any]] = []
        total = len(json_rows)
        for index, json_row in enumerate(json_rows, start=1):
            if self._text_analysis_stop_requested:
                break
            QApplication.processEvents()
            self._set_progress("텍스트 분석 결과 정리", index, total)
            try:
                payload = self._load_page_json_payload(json_row)
            except Exception as exc:
                self._set_recent_log(f"텍스트 분석 결과 정리 실패: {json_row.get('page_no', '')} ({exc})")
                continue

            book_id = str(json_row.get("book_id", "")).strip()
            page_name = str(json_row.get("page_no", "")).strip()
            for shape_index, shape in enumerate(self._extract_shapes(payload)):
                label_rows.append(
                    self._build_label_row(
                        book_id=book_id,
                        page_name=page_name,
                        shape=shape,
                        shape_index=shape_index,
                    )
                )
        return label_rows

    def _extract_shapes(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        shapes = payload.get("shapes", [])
        if not isinstance(shapes, list):
            return []
        return [shape for shape in shapes if isinstance(shape, dict)]

    def _build_label_row(
        self,
        *,
        book_id: str,
        page_name: str,
        shape: Dict[str, Any],
        shape_index: int,
    ) -> Dict[str, Any]:
        is_problem = bool(shape.get("is_problem", False))
        problem_reason = str(shape.get("problem_reason", "") or "").strip()
        row = {
            "row_key": f"{book_id}:{page_name}:{shape_index + 1}",
            "book_id": book_id,
            "page_no": f"{book_id}:{page_name}",
            "page_name": page_name,
            "page": self._format_page_display(page_name),
            "file_name": self._format_page_display(page_name),
            "label_id": shape_index + 1,
            "shape_index": shape_index,
            "label": str(shape.get("label", "")).strip(),
            "value": self._shape_flag_text(shape),
            "flags_text": self._shape_flag_text(shape),
            "detail_filter_tool_id": "",
            "detail_filter_values": [],
            "base_state": BASE_STATE_NORMAL,
            "is_problem": is_problem,
            "problem_reason": problem_reason,
            "tool_id": "",
            "tool_error_detail": "",
            "tool_error_type": "",
            "tool_error_matches": [],
            "match_spans": [],
            "highlight_text": "",
            "highlight_matches": [],
            "replace_preview_value": "",
            "replace_preview_segments": [],
            "replace_applied": False,
            "replace_original_value": "",
            "bbox": self._shape_bbox(shape),
        }
        self._refresh_row_result_state(row)
        return row

    def _refresh_row_result_state(self, row: Dict[str, Any]) -> None:
        detail_text = str(row.get("tool_error_detail", "") or "").strip()
        row["base_state"] = BASE_STATE_ERROR if detail_text else BASE_STATE_NORMAL

    def _render_disallowed_char(self, char: str) -> str:
        return render_disallowed_char(char)

    def _search_matches(
        self,
        text: str,
        keyword: str,
        *,
        use_regex: bool,
        case_sensitive: bool,
        regex: Optional[re.Pattern],
    ) -> List[str]:
        return search_matches(
            text,
            keyword,
            use_regex=use_regex,
            case_sensitive=case_sensitive,
            regex=regex,
        )

    def _normalize_match_values(self, matches: Any) -> List[str]:
        return normalize_match_values(matches)

    def _set_detail_filter_state(self, row: Dict[str, Any], *, tool_id: str, values: Any) -> None:
        detail_tool_id = str(tool_id or "").strip()
        row["detail_filter_tool_id"] = detail_tool_id
        if detail_tool_id in {"search_tool", "special_char_analysis"}:
            row["detail_filter_values"] = self._normalize_match_values(values)
            return
        row["detail_filter_values"] = []

    def _build_match_detail(self, *, prefix: str, pattern: str, matches: List[str], use_regex: bool) -> str:
        return build_match_detail(prefix=prefix, pattern=pattern, matches=matches, use_regex=use_regex)

    def _issues_from_label_row(self, row: Dict[str, Any]) -> List[dict]:
        matches = self._normalize_match_values(row.get("tool_error_matches", []))
        if not matches:
            return []
        issues: List[dict] = []
        tool_id = str(row.get("tool_id", "")).strip()
        for match_value in matches:
            issues.append(
                {
                    "page_no": str(row.get("page_no", "")).strip(),
                    "page_display": str(row.get("page", "")).strip(),
                    "book_id": str(row.get("book_id", "")).strip(),
                    "label": str(row.get("label", "")).strip(),
                    "detected_text": self._render_detected_text(tool_id, str(match_value)),
                    "description": str(row.get("tool_error_detail", "")).strip(),
                }
            )
        return issues

    def _render_detected_text(self, tool_id: str, value: str) -> str:
        if tool_id == "special_char_analysis":
            return self._render_disallowed_char(value)
        return value

    def _shape_flag_text(self, shape: Dict[str, Any]) -> str:
        flags = shape.get("flags")
        if not isinstance(flags, dict):
            return ""
        return str(flags.get("text", "") or "")

    def _shape_bbox(self, shape: Dict[str, Any]) -> List[float]:
        points = shape.get("points", [])
        xs: List[float] = []
        ys: List[float] = []
        if isinstance(points, list):
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                try:
                    xs.append(float(point[0]))
                    ys.append(float(point[1]))
                except (TypeError, ValueError):
                    continue
        if not xs or not ys:
            return [0, 0, 0, 0]
        return [min(xs), min(ys), max(xs), max(ys)]

    def _extract_page_no(self, page_name: str) -> int:
        matched = re.search(r"(\d+)(?!.*\d)", str(page_name))
        return int(matched.group(1)) if matched else 0

    def _format_page_display(self, page_name: str) -> str:
        page_no = self._extract_page_no(page_name)
        return f"{page_no:04d}" if page_no > 0 else str(Path(page_name).stem)
