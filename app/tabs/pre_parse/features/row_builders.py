from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.common.labels.label_reference import load_label_color_map
from app.tabs.pre_parse.features.base_state import BASE_STATE_ERROR, BASE_STATE_NORMAL


class PreParseRowBuildersMixin:
    def _build_label_rows_for_payload(
        self,
        *,
        page_key: str,
        book_id: str,
        page_name: str,
        payload: Optional[Dict],
        issue_detail_map: Dict[Tuple[str, int, int], List[str]],
        issue_type_map: Dict[Tuple[str, int, int], List[str]],
    ) -> List[dict]:
        rows: List[dict] = []
        page_no = self._extract_page_no(page_key.split(":", 1)[1] if ":" in page_key else page_key)
        for shape in self._load_shapes_from_payload(payload):
            shape_index = int(shape.get("shape_index", -1))
            details = issue_detail_map.get((book_id, page_no, shape_index), [])
            error_types = issue_type_map.get((book_id, page_no, shape_index), [])
            rows.append(
                {
                    "row_key": f"{page_key}:shape:{shape_index}",
                    "page_no": page_key,
                    "book_id": book_id,
                    "page": page_name,
                    "shape_index": shape_index,
                    "label_id": str(shape_index + 1),
                    "label": str(shape.get("label", "")),
                    "value": str(shape.get("value", "")),
                    "error_detail": " / ".join(details),
                    "error_type": " / ".join(error_types),
                    "base_state": BASE_STATE_ERROR if details else BASE_STATE_NORMAL,
                    "is_problem": shape.get("is_problem", None),
                    "problem_reason": str(shape.get("problem_reason", "") or ""),
                }
            )
        return rows

    def _load_shapes_from_payload(self, payload: Optional[Dict]) -> List[dict]:
        if not isinstance(payload, dict):
            return []
        shapes = payload.get("shapes", [])
        if not isinstance(shapes, list):
            return []
        results: List[dict] = []
        for idx, shape in enumerate(shapes):
            if not isinstance(shape, dict):
                continue
            label = str(shape.get("label", "")).strip().upper()
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
                    except Exception:
                        continue
            bbox = [min(xs), min(ys), max(xs), max(ys)] if xs and ys else [0, 0, 0, 0]
            results.append(
                {
                    "shape_index": idx,
                    "label": label,
                    "bbox": bbox,
                    "value": self._shape_value_from_flags(shape),
                    "is_problem": shape.get("is_problem", None),
                    "problem_reason": str(shape.get("problem_reason", "") or ""),
                }
            )
        return results

    def _build_issue_detail_map(self, issues: List[dict]) -> Dict[Tuple[str, int, int], List[str]]:
        detail_map: Dict[Tuple[str, int, int], List[str]] = {}
        for issue in issues:
            page_key = str(issue.get("page_no", ""))
            issue_book, issue_page = self._split_issue_page(page_key)
            if not issue_book:
                issue_book = str(issue.get("book_id", "")).strip()
            page_no = self._extract_page_no(issue_page)
            shape_index = self._to_int(issue.get("shape_index", -1), default=-1)
            if shape_index < 0:
                continue
            check_id = str(issue.get("check_id", "")).strip()
            error_message = str(issue.get("error_message", issue.get("message", ""))).strip()
            detail = self._issue_detail_text(check_id, error_message)
            key = (issue_book, page_no, shape_index)
            bucket = detail_map.setdefault(key, [])
            if detail and detail not in bucket:
                bucket.append(detail)
        return detail_map

    def _build_issue_type_map(self, issues: List[dict]) -> Dict[Tuple[str, int, int], List[str]]:
        type_map: Dict[Tuple[str, int, int], List[str]] = {}
        for issue in issues:
            page_key = str(issue.get("page_no", ""))
            issue_book, issue_page = self._split_issue_page(page_key)
            if not issue_book:
                issue_book = str(issue.get("book_id", "")).strip()
            page_no = self._extract_page_no(issue_page)
            shape_index = self._to_int(issue.get("shape_index", -1), default=-1)
            if shape_index < 0:
                continue
            error_type = str(issue.get("error_type", "")).strip()
            if not error_type:
                continue
            key = (issue_book, page_no, shape_index)
            bucket = type_map.setdefault(key, [])
            if error_type not in bucket:
                bucket.append(error_type)
        return type_map

    def _plugin_description(self, check_id: str) -> str:
        plugin_id = str(check_id).strip()
        if not plugin_id:
            return ""
        try:
            plugin = self.registry.get(plugin_id)
        except Exception:
            return ""
        description = str(getattr(plugin, "DESCRIPTION", "") or "").strip()
        if description:
            return description
        try:
            metadata = plugin.metadata()
        except Exception:
            return ""
        return str(metadata.get("description", "") or "").strip()

    def _issue_detail_text(self, check_id: str, error_message: str) -> str:
        del check_id
        return str(error_message or "").strip()

    def _shape_snapshot_from_payload(self, payload: Optional[Dict], shape_index: int) -> Dict[str, object]:
        snapshot: Dict[str, object] = {"label": "", "bbox": [0, 0, 0, 0], "value": ""}
        if not isinstance(payload, dict):
            return snapshot
        shapes = payload.get("shapes", [])
        if not isinstance(shapes, list) or shape_index < 0 or shape_index >= len(shapes):
            return snapshot
        shape = shapes[shape_index]
        if not isinstance(shape, dict):
            return snapshot

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
                except Exception:
                    continue

        if xs and ys:
            snapshot["bbox"] = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
        snapshot["label"] = str(shape.get("label", "")).strip().upper()
        snapshot["value"] = self._shape_value_from_flags(shape)
        return snapshot

    def _build_label_rows_for_pages(
        self,
        page_rows: List[dict],
        issue_detail_map: Dict[Tuple[str, int, int], List[str]],
        issue_type_map: Dict[Tuple[str, int, int], List[str]],
    ) -> List[dict]:
        rows: List[dict] = []
        for page in page_rows:
            page_key = str(page.get("page_no", ""))
            if ":" in page_key:
                book_id, page_token = page_key.split(":", 1)
            else:
                book_id, page_token = str(page.get("book_id", "")), page_key
            page_no = self._extract_page_no(page_token)

            json_row = self._resolve_json_row(book_id, page_token)
            shapes = self._load_shapes_from_json_row(json_row)
            page_name = str(page.get("file_name", "")).strip()
            if not page_name:
                page_name = str(page_token).rsplit(".", 1)[0]
                if page_name.startswith(f"{book_id}_"):
                    page_name = page_name[len(book_id) + 1 :]

            for shape in shapes:
                shape_index = int(shape.get("shape_index", -1))
                details = issue_detail_map.get((book_id, page_no, shape_index), [])
                error_types = issue_type_map.get((book_id, page_no, shape_index), [])
                rows.append(
                    {
                        "row_key": f"{page_key}:shape:{shape_index}",
                        "page_no": page_key,
                        "book_id": book_id,
                        "page": page_name,
                        "shape_index": shape_index,
                        "label_id": str(shape_index + 1),
                        "label": str(shape.get("label", "")),
                        "value": str(shape.get("value", "")),
                        "error_detail": " / ".join(details),
                        "error_type": " / ".join(error_types),
                        "base_state": BASE_STATE_ERROR if details else BASE_STATE_NORMAL,
                        "is_problem": shape.get("is_problem", None),
                        "problem_reason": str(shape.get("problem_reason", "") or ""),
                    }
                )
        return rows

    def _build_placeholder_rows_for_pages(self, page_rows: List[dict]) -> List[dict]:
        rows: List[dict] = []
        for i, page in enumerate(page_rows):
            page_key = str(page.get("page_no", ""))
            book_id = str(page.get("book_id", ""))
            page_name = str(page.get("file_name", ""))
            has_error_state = int(page.get("issue_count", 0)) > 0
            rows.append(
                {
                    "row_key": f"{page_key}:placeholder:{i}",
                    "page_no": page_key,
                    "book_id": book_id,
                    "page": page_name,
                    "shape_index": -1,
                    "label_id": "",
                    "label": "",
                    "value": "",
                    "error_detail": "",
                    "error_type": "",
                    "base_state": BASE_STATE_ERROR if has_error_state else BASE_STATE_NORMAL,
                    "is_problem": None,
                    "problem_reason": "",
                }
            )
        return rows

    def _build_page_rows_for_books(self, selected_books: set[str]) -> List[dict]:
        logical_pages: Dict[Tuple[str, str], dict] = {}
        for item in self.current_s3_pages:
            book_id = str(item.get("book_id", "unknown"))
            if selected_books and book_id not in selected_books:
                continue
            page_no = str(item.get("page_no", ""))
            if not page_no:
                continue
            page_key = f"{book_id}:{page_no}"
            issue_count = int(item.get("issue_count", 0))
            base_name = page_no.rsplit(".", 1)[0]
            base_name_clean = base_name[len(book_id) + 1 :] if base_name.startswith(f"{book_id}_") else base_name
            logical_key = (book_id, base_name_clean)
            info = logical_pages.setdefault(
                logical_key,
                {
                    "page_no": page_key,
                    "book_id": book_id,
                    "file_name": base_name_clean,
                    "status": item.get("status", "PENDING"),
                    "issue_count": 0,
                },
            )
            info["issue_count"] += issue_count

        page_rows: List[dict] = []
        for info in logical_pages.values():
            icount = int(info.get("issue_count", 0))
            page_rows.append(
                {
                    "page_no": info["page_no"],
                    "book_id": info["book_id"],
                    "file_name": info["file_name"],
                    "status": info.get("status", "PENDING"),
                    "issue_count": icount,
                    "box_count": icount,
                    "failed_checks": [],
                    "error_detail": "",
                }
            )
        return page_rows

    def _to_int(self, value, default: int = -1) -> int:
        try:
            if value is None:
                return default
            text = str(value).strip()
            if not text:
                return default
            return int(text)
        except Exception:
            return default

    def _load_label_color_map(self) -> Dict[str, str]:
        return load_label_color_map(self.project_root)
