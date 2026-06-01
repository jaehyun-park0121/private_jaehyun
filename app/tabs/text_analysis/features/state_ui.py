from __future__ import annotations

from typing import Dict, List

from PyQt5.QtCore import QModelIndex, QTimer
from PyQt5.QtWidgets import QApplication, QMenu, QMessageBox

from app.tabs.text_analysis.features.base_state import is_error_base_state
from app.tabs.text_analysis.features.results.aggregator import TextAnalysisResultAggregator
from app.tabs.text_analysis.tools.search import prepare_runtime as prepare_search_runtime


class TextAnalysisStateUiMixin:
    _REPLACE_PREVIEW_DEBOUNCE_MS = 500

    def _initialize_text_analysis_ui_state(self) -> None:
        self.aggregator = TextAnalysisResultAggregator()

    def _wire_events(self) -> None:
        self.left_panel.query_btn.clicked.connect(self.query_selected_books)
        self.left_panel.run_btn.clicked.connect(self._on_run_tool_clicked)
        self.left_panel.tool_selected.connect(self.center_panel.set_active_tool_id)
        self.left_panel.tool_selected.connect(self._on_tool_selected)
        self.left_panel.book_list.itemChanged.connect(self._on_book_selection_changed)
        self.left_panel.replace_target_edit.textEdited.connect(self._schedule_replace_preview_refresh)
        self.left_panel.replace_target_edit.editingFinished.connect(self._refresh_replace_preview_immediately)
        self.left_panel.replace_regex_checkbox.toggled.connect(self._refresh_replace_preview_immediately)
        self.center_panel.filters_changed.connect(self._refresh_replace_preview_immediately)
        selection_model = self.center_panel.page_table.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._on_current_changed)
        self.center_panel.problem_check_btn.clicked.connect(self._mark_problem_for_visible_rows)

    def _ensure_replace_preview_timer(self) -> QTimer:
        timer = getattr(self, "_replace_preview_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._refresh_replace_preview)
            self._replace_preview_timer = timer
        return timer

    def _schedule_replace_preview_refresh(self, *_args) -> None:
        self._ensure_replace_preview_timer().start(self._REPLACE_PREVIEW_DEBOUNCE_MS)

    def _refresh_replace_preview_immediately(self, *_args) -> None:
        timer = getattr(self, "_replace_preview_timer", None)
        if timer is not None:
            timer.stop()
        self._refresh_replace_preview()

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
        menu = QMenu(self)
        menu.setStyleSheet(self._problem_menu_style())
        reset_all = menu.addAction("검수 도서 전체 초기화")
        reset_filtered = menu.addAction("현재 필터 결과 초기화")
        reset_reason_menu = menu.addMenu("특정 problem_reason 항목 초기화")
        reset_reason_menu.setStyleSheet(self._problem_menu_style())
        reset_reason_menu.aboutToShow.connect(
            lambda m=reset_reason_menu: self._rebuild_reset_reason_menu(m)
        )
        reset_all.triggered.connect(self._reset_problem_for_all_rows)
        reset_filtered.triggered.connect(self._reset_problem_for_visible_rows)
        self.center_panel.problem_reset_btn.setMenu(menu)

    def _on_book_selection_changed(self, _item) -> None:
        current_selected = set(self.left_panel.selected_book_ids())
        if current_selected != self._text_analysis_queried_book_ids:
            self._text_analysis_query_ready = False
        self._refresh_run_button_state()
        self._refresh_query_button_state()

    def _on_tool_selected(self, _tool_id: str) -> None:
        self._refresh_replace_preview_immediately()

    def _refresh_run_button_state(self) -> None:
        if self._text_analysis_is_running:
            self.left_panel.run_btn.setText("중지")
            self.left_panel.run_btn.setEnabled(True)
            self._refresh_query_button_state()
            return
        self.left_panel.run_btn.setText("실행")
        self.left_panel.set_run_ready(
            (not self._text_analysis_snapshot_loading)
            and self._text_analysis_query_ready
            and bool(self.current_label_rows)
        )
        self._refresh_query_button_state()

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if current.isValid():
            self._show_preview_for_proxy_index(current)

    def _select_first_row_after_refresh(self, *, prefer_result: bool) -> None:
        model = self.center_panel.page_table.model()
        if model is None or model.rowCount() == 0:
            self.right_panel.clear_preview()
            return

        target_row = 0
        if prefer_result:
            for row_index in range(model.rowCount()):
                row_data = self.center_panel.source_row_data(row_index)
                if row_data and is_error_base_state(row_data.get("base_state")):
                    target_row = row_index
                    break

        self.center_panel.page_table.setCurrentIndex(model.index(target_row, 0))
        self._show_preview_for_proxy_index(model.index(target_row, 0))

    def _refresh_dashboard(self) -> None:
        dashboard_tool_id = self._dashboard_active_tool_id()
        dashboard_runtime = self._dashboard_runtime(dashboard_tool_id)
        stats, page_rows, issues = self.aggregator.build_dashboard_payload(
            active_tool_id=dashboard_tool_id,
            label_rows=self.current_label_rows,
            row_has_issue=lambda row: self._dashboard_row_has_issue(
                row,
                dashboard_tool_id=dashboard_tool_id,
                dashboard_runtime=dashboard_runtime,
            ),
            issue_builder=lambda row: self._dashboard_issues_from_row(
                row,
                dashboard_tool_id=dashboard_tool_id,
                dashboard_runtime=dashboard_runtime,
            ),
        )
        self.right_panel.update_dashboard(
            stats=stats,
            rows=page_rows,
            issues=issues,
            label_rows=self.current_label_rows,
        )

    def _dashboard_active_tool_id(self) -> str:
        active_tool_id = str(getattr(self, "_active_tool_id", "") or "").strip() or "special_char_analysis"
        if active_tool_id == "replace_tool" and self._last_search_context:
            return "search_tool"
        return active_tool_id

    def _dashboard_runtime(self, dashboard_tool_id: str) -> Dict[str, object] | None:
        if dashboard_tool_id == "search_tool" and str(getattr(self, "_active_tool_id", "") or "").strip() == "replace_tool":
            search_context = dict(self._last_search_context or {})
            keyword = str(search_context.get("pattern", "") or "").strip()
            if not keyword:
                return None
            return prepare_search_runtime(
                {
                    "keyword": keyword,
                    "use_regex": bool(search_context.get("use_regex", False)),
                    "case_sensitive": bool(search_context.get("case_sensitive", False)),
                }
            )
        return None

    def _dashboard_row_has_issue(
        self,
        row: dict,
        *,
        dashboard_tool_id: str,
        dashboard_runtime: Dict[str, object] | None,
    ) -> bool:
        return bool(self._dashboard_issues_from_row(row, dashboard_tool_id=dashboard_tool_id, dashboard_runtime=dashboard_runtime))

    def _dashboard_issues_from_row(
        self,
        row: dict,
        *,
        dashboard_tool_id: str,
        dashboard_runtime: Dict[str, object] | None,
    ) -> List[dict]:
        if dashboard_tool_id != "search_tool" or dashboard_runtime is None:
            return self._issues_from_label_row(row)

        keyword = str(dashboard_runtime.get("keyword", "") or "")
        matches = self._search_matches(
            str(row.get("flags_text", "") or ""),
            keyword,
            use_regex=bool(dashboard_runtime.get("use_regex", False)),
            case_sensitive=bool(dashboard_runtime.get("case_sensitive", False)),
            regex=dashboard_runtime.get("regex"),
        )
        if not matches:
            return []

        issues: List[dict] = []
        detail_text = self._build_match_detail(
            prefix="검색 결과",
            pattern=keyword,
            matches=matches,
            use_regex=bool(dashboard_runtime.get("use_regex", False)),
        )
        for match_value in self._normalize_match_values(matches):
            issues.append(
                {
                    "page_no": str(row.get("page_no", "")).strip(),
                    "page_display": str(row.get("page", "")).strip(),
                    "book_id": str(row.get("book_id", "")).strip(),
                    "label": str(row.get("label", "")).strip(),
                    "detected_text": self._render_detected_text("search_tool", str(match_value)),
                    "description": detail_text,
                }
            )
        return issues
