from __future__ import annotations

from typing import Any, Dict, List

from PyQt5.QtWidgets import QApplication, QMessageBox

from app.common.config.parallel_settings import resolve_parallel_workers

from .json_snapshot_worker import TextAnalysisJsonSnapshotWorker


class TextAnalysisSnapshotFlowMixin:
    def query_selected_books(self) -> None:
        if self._text_analysis_snapshot_loading:
            if not self._request_snapshot_stop():
                self._set_recent_log("JSON 스냅샷 중지 요청 실패")
            self._refresh_query_button_state()
            return

        if self._text_analysis_is_running:
            QMessageBox.information(self, "실행 중", "실행 중에는 조회를 다시 시작할 수 없습니다.")
            return

        selected_books = set(self.left_panel.selected_book_ids())
        if not selected_books:
            QMessageBox.information(self, "안내", "도서를 1권 이상 선택해 주세요.")
            return

        all_books_selected = selected_books == set(self.left_panel.book_ids())
        if not self._refresh_s3_rows_for_query(
            selected_books=selected_books,
            all_books_selected=all_books_selected,
        ):
            return

        selected_books = set(self.left_panel.selected_book_ids())
        if not selected_books:
            QMessageBox.information(self, "안내", "도서를 1권 이상 선택해 주세요.")
            return

        if not self.current_s3_rows:
            QMessageBox.information(self, "안내", "먼저 S3 도서 목록을 불러와 주세요.")
            return

        page_rows = self._build_page_rows_for_books(selected_books)
        self.center_panel.set_books([{"book_id": book_id} for book_id in sorted(selected_books)])

        self.current_page_rows = self._build_placeholder_rows_for_pages(page_rows)
        self.current_label_rows = list(self.current_page_rows)
        self._text_analysis_query_ready = False
        self._text_analysis_queried_book_ids = set(selected_books)
        self._refresh_special_char_label_options()
        self.center_panel.set_pages(self.current_page_rows, results_only=False)
        self._refresh_dashboard()
        self._refresh_query_button_state()
        self._refresh_run_button_state()

        if self.current_page_rows:
            self._select_first_row_after_refresh(prefer_result=True)
        else:
            self.right_panel.clear_preview()

        self._set_recent_log(
            f"조회 완료: 도서 {len(selected_books)}권 / 페이지 {len(page_rows)}개 / JSON 스냅샷 준비 시작"
        )

        json_rows = self._json_rows_for_books(selected_books)
        if not json_rows:
            self._set_recent_log("JSON 스냅샷 대상이 없어 바로 실행 가능한 상태로 전환했습니다.")
            self._text_analysis_query_ready = True
            self._refresh_run_button_state()
            return

        self._begin_snapshot_loading(json_rows)

    def _refresh_query_button_state(self) -> None:
        if self._text_analysis_snapshot_loading:
            self.left_panel.query_btn.setText("중지")
            self.left_panel.query_btn.setEnabled(True)
            self.left_panel.book_list.setEnabled(False)
            self.left_panel.select_all_books_checkbox.setEnabled(False)
            return

        if self._text_analysis_is_running:
            self.left_panel.query_btn.setText("조회")
            self.left_panel.query_btn.setEnabled(False)
            self.left_panel.book_list.setEnabled(False)
            self.left_panel.select_all_books_checkbox.setEnabled(False)
            return

        self.left_panel.query_btn.setText("조회")
        self.left_panel.query_btn.setEnabled(True)
        self.left_panel.book_list.setEnabled(True)
        self.left_panel.select_all_books_checkbox.setEnabled(True)

    def _request_snapshot_stop(self) -> bool:
        worker = self._text_analysis_snapshot_worker
        if worker is None:
            return False
        try:
            self._text_analysis_stop_requested = True
            worker.request_stop()
            self._set_recent_log("JSON 스냅샷 중지 요청됨: 진행 중인 다운로드 정리 후 멈춥니다.")
            return True
        except Exception as exc:
            self._set_recent_log(f"JSON 스냅샷 중지 요청 실패: {exc}")
            return False

    def _begin_snapshot_loading(self, json_rows: List[Dict[str, Any]]) -> None:
        request_id = self._text_analysis_snapshot_request_id + 1
        self._text_analysis_snapshot_request_id = request_id
        self._text_analysis_snapshot_json_rows = [dict(row) for row in json_rows]
        self._text_analysis_snapshot_loading = True
        self._text_analysis_stop_requested = False

        worker_count = resolve_parallel_workers(self.config, total_tasks=len(json_rows))
        worker = TextAnalysisJsonSnapshotWorker(
            aws_config=self.config.get("aws", {}),
            json_rows=self._text_analysis_snapshot_json_rows,
            cache_dir=str(self._json_cache_dir),
            max_workers=worker_count,
        )
        self._text_analysis_snapshot_worker = worker
        worker.progress.connect(
            lambda desc, current, total, rid=request_id: self._on_snapshot_progress(rid, desc, current, total)
        )
        worker.finished_ok.connect(
            lambda cache_paths, failures, rid=request_id: self._on_snapshot_finished(rid, cache_paths, failures)
        )
        worker.cancelled.connect(
            lambda cache_paths, failures, rid=request_id: self._on_snapshot_cancelled(rid, cache_paths, failures)
        )
        worker.failed.connect(lambda traceback_text, rid=request_id: self._on_snapshot_failed(rid, traceback_text))
        self._refresh_query_button_state()
        self._refresh_run_button_state()
        worker.start()

    def _finish_snapshot_loading(self, request_id: int) -> None:
        if request_id != self._text_analysis_snapshot_request_id:
            return
        self._text_analysis_snapshot_loading = False
        worker = self._text_analysis_snapshot_worker
        if worker is not None:
            worker.deleteLater()
        self._text_analysis_snapshot_worker = None
        self._refresh_query_button_state()
        self._refresh_run_button_state()

    def _on_snapshot_progress(self, request_id: int, desc: str, current: int, total: int) -> None:
        if request_id != self._text_analysis_snapshot_request_id:
            return
        self._set_progress(desc, current, total)

    def _on_snapshot_finished(self, request_id: int, cache_paths: Dict[str, str], failures: List[str]) -> None:
        if request_id != self._text_analysis_snapshot_request_id:
            return

        self._preview_json_cache.update({str(key): str(path) for key, path in cache_paths.items() if key and path})
        label_rows = self._build_label_rows_from_json_rows(self._text_analysis_snapshot_json_rows)
        if self._text_analysis_stop_requested:
            self._on_snapshot_cancelled(request_id, cache_paths, failures)
            return

        self.current_label_rows = label_rows
        self._text_analysis_query_ready = True
        self._text_analysis_stop_requested = False
        self._refresh_special_char_label_options()
        self.center_panel.set_books(self.current_book_rows)
        self.center_panel.set_pages(self.current_page_rows, results_only=False)
        self._refresh_dashboard()
        self._finish_snapshot_loading(request_id)

        if self.current_page_rows:
            self._select_first_row_after_refresh(prefer_result=True)
        else:
            self.right_panel.clear_preview()

        snapshot_count = len([key for key in cache_paths.keys() if str(key).strip()])
        expected_count = len(self._text_analysis_snapshot_json_rows)
        if snapshot_count:
            self._set_recent_log(f"JSON 스냅샷 준비 완료: {snapshot_count}/{expected_count} 페이지")
        else:
            self._set_recent_log("JSON 스냅샷 준비 실패: 다시 조회해 주세요.")

        if failures:
            preview = ", ".join(failures[:3])
            suffix = "" if len(failures) <= 3 else " ..."
            self._set_recent_log(f"JSON 스냅샷 로드 실패 {len(failures)}건: {preview}{suffix}")

    def _on_snapshot_cancelled(self, request_id: int, cache_paths: Dict[str, str], failures: List[str]) -> None:
        if request_id != self._text_analysis_snapshot_request_id:
            return

        self._preview_json_cache.update({str(key): str(path) for key, path in cache_paths.items() if key and path})
        self._text_analysis_query_ready = False
        self._text_analysis_stop_requested = False
        self._finish_snapshot_loading(request_id)
        self._set_recent_log("JSON 스냅샷 로드를 중지했습니다.")

        if failures:
            preview = ", ".join(failures[:3])
            suffix = "" if len(failures) <= 3 else " ..."
            self._set_recent_log(f"JSON 스냅샷 로드 실패 {len(failures)}건: {preview}{suffix}")

    def _on_snapshot_failed(self, request_id: int, traceback_text: str) -> None:
        if request_id != self._text_analysis_snapshot_request_id:
            return

        self._text_analysis_query_ready = False
        self._text_analysis_stop_requested = False
        self._finish_snapshot_loading(request_id)
        self._set_recent_log("JSON 스냅샷 준비 실패: 다시 조회해 주세요.")
        QMessageBox.warning(self, "JSON 스냅샷 실패", traceback_text)
