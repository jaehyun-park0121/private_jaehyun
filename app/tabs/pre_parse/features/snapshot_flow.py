from __future__ import annotations

import copy
from typing import Dict, List, Set

from PyQt5.QtWidgets import QApplication, QMessageBox

from app.common.config.parallel_settings import resolve_parallel_workers
from app.tabs.pre_parse.features.json_snapshot_worker import PreParseJsonSnapshotWorker


class PreParseSnapshotFlowMixin:
    def _on_query_clicked(self) -> None:
        if self._pre_parse_snapshot_loading:
            if not self._request_snapshot_stop():
                self._set_recent_log("JSON 스냅샷 중지 요청 실패")
            return

        if self._pre_parse_is_running:
            QMessageBox.information(self, "실행 중", "검사 실행 중에는 조회를 다시 시작할 수 없습니다.")
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

        if not self.current_s3_pages:
            QMessageBox.information(self, "안내", "먼저 S3 도서 목록을 불러와 주세요.")
            return

        self._run_query_mode(selected_books)

    def _run_query_mode(self, selected_books: set[str]) -> None:
        page_rows = self._build_page_rows_for_books(selected_books)
        placeholder_rows = self._build_placeholder_rows_for_pages(page_rows)
        self.center_panel.set_books([{"book_id": book_id} for book_id in sorted(selected_books)])

        self.last_page_issues = []
        self.current_issues = []
        self._label_rows = []
        self.center_panel.set_error_only_mode(False)
        self.right_panel.image_viewer.set_image("")
        self.right_panel.image_viewer.set_bboxes([])
        self.center_panel.set_pages([])

        rows_by_book: Dict[str, List[dict]] = {}
        book_order: List[str] = []
        for row in placeholder_rows:
            book_id = str(row.get("book_id", "")).strip()
            if book_id not in rows_by_book:
                rows_by_book[book_id] = []
                book_order.append(book_id)
            rows_by_book[book_id].append(dict(row))

        visible_rows: List[dict] = []
        total_books = len(book_order)
        for index, book_id in enumerate(book_order, start=1):
            visible_rows.extend(rows_by_book.get(book_id, []))
            self._label_rows = list(visible_rows)
            self.center_panel.set_pages(self._label_rows)
            self._set_progress("조회 대상 도서 준비", index, max(total_books, 1))
            QApplication.processEvents()

        self._page_rows_for_stats = [
            {
                "page_no": row.get("page_no", ""),
                "issue_count": int(row.get("issue_count", 0)),
                "status": row.get("status", ""),
            }
            for row in page_rows
        ]
        self._update_stats_from_rows(self._page_rows_for_stats)
        self._set_pre_parse_query_state(ready=False, queried_books=selected_books)
        self._set_recent_log(
            f"조회 완료: 도서 {len(selected_books)}권 / 페이지 {len(page_rows)}건 / JSON 스냅샷 준비 시작"
        )
        self._begin_snapshot_loading(selected_books=selected_books, page_rows=page_rows)

    def _begin_snapshot_loading(self, *, selected_books: set[str], page_rows: List[dict]) -> None:
        self._pre_parse_snapshot_request_id += 1
        request_id = self._pre_parse_snapshot_request_id
        json_rows = self._json_rows_for_page_rows(page_rows)

        self._pre_parse_snapshot_payloads = {}
        self._pre_parse_snapshot_failed_pages = []
        self._pre_parse_snapshot_page_cache_keys = {}
        self._pre_parse_snapshot_json_rows = {}

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
            cache_key = self._json_cache_key(json_row)
            if not cache_key:
                continue
            page_tuple = (str(book_id).strip(), str(page_token).strip())
            self._pre_parse_snapshot_json_rows[page_tuple] = dict(json_row)
            self._pre_parse_snapshot_page_cache_keys[page_tuple] = cache_key

        if not json_rows:
            self._pre_parse_snapshot_loading = False
            self.left_panel.book_list.setEnabled(True)
            self.left_panel.select_all_books_checkbox.setEnabled(True)
            self._set_pre_parse_query_state(ready=True, queried_books=selected_books)
            self._set_recent_log("JSON 스냅샷 대상이 없어 바로 실행 가능 상태로 전환했습니다.")
            return

        self._pre_parse_snapshot_loading = True
        self.left_panel.book_list.setEnabled(False)
        self.left_panel.select_all_books_checkbox.setEnabled(False)
        self._refresh_pre_parse_action_buttons()

        worker = PreParseJsonSnapshotWorker(
            aws_config=copy.deepcopy(self.config.get("aws", {})),
            json_rows=json_rows,
            cache_dir=str(self._json_cache_dir),
            max_workers=resolve_parallel_workers(
                self.config,
                total_tasks=len(json_rows),
            ),
        )
        self._pre_parse_snapshot_worker = worker
        worker.progress.connect(
            lambda desc, current, total, rid=request_id: self._on_snapshot_progress(rid, desc, current, total)
        )
        worker.finished_ok.connect(
            lambda cache_paths, failures, rid=request_id, books=set(selected_books): self._on_snapshot_finished(
                rid,
                books,
                cache_paths,
                failures,
            )
        )
        worker.cancelled.connect(
            lambda cache_paths, failures, rid=request_id, books=set(selected_books): self._on_snapshot_cancelled(
                rid,
                books,
                cache_paths,
                failures,
            )
        )
        worker.failed.connect(lambda message, rid=request_id: self._on_snapshot_failed(rid, message))
        worker.finished.connect(lambda rid=request_id: self._on_snapshot_worker_finished(rid))
        worker.start()

    def _on_snapshot_progress(self, request_id: int, desc: str, current: int, total: int) -> None:
        if request_id != self._pre_parse_snapshot_request_id:
            return
        self._set_progress(desc, current, total)

    def _on_snapshot_finished(
        self,
        request_id: int,
        selected_books: set[str],
        cache_paths: Dict[str, str],
        failures: List[str],
    ) -> None:
        if request_id != self._pre_parse_snapshot_request_id:
            return

        self._pre_parse_snapshot_loading = False
        self.left_panel.book_list.setEnabled(True)
        self.left_panel.select_all_books_checkbox.setEnabled(True)
        self._pre_parse_snapshot_failed_pages = list(failures or [])
        self._pre_parse_snapshot_payloads = {}
        for cache_key, path in dict(cache_paths or {}).items():
            if str(cache_key).strip() and str(path).strip():
                self._preview_json_cache[str(cache_key)] = str(path)

        snapshot_count = len([key for key in dict(cache_paths or {}).keys() if str(key).strip()])
        expected_count = len(self._pre_parse_snapshot_page_cache_keys)
        is_ready = bool(snapshot_count) or expected_count == 0
        self._set_pre_parse_query_state(ready=is_ready, queried_books=selected_books)
        if is_ready:
            page_rows = self._build_page_rows_for_books(selected_books)
            self._label_rows = self._build_label_rows_for_pages(page_rows, {}, {})
            self.center_panel.set_pages(self._label_rows)
            self._update_stats_from_rows(self._page_rows_for_stats)
            self._set_recent_log(f"JSON 스냅샷 준비 완료: {snapshot_count}/{expected_count} 페이지")
        else:
            self._set_recent_log("JSON 스냅샷 준비 실패: 다시 조회해주세요.")

        if self._pre_parse_snapshot_failed_pages:
            failed_preview = ", ".join(self._pre_parse_snapshot_failed_pages[:3])
            suffix = "" if len(self._pre_parse_snapshot_failed_pages) <= 3 else " ..."
            self._set_recent_log(
                f"JSON 스냅샷 제외 페이지 {len(self._pre_parse_snapshot_failed_pages)}건: {failed_preview}{suffix}"
            )

        proxy = self.center_panel.page_table.model()
        if proxy is not None and proxy.rowCount() > 0:
            self.center_panel.page_table.selectRow(0)
            self._show_pre_parse_preview_for_row(0)
        else:
            self.right_panel.image_viewer.set_image("")
            self.right_panel.image_viewer.set_bboxes([])

    def _on_snapshot_failed(self, request_id: int, message: str) -> None:
        if request_id != self._pre_parse_snapshot_request_id:
            return
        self._pre_parse_snapshot_loading = False
        self.left_panel.book_list.setEnabled(True)
        self.left_panel.select_all_books_checkbox.setEnabled(True)
        self._pre_parse_snapshot_payloads = {}
        self._pre_parse_snapshot_failed_pages = []
        self._set_pre_parse_query_state(ready=False)
        QMessageBox.warning(self, "JSON 스냅샷 실패", str(message).strip() or "알 수 없는 오류")

    def _on_snapshot_worker_finished(self, request_id: int) -> None:
        if request_id != self._pre_parse_snapshot_request_id:
            return
        self._pre_parse_snapshot_worker = None

    def _on_snapshot_cancelled(
        self,
        request_id: int,
        selected_books: Set[str],
        cache_paths: Dict[str, str],
        failures: List[str],
    ) -> None:
        if request_id != self._pre_parse_snapshot_request_id:
            return

        self._pre_parse_snapshot_loading = False
        self.left_panel.book_list.setEnabled(True)
        self.left_panel.select_all_books_checkbox.setEnabled(True)
        self._pre_parse_snapshot_failed_pages = list(failures or [])
        self._pre_parse_snapshot_payloads = {}
        for cache_key, path in dict(cache_paths or {}).items():
            if str(cache_key).strip() and str(path).strip():
                self._preview_json_cache[str(cache_key)] = str(path)

        self._set_pre_parse_query_state(ready=False, queried_books=set(selected_books))
        self._set_recent_log("JSON 스냅샷 로드를 중지했습니다.")
        if self._pre_parse_snapshot_failed_pages:
            failed_preview = ", ".join(self._pre_parse_snapshot_failed_pages[:3])
            suffix = "" if len(self._pre_parse_snapshot_failed_pages) <= 3 else " ..."
            self._set_recent_log(
                f"JSON 스냅샷 제외 페이지 {len(self._pre_parse_snapshot_failed_pages)}건: {failed_preview}{suffix}"
            )

    def _request_snapshot_stop(self) -> bool:
        worker = self._pre_parse_snapshot_worker
        if worker is None:
            return False
        try:
            worker.request_stop()
            self._set_recent_log("JSON 스냅샷 중지 요청됨: 진행 중인 다운로드 정리 후 멈춥니다.")
            return True
        except Exception as exc:
            self._set_recent_log(f"JSON 스냅샷 중지 요청 실패: {exc}")
            return False
