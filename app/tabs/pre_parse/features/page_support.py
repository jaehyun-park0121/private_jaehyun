from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from PyQt5.QtWidgets import QMessageBox

from app.common.shared_status_bar import format_progress_status
from app.tabs.pre_parse.features.base_state import is_error_base_state
from app.tabs.pre_parse.features.s3.s3_loader import S3Loader


class PreParsePageSupportMixin:
    def _reset_to_empty_state(self) -> None:
        self.left_panel.set_books([])
        self.center_panel.set_books([])
        self.center_panel.set_pages([])
        self.right_panel.image_viewer.set_image("")
        self.right_panel.image_viewer.set_bboxes([])
        self.current_issues = []
        self._set_current_s3_pages([])
        self._page_rows_for_stats = []
        self._label_rows = []
        self._update_stats_from_rows([])
        self._set_pre_parse_query_state(ready=False, queried_books=set())

    def _refresh_books_from_s3(self, show_message: bool) -> None:
        project = self.config.get("project", {})
        aws = self.config.get("aws", {})
        s3_path = str(project.get("s3_path", "")).strip()
        if not s3_path:
            if show_message:
                QMessageBox.information(self, "S3 경로 필요", "먼저 설정에서 S3 경로를 입력해주세요.")
            self._reset_to_empty_state()
            return
        if not str(aws.get("access_key", "")).strip() or not str(aws.get("secret_key", "")).strip():
            if show_message:
                QMessageBox.warning(self, "S3 연결 실패", "설정에서 Access Key와 Secret Key를 먼저 입력해주세요.")
            self._reset_to_empty_state()
            return

        try:
            bucket, prefix = S3Loader.parse_s3_path(s3_path)
            loader = S3Loader(aws)
            scanned = loader.scan_project(bucket, prefix)
        except Exception as exc:
            if show_message:
                QMessageBox.warning(self, "S3 연결 실패", str(exc))
            self._reset_to_empty_state()
            return

        png_extensions = {".png", ".jpg", ".jpeg"}
        books_by_id = {}
        for row in scanned:
            book_id = str(row.get("book_id", "unknown"))
            page_no = str(row.get("page_no", ""))
            if Path(page_no).suffix.lower() in png_extensions:
                books_by_id.setdefault(book_id, 0)
                books_by_id[book_id] += 1

        book_rows = [
            {"book_id": book_id, "total_pages": total_pages, "error_pages": 0, "total_issues": 0}
            for book_id, total_pages in sorted(books_by_id.items())
        ]
        page_rows = []
        logical_pages = {}
        for item in scanned:
            book_id = str(item.get("book_id", "unknown"))
            page_no = str(item.get("page_no", ""))
            page_key = f"{book_id}:{page_no}"
            issue_count = int(item.get("issue_count", 0))

            base_name = page_no.rsplit(".", 1)[0]
            if base_name.startswith(f"{book_id}_"):
                base_name_clean = base_name[len(book_id) + 1 :]
            else:
                base_name_clean = base_name
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

        for info in logical_pages.values():
            issue_count = int(info.get("issue_count", 0))
            page_rows.append(
                {
                    "page_no": info["page_no"],
                    "book_id": info["book_id"],
                    "file_name": info["file_name"],
                    "status": info.get("status", "PENDING"),
                    "issue_count": issue_count,
                    "box_count": issue_count,
                    "failed_checks": [],
                    "error_detail": "",
                }
            )

        self._set_current_s3_pages(scanned)
        self._json_payload_cache.clear()
        self._pre_parse_snapshot_request_id += 1
        self._pre_parse_snapshot_loading = False
        self._pre_parse_snapshot_payloads = {}
        self._pre_parse_snapshot_failed_pages = []
        self._pre_parse_snapshot_page_cache_keys = {}
        self._pre_parse_snapshot_json_rows = {}
        self._pre_parse_snapshot_worker = None
        self.left_panel.book_list.setEnabled(True)
        self.left_panel.select_all_books_checkbox.setEnabled(True)
        self.left_panel.set_books(book_rows)
        self.center_panel.set_books(book_rows)
        self._label_rows = []
        self.right_panel.image_viewer.set_image("")
        self.right_panel.image_viewer.set_bboxes([])
        self.center_panel.set_pages([])
        self.current_issues = []
        self._page_rows_for_stats = []
        self._update_stats_from_rows([])
        self._set_pre_parse_query_state(ready=False, queried_books=set())

        if show_message:
            QMessageBox.information(
                self,
                "S3 갱신 완료",
                f"S3 데이터를 다시 불러왔습니다.\n도서 {len(book_rows)}권 / 파일 {len(page_rows)}개",
            )
        self._set_recent_log(f"S3 갱신 완료: 도서 {len(book_rows)}권 / 파일 {len(page_rows)}개")

    def _refresh_s3_rows_for_query(self, *, selected_books: set[str], all_books_selected: bool) -> bool:
        project = self.config.get("project", {})
        aws = self.config.get("aws", {})
        s3_path = str(project.get("s3_path", "")).strip()
        if not s3_path:
            QMessageBox.information(self, "S3 설정 필요", "프로젝트 설정에서 S3 경로를 먼저 입력해 주세요.")
            return False
        if not str(aws.get("access_key", "")).strip() or not str(aws.get("secret_key", "")).strip():
            QMessageBox.warning(self, "S3 설정 필요", "프로젝트 설정에서 AWS Access Key와 Secret Key를 먼저 입력해 주세요.")
            return False

        try:
            bucket, prefix = S3Loader.parse_s3_path(s3_path)
            loader = S3Loader(aws)
            scanned = loader.scan_project(bucket, prefix)
        except Exception as exc:
            QMessageBox.warning(self, "S3 조회 실패", str(exc))
            return False

        png_extensions = {".png", ".jpg", ".jpeg"}
        books_by_id = {}
        for row in scanned:
            book_id = str(row.get("book_id", "unknown"))
            page_no = str(row.get("page_no", ""))
            if Path(page_no).suffix.lower() in png_extensions:
                books_by_id.setdefault(book_id, 0)
                books_by_id[book_id] += 1

        book_rows = [
            {"book_id": book_id, "total_pages": total_pages, "error_pages": 0, "total_issues": 0}
            for book_id, total_pages in sorted(books_by_id.items())
        ]

        self._set_current_s3_pages(scanned)
        self._json_payload_cache.clear()
        self._pre_parse_snapshot_request_id += 1
        self._pre_parse_snapshot_loading = False
        self._pre_parse_snapshot_payloads = {}
        self._pre_parse_snapshot_failed_pages = []
        self._pre_parse_snapshot_page_cache_keys = {}
        self._pre_parse_snapshot_json_rows = {}
        self._pre_parse_snapshot_worker = None
        self.left_panel.set_books(
            book_rows,
            selected_book_ids=None if all_books_selected else selected_books,
        )
        self.center_panel.set_books(book_rows)
        self._set_pre_parse_query_state(ready=False, queried_books=set())
        return True

    def _set_recent_log(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return
        if self._status_callback is not None:
            self._status_callback(text)

    def _set_progress(self, desc: str, current: int, total: int) -> None:
        self._set_recent_log(format_progress_status(desc, current, total))

    def _extract_page_no(self, page_name: str) -> int:
        matched = re.search(r"(\d+)(?!.*\d)", page_name)
        if matched:
            return int(matched.group(1))
        return 1

    def _calc_stats(self, rows: List[dict], label_rows: Optional[List[dict]] = None) -> dict:
        total_pages = len(rows)
        error_pages = 0
        total_issues = 0
        total_labels = 0
        error_labels = 0
        books = set()
        for row in rows:
            page_key = str(row.get("page_no", ""))
            if ":" in page_key:
                books.add(page_key.split(":", 1)[0])
            issue_count = int(row.get("issue_count", 0))
            status = str(row.get("status", ""))
            if issue_count > 0 and status != "NORMAL":
                error_pages += 1
                total_issues += issue_count

        for row in label_rows or []:
            try:
                shape_index = int(row.get("shape_index", -1))
            except (TypeError, ValueError):
                shape_index = -1
            if shape_index < 0:
                continue
            total_labels += 1
            if is_error_base_state(row.get("base_state")) or str(row.get("error_detail", "")).strip():
                error_labels += 1

        total_books = len(books)
        pass_rate = ((total_pages - error_pages) / total_pages * 100.0) if total_pages else 0.0
        avg_issue_pct = (error_pages / total_pages * 100.0) if total_pages else 0.0
        return {
            "도서 수": total_books,
            "페이지 수": total_pages,
            "오류 페이지": error_pages,
            "총 오류": total_issues,
            "통과율": pass_rate,
            "평균 오류율": avg_issue_pct,
        }

    def _filter_issues_by_books(self, issues: List[dict], selected_books: set) -> List[dict]:
        if not selected_books:
            return []
        filtered: List[dict] = []
        for issue in issues:
            issue_book = str(issue.get("book_id", ""))
            if issue_book in selected_books:
                filtered.append(issue)
        return filtered
