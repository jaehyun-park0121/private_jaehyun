"""표 편집기 — WebView(렌더링/편집) + HTML/Markdown 원본 편집."""

from PyQt6.QtCore import QEvent, QPoint, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..assets import assets_dir
from ..constants import COLOR_OK, COLOR_WARN
from .html_renderer import render_page
from .table_formats import (
    TABLE_FORMAT_HTML,
    TABLE_FORMAT_LABELS,
    TABLE_FORMAT_MARKDOWN,
    TableFormatError,
    format_source_pretty,
    render_html_to_source_and_spans,
    render_source_to_html,
    spans_from_attr,
    spans_to_attr,
)

# WebView setHtml용 base URL — `mathjax/tex-svg.js` 같은 상대 경로가 동작하도록
# assets 디렉토리를 가리켜야 한다. 끝에 슬래시 필수.
_ASSETS_BASE_URL = QUrl.fromLocalFile(str(assets_dir()) + "/")
_AUTO_PULL_INTERVAL_MS = 400


class TableEditor(QWidget):
    """표 편집기. 프로젝트별 원본 포맷(HTML/Markdown)을 유지하며 편집한다."""

    table_text_changed = pyqtSignal(str)
    table_spans_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_text = ""
        self._current_spans: list[dict[str, int]] = []
        self._source_format = TABLE_FORMAT_HTML
        self._render_valid = True
        self._source_tab_index: dict[str, int] = {}
        self._source_editors: dict[str, QPlainTextEdit] = {}
        self._source_placeholders: dict[str, str] = {}
        self._render_generation = 0
        self._has_rendered = False
        self._auto_pull_in_flight = False
        self._auto_pull_timer = QTimer(self)
        self._auto_pull_timer.setInterval(_AUTO_PULL_INTERVAL_MS)
        self._auto_pull_timer.timeout.connect(self._pull_if_dirty)
        self._edit_tool_buttons: list[QToolButton] = []
        self._html_edit_actions = []
        self._active_edit_button: QToolButton | None = None
        self._active_edit_menu: QMenu | None = None
        self._hover_close_timer = QTimer(self)
        self._hover_close_timer.setInterval(80)
        self._hover_close_timer.timeout.connect(self._close_hover_menu_if_away)
        self._build_ui()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._apply_format_ui()
        self.set_table_text("")

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("viewerEditorTabs")
        self.tabs.addTab(self._build_render_tab(), "렌더링 편집")
        self._source_tab_index[TABLE_FORMAT_HTML] = self.tabs.addTab(
            self._build_source_tab(TABLE_FORMAT_HTML),
            "HTML 소스",
        )
        self._source_tab_index[TABLE_FORMAT_MARKDOWN] = self.tabs.addTab(
            self._build_source_tab(TABLE_FORMAT_MARKDOWN),
            "Markdown 소스",
        )
        root.addWidget(self.tabs)

    def _build_render_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        top = QHBoxLayout()
        self.edit_mode_btn = QPushButton("편집")
        self.edit_mode_btn.setObjectName("toggle")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.setToolTip("편집 모드 켜기/끄기 (Ctrl+E)")
        self.edit_mode_btn.toggled.connect(self._on_edit_mode_toggled)
        top.addWidget(self.edit_mode_btn)
        top.addStretch()
        layout.addLayout(top)

        self.col_status = QLabel("")
        self.col_status.setObjectName("subtitle")
        self.col_status.setStyleSheet("padding: 2px 6px; font-size: 11px;")
        self.col_status.hide()
        layout.addWidget(self.col_status)

        view_row = QHBoxLayout()
        view_row.setContentsMargins(0, 0, 0, 0)
        view_row.setSpacing(8)
        self.edit_rail = self._build_table_edit_rail()
        self.edit_rail.hide()
        view_row.addWidget(self.edit_rail, 0, Qt.AlignmentFlag.AlignTop)

        self.web_view = QWebEngineView()
        self.web_view.setMinimumHeight(300)
        self.web_view.loadFinished.connect(lambda _: self._refresh_col_status())
        view_row.addWidget(self.web_view, 1)
        layout.addLayout(view_row, 1)

        return tab

    def _build_table_edit_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("editRail")
        rail.setFixedWidth(44)
        rail.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        rail_layout = QVBoxLayout(rail)
        margins = (5, 6, 5, 6)
        spacing = 6
        button_size = 34
        rail_layout.setContentsMargins(*margins)
        rail_layout.setSpacing(spacing)
        rail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        rail_buttons: list[QToolButton] = []

        def add_tool(
            text: str,
            tooltip: str,
            items: list[tuple[str, str, str]],
        ) -> QToolButton:
            btn = QToolButton()
            btn.setObjectName("railButton")
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setAccessibleName(tooltip)
            btn.setFixedSize(button_size, button_size)
            btn.clicked.connect(lambda _checked=False, b=btn: self._show_edit_menu(b))
            btn.installEventFilter(self)

            menu = QMenu(btn)
            menu.installEventFilter(self)
            menu.aboutToHide.connect(lambda m=menu: self._on_edit_menu_hidden(m))
            for label, action_tooltip, op in items:
                action = menu.addAction(label)
                action.setToolTip(action_tooltip)
                action.triggered.connect(lambda _checked=False, o=op: self._run_table_op(o))
            btn.setMenu(menu)
            rail_layout.addWidget(btn)
            self._edit_tool_buttons.append(btn)
            rail_buttons.append(btn)
            return btn

        add_tool("행", "행 편집", [
            ("위 추가", "위에 행 추가", "addRowAbove"),
            ("아래 추가", "아래에 행 추가", "addRowBelow"),
            ("행 삭제", "선택 행 삭제", "delRow"),
        ])
        add_tool("열", "열 편집", [
            ("왼쪽 추가", "왼쪽 열 추가", "addColLeft"),
            ("오른쪽 추가", "오른쪽 열 추가", "addColRight"),
            ("열 삭제", "선택 열 삭제", "delCol"),
        ])
        cell_btn = add_tool("셀", "셀 편집", [
            ("병합", "선택 셀 병합", "mergeSelection"),
            ("분할", "병합 셀 분할", "splitCell"),
            ("분할선 그리기", "선택 셀 안에 수평/수직 분할선을 그립니다", "drawSplitMode"),
            ("셀 추가", "현재 행 끝에 셀 추가", "addCellEnd"),
        ])
        cell_menu = cell_btn.menu()
        if cell_menu is not None:
            self._html_edit_actions.append(cell_menu.addSeparator())
            for label, action_tooltip, op in [
                ("헤더 지정", "헤더 지정", "setHeader"),
                ("헤더 해제", "헤더 해제", "unsetHeader"),
                ("하단 지정", "tfoot 지정", "setFooter"),
                ("하단 해제", "tfoot 해제", "unsetFooter"),
            ]:
                action = cell_menu.addAction(label)
                action.setToolTip(action_tooltip)
                action.triggered.connect(lambda _checked=False, o=op: self._run_table_op(o))
                self._html_edit_actions.append(action)
        add_tool("편", "잘라내기 / 복사 / 붙여넣기", [
            ("잘라내기", "선택 셀 잘라내기", "cut"),
            ("복사", "선택 셀 복사", "copy"),
            ("붙여넣기", "선택 셀 붙여넣기", "paste"),
        ])
        add_tool("정", "정합성", [
            ("열 맞춤", "전체 행 열 수 정규화", "normalizeTable"),
        ])

        rail_height = (
            margins[1]
            + margins[3]
            + len(rail_buttons) * button_size
            + max(0, len(rail_buttons) - 1) * spacing
        )
        rail.setFixedHeight(rail_height)
        return rail

    def _build_source_tab(self, table_format: str) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        top = QHBoxLayout()
        hint = QLabel(self._source_hint_text(table_format))
        hint.setObjectName("subtitle")
        top.addWidget(hint)
        top.addStretch()

        btn_pretty = QPushButton("Pretty뷰")
        btn_pretty.clicked.connect(lambda: self._format_source_view(table_format))
        top.addWidget(btn_pretty)

        btn_apply = QPushButton("미리보기 적용")
        btn_apply.setObjectName("primary")
        btn_apply.clicked.connect(self._apply_source_to_render)
        top.addWidget(btn_apply)
        layout.addLayout(top)

        editor = QPlainTextEdit()
        editor.setPlaceholderText(self._placeholder_for_format(table_format))
        layout.addWidget(editor, 1)

        self._source_editors[table_format] = editor
        self._source_placeholders[table_format] = self._placeholder_for_format(table_format)
        return tab

    # ---------- 외부 API ----------
    def set_table_text(self, text: str, spans_attr: str = ""):
        """현재 shape의 원본 문자열을 로드."""
        next_text = text or ""
        try:
            next_spans = spans_from_attr(spans_attr)
        except TableFormatError as exc:
            next_spans = []
            self.status_message.emit(str(exc))
        if (
            self._has_rendered
            and next_text == self._current_text
            and spans_to_attr(next_spans) == spans_to_attr(self._current_spans)
        ):
            return
        self._current_text = next_text
        self._current_spans = next_spans
        self._sync_source_editors()
        self._render_current_text()

    def current_table_text(self) -> str:
        return self._current_text

    def current_spans_attr(self) -> str:
        return spans_to_attr(self._current_spans)

    def set_table_format(self, table_format: str):
        """프로젝트별 원본 표 포맷을 지정."""
        if table_format == self._source_format:
            return
        self._source_format = table_format
        self._sync_source_editors()
        self._apply_format_ui()
        self._render_current_text()

    def current_table_format(self) -> str:
        return self._source_format

    def toggle_edit_mode(self):
        self.edit_mode_btn.toggle()

    def set_edit_mode(self, enabled: bool):
        if self.edit_mode_btn.isChecked() != enabled:
            self.edit_mode_btn.setChecked(enabled)

    def is_edit_mode(self) -> bool:
        return self.edit_mode_btn.isChecked()

    def run_table_op(self, op: str):
        self._run_table_op(op)

    def ensure_pulled(self, callback):
        """편집 중인 변경사항을 원본 포맷 문자열로 동기화한 뒤 callback."""
        if not self.is_edit_mode() or not self._render_valid:
            callback()
            return
        self._pull_now(callback)

    def is_on_source_tab(self) -> bool:
        """현재 소스 탭(HTML/Markdown)에 있는지 확인."""
        current_index = self.tabs.currentIndex()
        return current_index in self._source_tab_index.values()

    def apply_source_if_on_source_tab(self):
        """소스 탭에 있으면 자동으로 미리보기에 적용."""
        if self.is_on_source_tab():
            self._apply_source_to_render()

    # ---------- 내부 동작 ----------
    def _sync_source_editors(self):
        for fmt, editor in self._source_editors.items():
            editor.blockSignals(True)
            editor.setPlainText(self._current_text if fmt == self._source_format else "")
            editor.blockSignals(False)

    def _render_current_text(self):
        try:
            spans = self._current_spans if self._source_format == TABLE_FORMAT_MARKDOWN else None
            table_html = render_source_to_html(self._current_text, self._source_format, spans=spans)
            self._render_valid = True
        except TableFormatError as exc:
            if self._source_format == TABLE_FORMAT_MARKDOWN and self._current_spans:
                self._current_spans = []
                self.table_spans_changed.emit("")
                try:
                    table_html = render_source_to_html(self._current_text, self._source_format)
                    self._render_valid = True
                    self.status_message.emit(f"유효하지 않은 table_spans를 초기화했습니다: {exc}")
                except TableFormatError as retry_exc:
                    self._render_valid = False
                    msg = f"{TABLE_FORMAT_LABELS[self._source_format]} 파싱 실패: {retry_exc}"
                    table_html = f'<div class="empty">{msg}</div>'
            else:
                self._render_valid = False
                msg = f"{TABLE_FORMAT_LABELS[self._source_format]} 파싱 실패: {exc}"
                table_html = f'<div class="empty">{msg}</div>'
        self._render_generation += 1
        self.web_view.setHtml(
            render_page(table_html, self.edit_mode_btn.isChecked(), self._source_format),
            _ASSETS_BASE_URL,
        )
        self._has_rendered = True
        self._update_edit_controls()

    def _pull_if_dirty(self):
        if self._auto_pull_in_flight:
            return
        if not self.is_edit_mode() or not self._render_valid:
            return
        self._auto_pull_in_flight = True
        generation = self._render_generation
        js = "window.__consumeTableDirtyHtml ? window.__consumeTableDirtyHtml() : null"
        self.web_view.page().runJavaScript(
            js,
            lambda html, gen=generation: self._on_auto_pulled(html, gen),
        )

    def _on_auto_pulled(self, html, generation: int):
        self._auto_pull_in_flight = False
        if generation != self._render_generation:
            return
        if html is None:
            return
        try:
            table_text, spans = render_html_to_source_and_spans(html, self._source_format)
        except TableFormatError as exc:
            self.status_message.emit(
                f"{TABLE_FORMAT_LABELS[self._source_format]} 자동 반영 실패: {exc}"
            )
            return
        self._apply_pulled_state(table_text, spans)
        self._refresh_col_status()

    def _start_auto_pull(self):
        if not self._auto_pull_timer.isActive():
            self._auto_pull_timer.start()

    def _stop_auto_pull(self):
        if self._auto_pull_timer.isActive():
            self._auto_pull_timer.stop()
        self._auto_pull_in_flight = False

    def _pull_now(self, callback):
        js = (
            "window.__getEditableHtml ? "
            "window.__getEditableHtml() : "
            "(document.getElementById('editable') ? "
            "document.getElementById('editable').innerHTML : null)"
        )

        def _on(html):
            if html is not None:
                try:
                    pulled, spans = render_html_to_source_and_spans(html, self._source_format)
                except TableFormatError as exc:
                    self.status_message.emit(
                        f"{TABLE_FORMAT_LABELS[self._source_format]} 반영 실패: {exc}"
                    )
                    callback()
                    return
                self._apply_pulled_state(pulled, spans)
            callback()

        self.web_view.page().runJavaScript(js, _on)

    def eventFilter(self, obj, event):
        if obj in self._edit_tool_buttons:
            if event.type() == QEvent.Type.Enter:
                self._show_edit_menu(obj)
            elif event.type() == QEvent.Type.Leave:
                self._schedule_hover_menu_close()
        elif self._is_edit_menu(obj):
            if event.type() in {QEvent.Type.Enter, QEvent.Type.Leave}:
                self._schedule_hover_menu_close()
        return super().eventFilter(obj, event)

    def _on_edit_mode_toggled(self):
        on = self.edit_mode_btn.isChecked()
        if not on:
            self._stop_auto_pull()
            def _then():
                self._render_current_text()
            if self._render_valid:
                self._pull_now(_then)
            else:
                _then()
            return
        self._apply_format_ui()
        self._render_current_text()
        self._start_auto_pull()
        if not self._render_valid:
            self.status_message.emit(
                f"{TABLE_FORMAT_LABELS[self._source_format]} 원본을 먼저 수정해야 렌더링 편집을 사용할 수 있습니다."
            )

    def _on_tab_changed(self, _index: int):
        if not self.is_edit_mode():
            return
        self.ensure_pulled(lambda: None)

    def _run_table_op(self, op: str):
        if not self.edit_mode_btn.isChecked() or not self._render_valid:
            return
        js = (
            f"window.__tableOp && window.__tableOp({op!r}); "
            "window.__getEditableHtml ? "
            "window.__getEditableHtml() : "
            "(document.getElementById('editable') ? "
            "document.getElementById('editable').innerHTML : null)"
        )
        self.web_view.page().runJavaScript(js, self._on_render_pulled_and_check)

    def _on_render_pulled(self, html):
        if html is None:
            return
        try:
            table_text, spans = render_html_to_source_and_spans(html, self._source_format)
        except TableFormatError as exc:
            self.status_message.emit(
                f"{TABLE_FORMAT_LABELS[self._source_format]} 반영 실패: {exc}"
            )
            return
        self._apply_pulled_state(table_text, spans, force_emit=True)
        self.status_message.emit(
            f"표 편집 내용을 {TABLE_FORMAT_LABELS[self._source_format]} 원본에 반영했습니다."
        )

    def _on_render_pulled_and_check(self, html):
        self._on_render_pulled(html)
        self._refresh_col_status()

    def _apply_pulled_state(
        self,
        table_text: str,
        spans: list[dict[str, int]],
        force_emit: bool = False,
    ):
        if table_text != self._current_text or force_emit:
            self._current_text = table_text
            self._sync_source_editors()
            self.table_text_changed.emit(table_text)

        if self._source_format != TABLE_FORMAT_MARKDOWN:
            return
        old_attr = spans_to_attr(self._current_spans)
        new_attr = spans_to_attr(spans)
        self._current_spans = spans
        if old_attr != new_attr or (force_emit and new_attr):
            self.table_spans_changed.emit(new_attr)

    def _apply_source_to_render(self):
        editor = self._source_editors[self._source_format]
        source_text = editor.toPlainText()
        try:
            render_source_to_html(source_text, self._source_format)
        except TableFormatError as exc:
            self.status_message.emit(
                f"{TABLE_FORMAT_LABELS[self._source_format]} 파싱 실패: {exc}"
            )
            return
        self._current_text = source_text
        self._sync_source_editors()
        self._render_current_text()
        self.table_text_changed.emit(source_text)
        self.status_message.emit(
            f"{TABLE_FORMAT_LABELS[self._source_format]} 원본을 미리보기와 데이터에 반영했습니다."
        )

    def _format_source_view(self, table_format: str):
        editor = self._source_editors[table_format]
        try:
            formatted = format_source_pretty(editor.toPlainText(), table_format)
        except TableFormatError as exc:
            self.status_message.emit(
                f"{TABLE_FORMAT_LABELS[table_format]} 소스 정렬 실패: {exc}"
            )
            return
        editor.setPlainText(formatted)
        self.status_message.emit(f"{TABLE_FORMAT_LABELS[table_format]} 소스를 정렬했습니다.")

    def _apply_format_ui(self):
        for fmt, index in self._source_tab_index.items():
            enabled = fmt == self._source_format
            self.tabs.setTabEnabled(index, enabled)
            self._source_editors[fmt].setPlaceholderText(self._source_placeholders[fmt])
            self._source_editors[fmt].setReadOnly(not enabled)

        current_index = self.tabs.currentIndex()
        active_index = self._source_tab_index[self._source_format]
        if current_index in self._source_tab_index.values() and current_index != active_index:
            self.tabs.setCurrentIndex(active_index)

        self._update_edit_controls()

    def _update_edit_controls(self):
        editable = self.edit_mode_btn.isChecked() and self._render_valid
        self.edit_rail.setVisible(editable)
        for btn in self._edit_tool_buttons:
            btn.setEnabled(editable)
        for action in self._html_edit_actions:
            action.setVisible(self._source_format == TABLE_FORMAT_HTML)
        if not editable:
            self._hide_active_edit_menu()
        if not editable:
            self.col_status.hide()

    def _show_edit_menu(self, btn: QToolButton):
        if not self.edit_mode_btn.isChecked() or not self._render_valid or not btn.isEnabled():
            return
        menu = btn.menu()
        if menu is None:
            return
        self._hover_close_timer.stop()
        if self._active_edit_menu is not None and self._active_edit_menu is not menu:
            self._active_edit_menu.hide()
        self._active_edit_button = btn
        self._active_edit_menu = menu
        menu_width = menu.sizeHint().width()
        menu.popup(btn.mapToGlobal(QPoint(-menu_width, 0)))
        self._schedule_hover_menu_close()

    def _schedule_hover_menu_close(self):
        if self._active_edit_menu is not None and not self._hover_close_timer.isActive():
            self._hover_close_timer.start()

    def _close_hover_menu_if_away(self):
        if self._active_edit_menu is None:
            self._hover_close_timer.stop()
            return
        hovered_button = self._edit_button_under_cursor()
        if hovered_button is not None:
            if hovered_button is not self._active_edit_button:
                self._show_edit_menu(hovered_button)
            return
        if self._is_cursor_over_widget(self._active_edit_menu):
            return
        if self._is_cursor_over_widget(self.edit_rail):
            return
        self._hide_active_edit_menu()

    def _hide_active_edit_menu(self):
        if self._active_edit_menu is not None:
            self._active_edit_menu.hide()
        self._active_edit_menu = None
        self._active_edit_button = None
        self._hover_close_timer.stop()

    def _on_edit_menu_hidden(self, menu: QMenu):
        if self._active_edit_menu is menu:
            self._active_edit_menu = None
            self._active_edit_button = None
            self._hover_close_timer.stop()

    def _is_edit_menu(self, obj) -> bool:
        return any(btn.menu() is obj for btn in self._edit_tool_buttons)

    def _edit_button_under_cursor(self) -> QToolButton | None:
        for btn in self._edit_tool_buttons:
            if btn.isEnabled() and self._is_cursor_over_widget(btn):
                return btn
        return None

    @staticmethod
    def _is_cursor_over_widget(widget: QWidget) -> bool:
        if not widget.isVisible():
            return False
        return widget.rect().contains(widget.mapFromGlobal(QCursor.pos()))

    def _refresh_col_status(self):
        if not self.edit_mode_btn.isChecked() or not self._render_valid:
            self.col_status.hide()
            return
        self.web_view.page().runJavaScript(
            "window.__getRowColInfo && window.__getRowColInfo()",
            self._on_col_info,
        )

    def _on_col_info(self, info):
        if not info:
            self.col_status.hide()
            return
        per_table: dict[int, list[int]] = {}
        for row in info:
            per_table.setdefault(row["t"], []).append(row["c"])
        msgs = []
        any_bad = False
        for ti, counts in per_table.items():
            mx = max(counts) if counts else 0
            bad = [(i + 1, c) for i, c in enumerate(counts) if c != mx]
            prefix = f"표{ti+1} " if len(per_table) > 1 else ""
            if bad:
                any_bad = True
                detail = ", ".join(f"{r}행={c}" for r, c in bad[:4])
                if len(bad) > 4:
                    detail += f" 외 {len(bad)-4}건"
                msgs.append(f"{prefix}기준 {mx}열 불일치: {detail}")
            else:
                msgs.append(f"{prefix}모든 행 {mx}열")
        color = COLOR_WARN if any_bad else COLOR_OK
        prefix = "주의 " if any_bad else "정상 "
        self.col_status.setStyleSheet(
            f"color: {color}; padding: 2px 6px; font-size: 11px;"
        )
        self.col_status.setText(prefix + "  |  ".join(msgs))
        self.col_status.show()

    @staticmethod
    def _source_hint_text(table_format: str) -> str:
        if table_format == TABLE_FORMAT_MARKDOWN:
            return "Markdown 원본"
        return "HTML 원본"

    @staticmethod
    def _placeholder_for_format(table_format: str) -> str:
        if table_format == TABLE_FORMAT_MARKDOWN:
            return "| 항목 | 값 |\n| --- | --- |\n| 예시 | 내용 |"
        return "<table>...</table>"
