from __future__ import annotations

from typing import List

from PyQt5.QtWidgets import QMenu


class PreParseStateUiMixin:
    def _initialize_pre_parse_state(self) -> None:
        self.last_page_issues: List[dict] = []
        self.current_issues: List[dict] = []
        self.current_s3_pages: List[dict] = []
        self._page_rows_for_stats: List[dict] = []
        self._label_rows: List[dict] = []
        self._pre_parse_query_ready = False
        self._pre_parse_queried_book_ids: set[str] = set()
        self._pre_parse_is_running = False
        self._pre_parse_stop_requested = False
        self._pre_parse_snapshot_loading = False
        self._pre_parse_snapshot_request_id = 0
        self._pre_parse_snapshot_worker = None
        self._pre_parse_run_request_id = 0
        self._pre_parse_run_worker = None
        self._pre_parse_snapshot_payloads: dict[str, dict] = {}
        self._pre_parse_snapshot_page_cache_keys: dict[tuple[str, str], str] = {}
        self._pre_parse_snapshot_json_rows: dict[tuple[str, str], dict] = {}
        self._pre_parse_snapshot_failed_pages: list[str] = []

    def _wire_pre_parse_events(self) -> None:
        self.left_panel.run_btn.clicked.connect(self._on_pre_parse_run_clicked)
        self.left_panel.query_btn.clicked.connect(self._on_query_clicked)
        self.center_panel.page_table.clicked.connect(lambda idx: self._on_page_clicked(idx.row(), idx.column()))
        selection_model = self.center_panel.page_table.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(
                lambda current, _previous: self._on_page_clicked(current.row(), current.column())
                if current.isValid()
                else None
            )
        self.center_panel.ui_log_requested.connect(self._set_recent_log)
        self.left_panel.book_list.itemChanged.connect(self._on_pre_parse_book_selection_changed)
        self.left_panel.checks_changed.connect(self._refresh_pre_parse_action_buttons)

    def _problem_menu_style(self) -> str:
        return """
            QMenu {
                background: #ffffff;
                color: #334155;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                background: transparent;
                border-radius: 6px;
                padding: 6px 12px;
                margin: 2px 2px;
            }
            QMenu::item:selected {
                background: #f8fafc;
            }
            QMenu::right-arrow {
                width: 10px;
                height: 10px;
                margin-right: 4px;
            }
            QMenu::separator {
                height: 1px;
                background: #e2e8f0;
                margin: 4px 6px;
            }
        """

    def _configure_problem_menu(self) -> None:
        self.center_panel.problem_check_btn.clicked.connect(self._mark_problem_for_visible_rows)

        reset_menu = QMenu(self)
        reset_menu.setStyleSheet(self._problem_menu_style())
        reset_all = reset_menu.addAction("검수 도서 전체 초기화")
        reset_filtered = reset_menu.addAction("현재 필터 결과 초기화")
        reset_reason_menu = reset_menu.addMenu("특정 problem_reason 항목 초기화")
        reset_reason_menu.setStyleSheet(self._problem_menu_style())
        reset_reason_menu.aboutToShow.connect(
            lambda m=reset_reason_menu: self._rebuild_reset_reason_menu(m)
        )
        reset_all.triggered.connect(self._reset_problem_for_all_rows)
        reset_filtered.triggered.connect(self._reset_problem_for_visible_rows)
        self.center_panel.problem_reset_btn.setMenu(reset_menu)

    def _refresh_dashboard(self) -> None:
        self._update_stats_from_rows(self._page_rows_for_stats)

    def _load_plugins(self) -> None:
        loaded_plugins = self.plugin_loader.load_into_registry(self.registry)
        checks = []
        for plugin in loaded_plugins:
            meta = plugin.metadata()
            source_file = getattr(plugin, "source_file", None)
            display_name = source_file.stem if source_file is not None else meta["plugin_id"]
            options = []
            if hasattr(plugin, "option_schema") and callable(getattr(plugin, "option_schema")):
                try:
                    options = list(plugin.option_schema())  # type: ignore[attr-defined]
                except Exception:
                    options = []
            checks.append(
                {
                    "plugin_id": meta["plugin_id"],
                    "title": display_name,
                    "tag": meta.get("tag", ""),
                    "description": meta.get("description", ""),
                    "options": options,
                }
            )
        import re as _re

        def _prefix_key(t: str) -> str:
            m = _re.match(r"^\[([^\]]+)\]", t)
            return m.group(1).lower() if m else t.lower()

        _TAG_PRIORITY = {"필수": 0, "required": 0, "선택": 1, "optional": 1}
        checks.sort(key=lambda c: (
            _prefix_key(c["title"]),
            _TAG_PRIORITY.get(c["tag"].strip(), 2),
            c["title"].lower(),
        ))
        self.left_panel.set_checks(checks)
        self._refresh_pre_parse_action_buttons()

    def _on_pre_parse_book_selection_changed(self, _item) -> None:
        self._update_stats_from_rows(self._page_rows_for_stats)
        current_selected = set(self.left_panel.selected_book_ids())
        if current_selected != self._pre_parse_queried_book_ids:
            self._set_pre_parse_query_state(ready=False)

    def _set_pre_parse_query_state(
        self,
        *,
        ready: bool,
        queried_books: set[str] | None = None,
    ) -> None:
        self._pre_parse_query_ready = bool(ready)
        if queried_books is not None:
            self._pre_parse_queried_book_ids = set(queried_books)
        self._refresh_pre_parse_action_buttons()

    def _refresh_pre_parse_action_buttons(self) -> None:
        selected_books = bool(self.left_panel.selected_book_ids())
        selected_checks = bool(self.left_panel.selected_check_ids())
        has_s3_rows = bool(self.current_s3_pages)

        if self._pre_parse_snapshot_loading:
            self.left_panel.query_btn.setText("중지")
            self.left_panel.query_btn.setEnabled(True)
        else:
            self.left_panel.query_btn.setText("조회")
            self.left_panel.query_btn.setEnabled(has_s3_rows and selected_books and not self._pre_parse_is_running)

        if self._pre_parse_is_running:
            self.left_panel.run_btn.setText("중지")
            self.left_panel.run_btn.setEnabled(True)
        else:
            self.left_panel.run_btn.setText("실행")
            self.left_panel.run_btn.setEnabled(
                self._pre_parse_query_ready
                and not self._pre_parse_snapshot_loading
                and selected_checks
                and bool(self._pre_parse_queried_book_ids)
            )

    def _on_page_clicked(self, row: int, _col: int) -> None:
        self._show_pre_parse_preview_for_row(row)

    def _update_stats_from_rows(self, rows: List[dict]) -> None:
        total_stats = self._calc_stats(rows, self._label_rows)
        selected_books = set(self.left_panel.selected_book_ids())
        selected_rows = []
        selected_label_rows = []
        for row in rows:
            page_key = str(row.get("page_no", ""))
            if ":" not in page_key:
                continue
            book_id = page_key.split(":", 1)[0]
            if book_id in selected_books:
                selected_rows.append(row)
        for row in self._label_rows:
            if str(row.get("book_id", "")) in selected_books:
                selected_label_rows.append(row)
        selected_stats = self._calc_stats(selected_rows, selected_label_rows)
        self.top_bar.update_stats(
            total_books=int(total_stats["도서 수"]),
            total_pages=int(total_stats["페이지 수"]),
            error_pages=int(total_stats["오류 페이지"]),
            total_issues=int(total_stats["총 오류"]),
            pass_rate=float(total_stats["통과율"]),
        )
        self.right_panel.update_dashboard(
            stats=selected_stats,
            rows=selected_rows,
            issues=self._filter_issues_by_books(self.current_issues, selected_books),
            label_rows=selected_label_rows,
        )
