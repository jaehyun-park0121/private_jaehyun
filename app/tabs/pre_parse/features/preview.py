from __future__ import annotations

from typing import List


class PreParsePreviewMixin:
    def _fallback_bboxes_from_issues(self, issues: List[dict], book_id: str, page_token: str) -> List[dict]:
        bboxes = self._filter_issues_for_page(issues, book_id, page_token)
        for bbox in bboxes:
            label = str(bbox.get("label", "")).strip().upper()
            bbox["color"] = self._label_color_map.get(label, "#9ca3af")
        return bboxes

    def _selected_bbox_index_for_row(self, row: int, page_bboxes: List[dict]) -> int:
        row_data = self.center_panel.source_row_data(row)
        if row_data is None:
            return -1
        shape_index = self._to_int(row_data.get("shape_index", -1), default=-1)
        if shape_index >= 0:
            for idx, issue in enumerate(page_bboxes):
                if self._to_int(issue.get("shape_index", -1), default=-1) == shape_index:
                    return idx
            return -1
        label_id_text = str(row_data.get("label_id", "")).strip()
        if not label_id_text.isdigit():
            return -1
        target_shape = max(int(label_id_text) - 1, 0)
        for idx, issue in enumerate(page_bboxes):
            if self._to_int(issue.get("shape_index", -1), default=-1) == target_shape:
                return idx
        return -1

    def _show_pre_parse_preview_for_row(self, row: int) -> None:
        row_data = self.center_panel.source_row_data(row)
        if row_data is None:
            return

        page_key = str(row_data.get("page_no", ""))
        if ":" in page_key:
            book_id, page_token = page_key.split(":", 1)
        else:
            book_id, page_token = "", page_key

        image_row = self._resolve_image_row(book_id, page_token)
        image_path = self._download_preview_image(image_row) if image_row else ""
        self.right_panel.image_viewer.set_image(image_path)

        page_payload = self._load_snapshot_page_json_payload(book_id, page_token)
        page_bboxes: List[dict] = []
        for shape in self._load_shapes_from_payload(page_payload):
            shape_index = int(shape.get("shape_index", -1))
            if shape_index < 0:
                continue
            label = str(shape.get("label", "")).strip().upper()
            page_bboxes.append(
                {
                    "shape_index": shape_index,
                    "label": label,
                    "bbox": shape.get("bbox", [0, 0, 0, 0]),
                    "color": self._label_color_map.get(label, "#9ca3af"),
                    "tone_down": True,
                }
            )

        if not page_bboxes:
            page_bboxes = self._fallback_bboxes_from_issues(self.last_page_issues, book_id, page_token)

        selected_bbox_index = self._selected_bbox_index_for_row(row, page_bboxes)
        if selected_bbox_index >= 0:
            for idx, bbox in enumerate(page_bboxes):
                bbox["tone_down"] = idx != selected_bbox_index
        else:
            for bbox in page_bboxes:
                bbox["tone_down"] = False
        self.right_panel.image_viewer.set_bboxes(page_bboxes, selected_bbox_index)
