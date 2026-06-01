from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

from PyQt5.QtWidgets import QMessageBox

from app.common.shared_status_bar import format_progress_status
from app.common.labels.label_reference import load_label_color_map, load_label_ids

from .s3_loader import S3Loader


class TextAnalysisPageSupportMixin:
    def _initialize_text_analysis_state(self) -> None:
        self.current_s3_rows = []
        self.current_book_rows = []
        self.current_page_rows = []
        self.current_label_rows = []
        self._text_analysis_query_ready = False
        self._text_analysis_queried_book_ids = set()
        self._text_analysis_snapshot_loading = False
        self._text_analysis_snapshot_worker = None
        self._text_analysis_snapshot_request_id = 0
        self._text_analysis_snapshot_json_rows = []
        self._label_color_map = load_label_color_map(self.project_root)
        self._special_char_label_options = load_label_ids(self.project_root)

    def _resolved_special_char_label_options(self) -> list[str]:
        if self._special_char_label_options:
            return list(self._special_char_label_options)
        return sorted(
            {
                str(row.get("label", "")).strip().upper()
                for row in self.current_label_rows
                if str(row.get("label", "")).strip()
            }
        )

    def _refresh_special_char_label_options(self) -> None:
        self.left_panel.set_available_labels(self._resolved_special_char_label_options())

    def apply_shared_settings(
        self,
        config: dict,
        *,
        show_message: bool = False,
        refresh_s3: bool = True,
    ) -> None:
        self.config = copy.deepcopy(config or {})
        if refresh_s3:
            self.refresh_books_from_s3(show_message=show_message)

    def refresh_books_from_s3(self, *, show_message: bool = False) -> None:
        project = self.config.get("project", {})
        aws = self.config.get("aws", {})
        s3_path = str(project.get("s3_path", "")).strip()
        access_key = str(aws.get("access_key", "")).strip()
        secret_key = str(aws.get("secret_key", "")).strip()
        if self._text_analysis_snapshot_worker is not None:
            self._text_analysis_snapshot_worker.request_stop()
        if getattr(self, "_text_analysis_scan_worker", None) is not None:
            self._text_analysis_scan_worker.request_stop()
        if getattr(self, "_text_analysis_replace_worker", None) is not None:
            self._text_analysis_replace_worker.request_stop()
        self._text_analysis_snapshot_request_id += 1
        self._text_analysis_scan_request_id += 1
        self._text_analysis_replace_request_id += 1
        self._text_analysis_snapshot_loading = False
        self._text_analysis_snapshot_worker = None
        self._text_analysis_scan_worker = None
        self._text_analysis_replace_worker = None
        self._text_analysis_snapshot_json_rows = []

        if not s3_path:
            if show_message:
                QMessageBox.information(self, "S3 경로 필요", "설정에서 S3 경로를 먼저 입력해주세요.")
            self._apply_placeholder_state()
            self._text_analysis_is_running = False
            self._refresh_run_button_state()
            return

        if not access_key or not secret_key:
            if show_message:
                QMessageBox.warning(self, "S3 설정 필요", "설정에서 AWS Access Key와 Secret Key를 입력해주세요.")
            self._apply_placeholder_state()
            return

        try:
            bucket, prefix = S3Loader.parse_s3_path(s3_path)
            loader = S3Loader(aws)
            scanned = loader.scan_project(bucket, prefix)
        except Exception as exc:
            if show_message:
                QMessageBox.warning(self, "S3 조회 실패", str(exc))
            self._apply_placeholder_state()
            return

        book_counts: Dict[str, int] = {}
        for row in scanned:
            page_name = str(row.get("page_no", ""))
            if Path(page_name).suffix.lower() in {".png", ".jpg", ".jpeg"}:
                book_id = str(row.get("book_id", "unknown")).strip() or "unknown"
                book_counts[book_id] = book_counts.get(book_id, 0) + 1

        self._set_current_s3_rows(scanned)
        self.current_book_rows = [
            {"book_id": book_id, "total_pages": total_pages}
            for book_id, total_pages in sorted(book_counts.items())
        ]
        self.current_page_rows = []
        self.current_label_rows = []
        self._text_analysis_query_ready = False
        self._text_analysis_queried_book_ids = set()
        self._json_payload_cache.clear()

        self.left_panel.set_books(self.current_book_rows)
        self._refresh_special_char_label_options()
        self._refresh_query_button_state()
        self._refresh_run_button_state()
        self.center_panel.set_books(self.current_book_rows)
        self.center_panel.set_pages([], results_only=False)
        self.right_panel.clear_preview()
        self._refresh_dashboard()
        image_count = sum(
            1
            for row in self.current_s3_rows
            if Path(str(row.get("page_no", ""))).suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        self._set_recent_log(f"S3 갱신 완료: 도서 {len(self.current_book_rows)}권 / 파일 {image_count}개")

        if show_message:
            QMessageBox.information(self, "S3 조회 완료", f"도서 {len(self.current_book_rows)}권을 불러왔습니다.")

    def _refresh_s3_rows_for_query(self, *, selected_books: set[str], all_books_selected: bool) -> bool:
        project = self.config.get("project", {})
        aws = self.config.get("aws", {})
        s3_path = str(project.get("s3_path", "")).strip()
        access_key = str(aws.get("access_key", "")).strip()
        secret_key = str(aws.get("secret_key", "")).strip()
        if not s3_path:
            QMessageBox.information(self, "S3 설정 필요", "프로젝트 설정에서 S3 경로를 먼저 입력해 주세요.")
            return False
        if not access_key or not secret_key:
            QMessageBox.warning(self, "S3 설정 필요", "프로젝트 설정에서 AWS Access Key와 Secret Key를 먼저 입력해 주세요.")
            return False

        try:
            bucket, prefix = S3Loader.parse_s3_path(s3_path)
            loader = S3Loader(aws)
            scanned = loader.scan_project(bucket, prefix)
        except Exception as exc:
            QMessageBox.warning(self, "S3 조회 실패", str(exc))
            return False

        book_counts: Dict[str, int] = {}
        for row in scanned:
            page_name = str(row.get("page_no", ""))
            if Path(page_name).suffix.lower() in {".png", ".jpg", ".jpeg"}:
                book_id = str(row.get("book_id", "unknown")).strip() or "unknown"
                book_counts[book_id] = book_counts.get(book_id, 0) + 1

        self._set_current_s3_rows(scanned)
        self.current_book_rows = [
            {"book_id": book_id, "total_pages": total_pages}
            for book_id, total_pages in sorted(book_counts.items())
        ]
        self.current_page_rows = []
        self.current_label_rows = []
        self._text_analysis_query_ready = False
        self._text_analysis_queried_book_ids = set()
        self._json_payload_cache.clear()
        self.left_panel.set_books(
            self.current_book_rows,
            selected_book_ids=None if all_books_selected else selected_books,
        )
        self._refresh_special_char_label_options()
        self._refresh_query_button_state()
        self._refresh_run_button_state()
        self.center_panel.set_books(self.current_book_rows)
        return True

    def _apply_placeholder_state(self) -> None:
        if self._text_analysis_snapshot_worker is not None:
            self._text_analysis_snapshot_worker.request_stop()
        if getattr(self, "_text_analysis_scan_worker", None) is not None:
            self._text_analysis_scan_worker.request_stop()
        if getattr(self, "_text_analysis_replace_worker", None) is not None:
            self._text_analysis_replace_worker.request_stop()
        self._text_analysis_snapshot_request_id += 1
        self._text_analysis_scan_request_id += 1
        self._text_analysis_replace_request_id += 1
        self._set_current_s3_rows([])
        self.current_book_rows = []
        self.current_page_rows = []
        self.current_label_rows = []
        self._text_analysis_query_ready = False
        self._text_analysis_queried_book_ids = set()
        self._text_analysis_is_running = False
        self._text_analysis_stop_requested = False
        self._text_analysis_snapshot_loading = False
        self._text_analysis_snapshot_worker = None
        self._text_analysis_scan_worker = None
        self._text_analysis_replace_worker = None
        self._text_analysis_snapshot_json_rows = []
        self.left_panel.set_books([])
        self._refresh_special_char_label_options()
        self.left_panel.set_run_ready(False)
        self._refresh_query_button_state()
        self.center_panel.set_books([])
        self.center_panel.set_pages([], results_only=False)
        self.right_panel.clear_preview()
        self._refresh_dashboard()

    def _set_recent_log(self, message: str) -> None:
        text = str(message).strip()
        if text and self._status_callback is not None:
            self._status_callback(text)

    def _set_progress(self, desc: str, current: int, total: int) -> None:
        self._set_recent_log(format_progress_status(desc, current, total))
