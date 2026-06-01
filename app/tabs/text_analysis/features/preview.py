from __future__ import annotations

from typing import List

from PyQt5.QtCore import QModelIndex


class TextAnalysisPreviewMixin:
    def _show_preview_for_proxy_index(self, proxy_index: QModelIndex) -> None:
        if not proxy_index.isValid():
            self.right_panel.clear_preview()
            return

        row_data = self.center_panel.source_row_data(proxy_index.row())
        if not row_data:
            self.right_panel.clear_preview()
            return

        book_id = str(row_data.get("book_id", "")).strip()
        page_name = str(row_data.get("page_name", "")).strip()
        image_row = self._resolve_image_row(book_id, page_name)
        try:
            image_path = self._download_preview_image(image_row) if image_row else ""
        except Exception as exc:
            self._set_recent_log(f"미리보기 로드 실패: {exc}")
            image_path = ""

        bboxes: List[dict] = []
        selected_index = -1
        selected_row_key = str(row_data.get("row_key", "")).strip()
        for page_row in self.current_label_rows:
            if str(page_row.get("book_id", "")).strip() != book_id:
                continue
            if str(page_row.get("page_name", "")).strip() != page_name:
                continue

            bbox = page_row.get("bbox", [0, 0, 0, 0])
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue

            label = str(page_row.get("label", "")).strip().upper()
            bboxes.append(
                {
                    "bbox": bbox,
                    "color": self._label_color_map.get(label, "#9ca3af"),
                    "label": label,
                    "tone_down": True,
                }
            )
            if str(page_row.get("row_key", "")).strip() == selected_row_key:
                selected_index = len(bboxes) - 1

        if selected_index >= 0:
            for idx, bbox in enumerate(bboxes):
                bbox["tone_down"] = idx != selected_index
        else:
            for bbox in bboxes:
                bbox["tone_down"] = False

        self.right_panel.show_preview(
            image_path=image_path,
            bboxes=bboxes,
            selected_index=selected_index,
        )
