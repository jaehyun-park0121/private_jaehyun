from __future__ import annotations

import copy
from typing import Dict, List, Tuple

from PyQt5.QtWidgets import QMessageBox

from app.common.config.parallel_settings import resolve_parallel_workers
from app.tabs.pre_parse.features.base_state import BASE_STATE_ERROR, is_error_base_state
from app.tabs.pre_parse.features.check_run_worker import PreParseCheckRunWorker
from app.tabs.pre_parse.plugin_system.context import PageContext


class PreParseRunFlowMixin:
    def _begin_check_run_worker(
        self,
        *,
        selected_books: set[str],
        total_pages: int,
        page_tasks: List[dict],
        skipped_snapshot_pages: List[str],
        selected_check_ids: List[str],
        selected_options: Dict,
    ) -> None:
        self._pre_parse_run_request_id += 1
        request_id = self._pre_parse_run_request_id

        worker = PreParseCheckRunWorker(
            plugin_dir=str(self.project_root / "app" / "tabs" / "pre_parse" / "plugins"),
            project_id=str(self.config.get("project", {}).get("id", "demo")),
            selected_plugin_ids=list(selected_check_ids),
            selected_options=copy.deepcopy(selected_options),
            page_tasks=page_tasks,
            max_workers=resolve_parallel_workers(
                self.config,
                total_tasks=len(page_tasks),
            ),
        )
        self._pre_parse_run_worker = worker
        worker.progress.connect(
            lambda desc, current, total, rid=request_id: self._on_check_run_progress(rid, desc, current, total)
        )
        worker.bundle_ready.connect(
            lambda bundle, rid=request_id: self._on_check_run_bundle_ready(rid, bundle)
        )
        worker.finished_ok.connect(
            lambda bundles, failures, rid=request_id, books=set(selected_books), total=total_pages, skipped=list(skipped_snapshot_pages): self._on_check_run_finished(
                rid,
                books,
                total,
                skipped,
                bundles,
                failures,
            )
        )
        worker.cancelled.connect(
            lambda bundles, failures, rid=request_id, books=set(selected_books), total=total_pages, skipped=list(skipped_snapshot_pages): self._on_check_run_cancelled(
                rid,
                books,
                total,
                skipped,
                bundles,
                failures,
            )
        )
        worker.failed.connect(lambda message, rid=request_id: self._on_check_run_failed(rid, message))
        worker.finished.connect(lambda rid=request_id: self._on_check_run_worker_finished(rid))
        worker.start()

    def _on_check_run_progress(self, request_id: int, desc: str, current: int, total: int) -> None:
        if request_id != self._pre_parse_run_request_id:
            return
        self._set_progress(desc, current, total)

    def _on_check_run_bundle_ready(self, request_id: int, bundle: dict) -> None:
        if request_id != self._pre_parse_run_request_id:
            return
        if not isinstance(bundle, dict):
            return

        page_key = str(bundle.get("page_key", "")).strip()
        book_id = str(bundle.get("book_id", "")).strip()
        if not page_key or not book_id or page_key in self._pre_parse_live_bundles:
            return

        self._pre_parse_live_bundles[page_key] = bundle
        self._pre_parse_live_book_completed[book_id] = self._pre_parse_live_book_completed.get(book_id, 0) + 1
        if self._pre_parse_live_book_completed.get(book_id, 0) >= self._pre_parse_live_book_totals.get(book_id, 0):
            if book_id not in self._pre_parse_live_displayed_books:
                self._pre_parse_live_displayed_books.add(book_id)
                self._rebuild_live_run_rows()
                completed_books = len(self._pre_parse_live_displayed_books)
                total_books = len(self._pre_parse_live_book_totals)
                self._set_recent_log(
                    f"검사 결과 반영: {book_id} 완료 ({completed_books}/{max(total_books, 1)} 도서)"
                )

    def _on_check_run_finished(
        self,
        request_id: int,
        selected_books: set[str],
        total_pages: int,
        skipped_snapshot_pages: List[str],
        bundles: List[dict],
        failures: List[str],
    ) -> None:
        if request_id != self._pre_parse_run_request_id:
            return
        self._handle_check_run_complete(
            selected_books=selected_books,
            total_pages=total_pages,
            skipped_snapshot_pages=skipped_snapshot_pages,
            bundles=list(bundles or []),
            failures=list(failures or []),
            cancelled=False,
        )

    def _on_check_run_cancelled(
        self,
        request_id: int,
        selected_books: set[str],
        total_pages: int,
        skipped_snapshot_pages: List[str],
        bundles: List[dict],
        failures: List[str],
    ) -> None:
        if request_id != self._pre_parse_run_request_id:
            return
        self._handle_check_run_complete(
            selected_books=selected_books,
            total_pages=total_pages,
            skipped_snapshot_pages=skipped_snapshot_pages,
            bundles=list(bundles or []),
            failures=list(failures or []),
            cancelled=True,
        )

    def _on_check_run_failed(self, request_id: int, message: str) -> None:
        if request_id != self._pre_parse_run_request_id:
            return
        self._pre_parse_is_running = False
        self._pre_parse_stop_requested = False
        self._refresh_pre_parse_action_buttons()
        QMessageBox.warning(self, "검사 실행 실패", str(message).strip() or "알 수 없는 오류")

    def _on_check_run_worker_finished(self, request_id: int) -> None:
        if request_id != self._pre_parse_run_request_id:
            return
        self._pre_parse_run_worker = None

    def _request_run_stop(self) -> bool:
        worker = self._pre_parse_run_worker
        if worker is None:
            return False
        try:
            worker.request_stop()
            self._set_recent_log("검사 중지 요청됨: 진행 중인 페이지 작업 정리 후 멈춥니다.")
            return True
        except Exception as exc:
            self._set_recent_log(f"검사 중지 요청 실패: {exc}")
            return False

    def _build_check_run_tasks(self, page_rows_for_run: List[dict]) -> Tuple[List[dict], List[str]]:
        page_tasks: List[dict] = []
        skipped_snapshot_pages: List[str] = []

        for order_index, row in enumerate(page_rows_for_run):
            page_key = str(row.get("page_no", ""))
            if ":" in page_key:
                book_id, page_token = page_key.split(":", 1)
            else:
                book_id = str(row.get("book_id", "unknown"))
                page_token = page_key

            page_payload = self._load_snapshot_page_json_payload(book_id, page_token)
            if not page_payload:
                skipped_snapshot_pages.append(f"{book_id}:{page_token}")
                continue

            file_name = str(row.get("file_name", "")).strip()
            if not file_name:
                file_name = str(page_token).rsplit(".", 1)[0]
                if file_name.startswith(f"{book_id}_"):
                    file_name = file_name[len(book_id) + 1 :]

            page_tasks.append(
                {
                    "order_index": order_index,
                    "page_key": page_key,
                    "book_id": book_id,
                    "page_token": page_token,
                    "page_no": self._extract_page_no(page_token),
                    "file_name": file_name,
                    "payload": page_payload,
                }
            )

        return page_tasks, skipped_snapshot_pages

    def _materialize_check_run_outputs(
        self,
        bundles: List[dict],
    ) -> Tuple[Dict[str, Dict], List[dict], List[dict], List[dict]]:
        page_results: Dict[str, Dict] = {}
        page_rows: List[dict] = []
        label_rows: List[dict] = []
        all_issues: List[dict] = []

        for bundle in sorted(bundles, key=lambda item: int(item.get("order_index", 0) or 0)):
            page_key = str(bundle.get("page_key", ""))
            book_id = str(bundle.get("book_id", ""))
            file_name = str(bundle.get("file_name", ""))
            page_payload = bundle.get("payload", {})
            checks = bundle.get("checks", {})
            if not page_key or not isinstance(page_payload, dict) or not isinstance(checks, dict):
                continue

            page_results[page_key] = checks
            issue_count = sum(result.issue_count for result in checks.values())
            page_failed = any(str(result.status).upper() == "FAIL" for result in checks.values())
            failed = [pid for pid, result in checks.items() if str(result.status).upper() == "FAIL"]

            descriptions: List[str] = []
            page_issue_rows: List[dict] = []
            extra_issue_rows: List[dict] = []
            for result in checks.values():
                if result.debug_message:
                    detail_text = self._issue_detail_text(result.check_id, result.debug_message)
                    if detail_text and detail_text not in descriptions:
                        descriptions.append(detail_text)
                for issue in result.issues:
                    detail_text = self._issue_detail_text(result.check_id, issue.error_message)
                    if detail_text and detail_text not in descriptions:
                        descriptions.append(detail_text)

                    shape_index = int(issue.shape_index)
                    shape_info = self._shape_snapshot_from_payload(page_payload, shape_index)
                    label = str(shape_info["label"]).strip().upper()
                    color = self._label_color_map.get(label, "#9ca3af")
                    page_issue_rows.append(
                        {
                            "check_id": result.check_id,
                            "label": label,
                            "shape_index": shape_index,
                            "bbox": shape_info["bbox"],
                            "error_message": issue.error_message,
                            "message": issue.error_message,
                            "description": self._plugin_description(result.check_id),
                            "value": shape_info["value"],
                            "error_type": getattr(issue, "error_type", "") or "",
                            "page_no": page_key,
                            "book_id": book_id,
                            "color": color,
                        }
                    )
                    if shape_index >= 0:
                        continue
                    extra_issue_rows.append(
                        {
                            "row_key": f"{page_key}:issue:{len(label_rows) + len(extra_issue_rows)}:{result.check_id}",
                            "page_no": page_key,
                            "book_id": book_id,
                            "page": file_name or str(page_key),
                            "shape_index": -1,
                            "label_id": "",
                            "label": "",
                            "value": "",
                            "error_detail": self._issue_detail_text(result.check_id, issue.error_message),
                            "error_type": str(getattr(issue, "error_type", "") or ""),
                            "base_state": BASE_STATE_ERROR,
                            "is_problem": False,
                            "problem_reason": "",
                        }
                    )

                if result.debug_message and not result.issues:
                    page_issue_rows.append(
                        {
                            "check_id": result.check_id,
                            "label": "",
                            "shape_index": -1,
                            "bbox": [0, 0, 0, 0],
                            "error_message": result.debug_message,
                            "message": result.debug_message,
                            "description": self._plugin_description(result.check_id),
                            "value": "",
                            "error_type": "[플러그인 실행 오류]",
                            "page_no": page_key,
                            "book_id": book_id,
                            "color": "#9ca3af",
                        }
                    )
                    extra_issue_rows.append(
                        {
                            "row_key": f"{page_key}:issue:{len(label_rows) + len(extra_issue_rows)}:{result.check_id}",
                            "page_no": page_key,
                            "book_id": book_id,
                            "page": file_name or str(page_key),
                            "shape_index": -1,
                            "label_id": "",
                            "label": "",
                            "value": "",
                            "error_detail": self._issue_detail_text(result.check_id, result.debug_message),
                            "error_type": "[플러그인 실행 오류]",
                            "base_state": BASE_STATE_ERROR,
                            "is_problem": False,
                            "problem_reason": "",
                        }
                    )

            page_rows.append(
                {
                    "page_no": page_key,
                    "book_id": book_id,
                    "file_name": file_name,
                    "status": "FAIL" if page_failed else "PASS",
                    "issue_count": issue_count,
                    "box_count": issue_count,
                    "failed_checks": failed,
                    "error_detail": " / ".join(descriptions),
                }
            )

            page_issue_map = self._build_issue_detail_map(page_issue_rows)
            page_issue_type_map = self._build_issue_type_map(page_issue_rows)
            page_label_rows = self._build_label_rows_for_payload(
                page_key=page_key,
                book_id=book_id,
                page_name=file_name,
                payload=page_payload,
                issue_detail_map=page_issue_map,
                issue_type_map=page_issue_type_map,
            )
            if extra_issue_rows:
                page_label_rows.extend(extra_issue_rows)

            all_issues.extend(page_issue_rows)
            label_rows.extend(page_label_rows)

        return page_results, page_rows, label_rows, all_issues

    def _rebuild_live_run_rows(self) -> None:
        visible_bundles = [
            bundle
            for bundle in self._pre_parse_live_bundles.values()
            if str(bundle.get("book_id", "")).strip() in self._pre_parse_live_displayed_books
        ]
        if not visible_bundles:
            self.last_page_issues = []
            self.current_issues = []
            self._label_rows = []
            self.center_panel.set_pages([])
            self.right_panel.image_viewer.set_bboxes([])
            return

        _page_results, _page_rows, label_rows, all_issues = self._materialize_check_run_outputs(visible_bundles)
        self.last_page_issues = all_issues
        self.current_issues = all_issues
        self._label_rows = label_rows
        self.center_panel.set_pages(self._label_rows)

        has_error_rows = any(is_error_base_state(row.get("base_state")) for row in self._label_rows)
        self.right_panel.image_viewer.set_bboxes(all_issues if has_error_rows else [])

    def _handle_check_run_complete(
        self,
        *,
        selected_books: set[str],
        total_pages: int,
        skipped_snapshot_pages: List[str],
        bundles: List[dict],
        failures: List[str],
        cancelled: bool,
    ) -> None:
        self._pre_parse_is_running = False
        self._pre_parse_stop_requested = False
        self._refresh_pre_parse_action_buttons()
        self._set_pre_parse_query_state(ready=True, queried_books=selected_books)

        completed_pages = len(bundles) + len(skipped_snapshot_pages)
        self._set_progress(
            "페이지 JSON 검사",
            min(completed_pages, total_pages) if cancelled else total_pages,
            total_pages,
        )

        if failures:
            preview = ", ".join(failures[:3])
            suffix = "" if len(failures) <= 3 else " ..."
            self._set_recent_log(f"검사 실행 중 예외 {len(failures)}건 {preview}{suffix}")

        if not bundles:
            self._set_recent_log(
                f"검사 중지: {completed_pages}/{total_pages} 페이지 처리" if cancelled else "검사 완료: 표시할 결과가 없습니다."
            )
            if skipped_snapshot_pages:
                preview = ", ".join(skipped_snapshot_pages[:3])
                suffix = "" if len(skipped_snapshot_pages) <= 3 else " ..."
                self._set_recent_log(
                    f"검사 제외 페이지 {len(skipped_snapshot_pages)}건 {preview}{suffix}"
                )
            return

        page_results, page_rows, label_rows, all_issues = self._materialize_check_run_outputs(bundles)
        self.last_page_issues = all_issues
        self.current_issues = all_issues
        self._label_rows = label_rows
        self.center_panel.set_error_only_mode(True)
        self.right_panel.image_viewer.set_image("")
        self.center_panel.set_pages(self._label_rows)

        has_error_rows = any(is_error_base_state(row.get("base_state")) for row in self._label_rows)
        self.right_panel.image_viewer.set_bboxes(all_issues if has_error_rows else [])

        stats = self.aggregator.aggregate(page_results, total_books=len(selected_books))
        try:
            self.exporter.export(page_results, page_rows, all_issues, stats)
        except Exception as exc:
            self._set_recent_log(f"결과 파일 저장 실패: {exc}")

        self.top_bar.update_stats(
            total_books=stats.total_books,
            total_pages=stats.total_pages,
            error_pages=stats.error_pages,
            total_issues=stats.total_issues,
            pass_rate=stats.pass_rate,
        )
        self._page_rows_for_stats = [
            {
                "page_no": row.get("page_no", ""),
                "issue_count": int(row.get("issue_count", 0)),
                "status": row.get("status", ""),
            }
            for row in page_rows
        ]
        self._update_stats_from_rows(self._page_rows_for_stats)

        if cancelled:
            self._set_recent_log(f"검사 중지: {completed_pages}/{total_pages} 페이지 처리")
        else:
            self._set_recent_log(
                f"검사 결과 표시 완료: 오류 {sum(1 for row in self._label_rows if str(row.get('error_detail', '')).strip())}건"
            )

        if skipped_snapshot_pages:
            preview = ", ".join(skipped_snapshot_pages[:3])
            suffix = "" if len(skipped_snapshot_pages) <= 3 else " ..."
            self._set_recent_log(
                f"검사 제외 페이지 {len(skipped_snapshot_pages)}건 {preview}{suffix}"
            )

    def _on_pre_parse_run_clicked(self) -> None:
        if self._pre_parse_is_running:
            if not self._request_run_stop():
                self._set_recent_log("검사 중지 요청 실패")
            return
        self._run_checks()

    def _run_checks(self) -> None:
        if self._pre_parse_is_running:
            return
        if self._pre_parse_snapshot_loading:
            QMessageBox.information(
                self,
                "JSON 스냅샷 준비 중",
                "조회 시점 JSON 스냅샷을 아직 준비 중입니다.\n잠시 후 다시 실행해주세요.",
            )
            return

        selected_checks = self.left_panel.selected_check_ids()
        if not self._pre_parse_query_ready:
            QMessageBox.information(
                self,
                "조회 필요",
                "도서 선택이 바뀌었거나 JSON 스냅샷 준비가 아직 끝나지 않았습니다.\n먼저 [조회]를 다시 실행해주세요.",
            )
            return

        selected_books = set(self._pre_parse_queried_book_ids)
        if not selected_books:
            QMessageBox.information(self, "안내", "검사할 도서를 1권 이상 선택해주세요.")
            return
        if not self.current_s3_pages:
            QMessageBox.information(self, "안내", "먼저 S3 도서 목록을 불러와주세요.")
            return
        if not selected_checks:
            QMessageBox.information(self, "안내", "검사 항목을 1개 이상 선택해주세요.")
            return

        page_rows_for_run = self._build_page_rows_for_books(selected_books)
        total_pages = len(page_rows_for_run)
        if total_pages == 0:
            QMessageBox.information(self, "안내", "선택한 도서에 검사할 페이지가 없습니다.")
            return

        page_tasks, skipped_snapshot_pages = self._build_check_run_tasks(page_rows_for_run)
        if not page_tasks and skipped_snapshot_pages:
            preview = ", ".join(skipped_snapshot_pages[:3])
            suffix = "" if len(skipped_snapshot_pages) <= 3 else " ..."
            self._set_recent_log(
                f"검사 제외 페이지 {len(skipped_snapshot_pages)}건 {preview}{suffix}"
            )
            return

        self._pre_parse_is_running = True
        self._pre_parse_stop_requested = False
        self._refresh_pre_parse_action_buttons()
        self.center_panel.set_error_only_mode(True)
        self.right_panel.image_viewer.set_image("")
        self.right_panel.image_viewer.set_bboxes([])
        self.center_panel.set_pages([])
        self.last_page_issues = []
        self.current_issues = []
        self._label_rows = []
        self._page_rows_for_stats = []
        self._reset_live_run_state()
        for task in page_tasks:
            book_id = str(task.get("book_id", "")).strip()
            if not book_id:
                continue
            self._pre_parse_live_book_totals[book_id] = self._pre_parse_live_book_totals.get(book_id, 0) + 1
        self._set_recent_log(f"검사 시작: 페이지 {len(page_tasks)}건 병렬 실행")

        self._begin_check_run_worker(
            selected_books=selected_books,
            total_pages=total_pages,
            page_tasks=page_tasks,
            skipped_snapshot_pages=skipped_snapshot_pages,
            selected_check_ids=list(selected_checks),
            selected_options=self.left_panel.selected_check_options(),
        )
