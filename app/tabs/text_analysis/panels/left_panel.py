from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
    QStyleOptionViewItem,
)

from app.common.panel_layout import DEFAULT_LEFT_PANEL_WIDTH
from ..widgets.info_dot_button import InfoDotButton

_DEFAULT_ALLOWED_PATTERN = r"[^A-Za-z0-9가-힣 ~!@#$%^&*()_\+\-=\[\]{}\|;:'\",<\.>/\?`\n]"

_ACTION_BTN_STYLE = """
    QPushButton {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 3px 10px;
        color: #334155;
        font-size: 11px;
        font-weight: 600;
        min-height: 26px;
    }
    QPushButton:hover {
        background: #f8fafc;
        border: 1px solid #d8dee8;
    }
    QPushButton:disabled {
        color: #94a3b8;
        background: #f1f5f9;
        border: 1px solid #d8dee8;
    }
"""

_GROUP_BOX_STYLE = """
    QGroupBox {
        border: 1px solid #d8dee8;
        border-radius: 8px;
        margin-top: 10px;
        background: #ffffff;
        color: #334155;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }
"""

_SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        background: #f6f8fc;
        width: 8px;
        border: none;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #cbd5e1;
        min-height: 24px;
        border-radius: 4px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background: #f6f8fc;
        height: 8px;
        border: none;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal {
        background: #cbd5e1;
        min-width: 24px;
        border-radius: 4px;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
"""

_CARD_STYLE = """
    QFrame[active="true"] {
        background: #eef4ff;
        border: 1px solid #93c5fd;
        border-radius: 8px;
    }
    QFrame[active="false"] {
        background: #ffffff;
        border: 1px solid #d8dee8;
        border-radius: 8px;
    }
    QFrame[planned="true"] QLabel[muted="true"] {
        color: #94a3b8;
    }
"""

_FIELD_STYLE = """
    QLineEdit {
        background: #f3f4f6;
        border: 1px solid #d8dee8;
        border-radius: 8px;
        padding: 3px 8px;
        color: #374151;
        font-size: 11px;
    }
    QLineEdit:focus {
        background: #ffffff;
    }
"""


class ToolCardFrame(QFrame):
    def __init__(self, tool_id: str, click_callback, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tool_id = str(tool_id)
        self._click_callback = click_callback

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if callable(self._click_callback):
            self._click_callback(self._tool_id)
        super().mousePressEvent(event)


class MultiSelectButtonGroup(QWidget):
    def __init__(
        self,
        choices: Optional[List[str]] = None,
        default_values: Optional[List[str]] = None,
        columns: int = 3,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._columns = max(1, int(columns))
        self._buttons: Dict[str, QPushButton] = {}
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(6)
        self._layout.setVerticalSpacing(6)
        self.set_choices(choices or [], default_values=default_values)

    def set_choices(self, choices: List[str], default_values: Optional[List[str]] = None) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons = {}

        selected = {str(value).strip().upper() for value in (default_values or []) if str(value).strip()}
        for index, choice in enumerate([str(choice).strip().upper() for choice in choices if str(choice).strip()]):
            button = QPushButton(choice)
            button.setCheckable(True)
            button.setChecked(choice in selected)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(30)
            button.setStyleSheet(
                """
                QPushButton {
                    background: #f3f4f6;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 3px 8px;
                    color: #334155;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #e2e8f0;
                }
                QPushButton:checked {
                    background: #dbeafe;
                    border: 1px solid #60a5fa;
                    color: #1d4ed8;
                    font-weight: 600;
                }
                """
            )
            row = index // self._columns
            col = index % self._columns
            self._layout.addWidget(button, row, col)
            self._buttons[choice] = button

    def selected_values(self) -> List[str]:
        return [value for value, button in self._buttons.items() if button.isChecked()]


class TextAnalysisLeftPanelWidget(QWidget):
    tool_selected = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._book_check_syncing = False
        self._select_all_was_partial = False
        self._selected_tool_id = "special_char_analysis"
        self._tool_cards: Dict[str, QFrame] = {}

        self.book_list = QListWidget()
        self.book_list.setAlternatingRowColors(False)
        self.book_list.setMinimumHeight(120)
        self.book_list.setStyleSheet(_SCROLLBAR_STYLE)

        self.select_all_books_checkbox = QCheckBox("전체")
        self.select_all_books_checkbox.setChecked(True)

        self.query_btn = QPushButton("조회")
        self.query_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self.run_btn = QPushButton("실행")
        self.run_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self.run_btn.setEnabled(False)

        self.book_box = QGroupBox("도서 목록(0)")
        self.book_box.setStyleSheet(_GROUP_BOX_STYLE)
        book_layout = QVBoxLayout(self.book_box)
        book_header = QHBoxLayout()
        book_header.addStretch(1)
        book_header.addWidget(self.select_all_books_checkbox)
        book_layout.addLayout(book_header)
        book_layout.addWidget(self.book_list)
        book_layout.addWidget(self.query_btn)

        self.tool_box = QGroupBox("검수 도구")
        self.tool_box.setStyleSheet(_GROUP_BOX_STYLE)
        tool_layout = QVBoxLayout(self.tool_box)
        tool_layout.setContentsMargins(8, 10, 8, 8)
        tool_layout.setSpacing(8)

        special_card = self._register_tool_card("special_char_analysis", self._build_special_char_card())
        search_card = self._register_tool_card("search_tool", self._build_search_card())
        replace_card = self._register_tool_card("replace_tool", self._build_replace_card())
        nfkc_card = self._register_tool_card("nfkc_normalize_tool", self._build_nfkc_card())

        tool_layout.addWidget(special_card)
        tool_layout.addWidget(search_card)
        tool_layout.addWidget(replace_card)
        tool_layout.addWidget(nfkc_card)
        tool_layout.addWidget(self.run_btn)

        root = QVBoxLayout(self)
        root.addWidget(self.book_box, 2)
        root.addWidget(self.tool_box, 3)
        self.setMinimumWidth(DEFAULT_LEFT_PANEL_WIDTH)

        self.select_all_books_checkbox.pressed.connect(self._remember_select_all_state)
        self.select_all_books_checkbox.clicked.connect(self._on_select_all_books_clicked)
        self.book_list.itemChanged.connect(self._sync_select_all_checkbox)
        self.book_list.viewport().installEventFilter(self)
        self._refresh_tool_card_states()

    def selected_book_ids(self) -> List[str]:
        selected: List[str] = []
        for index in range(self.book_list.count()):
            item = self.book_list.item(index)
            if item.checkState() == Qt.Checked:
                selected.append(str(item.data(Qt.UserRole)))
        return selected

    def selected_tool_id(self) -> str:
        return self._selected_tool_id

    def allowed_pattern(self) -> str:
        return self.allowed_pattern_edit.text().strip() or _DEFAULT_ALLOWED_PATTERN

    def target_labels(self) -> set[str]:
        normalized: set[str] = set()
        for raw_value in self.target_label_group.selected_values():
            value = str(raw_value or "").strip()
            if not value:
                continue
            if value.endswith(")") and "(" in value:
                candidate = value.rsplit("(", 1)[-1].rstrip(")").strip()
                if candidate:
                    value = candidate
            normalized.add(value.upper())
        return normalized

    def search_keyword(self) -> str:
        return self.search_keyword_edit.text().strip()

    def search_use_regex(self) -> bool:
        return self.search_regex_checkbox.isChecked()

    def search_case_sensitive(self) -> bool:
        return self.search_case_checkbox.isChecked()

    def replace_source_text(self) -> str:
        return self.search_keyword()

    def replace_target_text(self) -> str:
        return self.replace_target_edit.text()

    def replace_use_regex(self) -> bool:
        return self.replace_regex_checkbox.isChecked()

    def set_available_labels(self, labels: Iterable[str]) -> None:
        values = [str(label).strip().upper() for label in labels if str(label).strip()]
        self.target_label_group.set_choices(values)
        self.target_label_empty_label.setVisible(not bool(values))
        special_card = self._tool_cards.get("special_char_analysis")
        if special_card is not None:
            self._install_tool_card_event_filters(special_card)

    def set_run_ready(self, ready: bool) -> None:
        self.run_btn.setEnabled(bool(ready) and bool(self._selected_tool_id))

    def set_books(self, books: Iterable[dict], *, selected_book_ids: Optional[Iterable[str]] = None) -> None:
        self._book_check_syncing = True
        book_rows = list(books)
        selected_ids = None if selected_book_ids is None else {str(book_id) for book_id in selected_book_ids}
        self.book_list.clear()
        for row in book_rows:
            book_id = str(row.get("book_id", "")).strip()
            total_pages = int(row.get("total_pages", 0) or 0)
            item = QListWidgetItem(f"{book_id} ({total_pages})")
            item.setData(Qt.UserRole, book_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if selected_ids is None or book_id in selected_ids else Qt.Unchecked)
            self.book_list.addItem(item)
        self._book_check_syncing = False
        self._refresh_book_item_backgrounds()
        self.book_box.setTitle(f"도서 목록({len(book_rows)})")
        self._refresh_select_all_checkbox_state()

    def book_ids(self) -> List[str]:
        return [str(self.book_list.item(index).data(Qt.UserRole)) for index in range(self.book_list.count())]

    def _build_special_char_card(self) -> QFrame:
        card = ToolCardFrame("special_char_analysis", self._select_tool)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("active", True)
        card.setProperty("planned", False)
        card.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("특수문자 분석")
        title.setStyleSheet("font-weight: 600; color: #1f2937;")
        info_btn = self._build_info_button("허용 패턴 바깥의 문자를 OCR 라벨 값에서 찾아 비고에 표시합니다.")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(info_btn)
        layout.addLayout(header)

        pattern_row = QHBoxLayout()
        pattern_label = QLabel("허용 패턴")
        pattern_label.setFixedWidth(82)
        self.allowed_pattern_edit = QLineEdit(_DEFAULT_ALLOWED_PATTERN)
        self.allowed_pattern_edit.setPlaceholderText("허용 문자 패턴 입력")
        self.allowed_pattern_edit.setStyleSheet(_FIELD_STYLE)
        self.allowed_pattern_edit.installEventFilter(self)
        pattern_row.addWidget(pattern_label)
        pattern_row.addWidget(self.allowed_pattern_edit, 1)
        layout.addLayout(pattern_row)

        target_label = QLabel("대상 라벨")
        target_label.setStyleSheet("color: #475569;")
        layout.addWidget(target_label)
        self.target_label_group = MultiSelectButtonGroup(columns=3)
        self.target_label_group.installEventFilter(self)
        self.target_label_empty_label = QLabel("label 폴더의 라벨 목록이 여기에 표시됩니다.")
        self.target_label_empty_label.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.target_label_group)
        layout.addWidget(self.target_label_empty_label)
        return card

    def _build_search_card(self) -> QFrame:
        card = ToolCardFrame("search_tool", self._select_tool)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("active", False)
        card.setProperty("planned", False)
        card.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("검색")
        title.setStyleSheet("font-weight: 600; color: #1f2937;")
        info_btn = self._build_info_button("입력한 텍스트가 포함된 OCR 값만 찾아 비고와 통계에 표시합니다.")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(info_btn)
        layout.addLayout(header)

        keyword_row = QHBoxLayout()
        keyword_label = QLabel("검색어")
        keyword_label.setFixedWidth(82)
        self.search_keyword_edit = QLineEdit()
        self.search_keyword_edit.setPlaceholderText("검색어 또는 텍스트 입력")
        self.search_keyword_edit.setStyleSheet(_FIELD_STYLE)
        self.search_keyword_edit.installEventFilter(self)
        keyword_row.addWidget(keyword_label)
        keyword_row.addWidget(self.search_keyword_edit, 1)
        layout.addLayout(keyword_row)

        option_row = QHBoxLayout()
        option_label = QLabel("옵션")
        option_label.setFixedWidth(82)
        self.search_regex_checkbox = QCheckBox("정규식 모드")
        self.search_case_checkbox = QCheckBox("대소문자 구분")
        option_row.addWidget(option_label)
        option_row.addWidget(self.search_regex_checkbox)
        option_row.addWidget(self.search_case_checkbox)
        option_row.addStretch(1)
        layout.addLayout(option_row)
        return card

    def _build_replace_card(self) -> QFrame:
        card = ToolCardFrame("replace_tool", self._select_tool)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("active", False)
        card.setProperty("planned", False)
        card.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("치환")
        title.setStyleSheet("font-weight: 600; color: #1f2937;")
        info_btn = self._build_info_button("검색 도구의 검색어와 옵션을 그대로 사용해, 현재 중앙 결과 테이블에 보이는 항목만 치환합니다.")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(info_btn)
        layout.addLayout(header)

        linked_search_label = QLabel("검색/필터된 데이터를 치환합니다.")
        linked_search_label.setStyleSheet("color: #64748b; font-size: 11px;")
        linked_search_label.setWordWrap(True)
        layout.addWidget(linked_search_label)

        target_row = QHBoxLayout()
        target_label = QLabel("치환 값")
        target_label.setFixedWidth(82)
        self.replace_target_edit = QLineEdit()
        self.replace_target_edit.setPlaceholderText("대체 텍스트 입력")
        self.replace_target_edit.setStyleSheet(_FIELD_STYLE)
        self.replace_target_edit.installEventFilter(self)
        target_row.addWidget(target_label)
        target_row.addWidget(self.replace_target_edit, 1)
        layout.addLayout(target_row)

        option_row = QHBoxLayout()
        option_label = QLabel("옵션")
        option_label.setFixedWidth(82)
        self.replace_regex_checkbox = QCheckBox("정규식 모드")
        option_row.addWidget(option_label)
        option_row.addWidget(self.replace_regex_checkbox)
        option_row.addStretch(1)
        layout.addLayout(option_row)
        return card

    def _build_nfkc_card(self) -> QFrame:
        card = ToolCardFrame("nfkc_normalize_tool", self._select_tool)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("active", False)
        card.setProperty("planned", False)
        card.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("NFKC 정규화")
        title.setStyleSheet("font-weight: 600; color: #1f2937;")
        info_btn = self._build_info_button(
            "검색/특수문자 분석 결과와 현재 필터를 기준으로, 중앙 결과 테이블에 보이는 매칭 구간만 NFKC 정규화합니다."
        )
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(info_btn)
        layout.addLayout(header)

        description = QLabel("검색/필터된 데이터를 NFKC 정규화합니다.")
        description.setStyleSheet("color: #64748b; font-size: 11px;")
        description.setWordWrap(True)
        layout.addWidget(description)
        return card

    def _build_planned_card(self, *, tool_id: str, title: str, placeholder: str) -> QFrame:
        card = ToolCardFrame(tool_id, self._select_tool)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("active", False)
        card.setProperty("planned", True)
        card.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 600; color: #1f2937;")
        info_btn = self._build_info_button("선택은 가능하지만 아직 실행 동작은 연결되지 않았습니다.")
        header.addWidget(title_label)
        header.addStretch(1)
        header.addWidget(info_btn)
        layout.addLayout(header)

        muted = QLabel(placeholder)
        muted.setProperty("muted", True)
        muted.setWordWrap(True)
        layout.addWidget(muted)
        return card

    def _build_info_button(self, tooltip: str) -> QToolButton:
        info_btn = InfoDotButton()
        info_btn.setText("i")
        info_btn.setToolTip(str(tooltip))
        info_btn.setCursor(Qt.PointingHandCursor)
        info_btn.setFixedSize(16, 16)
        info_btn.setStyleSheet(
            """
            QToolButton {
                color: #64748b;
                background: #e5e7eb;
                border: 1px solid #d8dee8;
                border-radius: 8px;
                font-size: 10px;
                font-weight: 700;
                padding: 0;
            }
            QToolButton:hover {
                background: #dce3ea;
            }
            """
        )
        return info_btn

    def _select_tool(self, tool_id: str) -> None:
        self._selected_tool_id = str(tool_id)
        self._refresh_tool_card_states()
        self.tool_selected.emit(self._selected_tool_id)

    def _refresh_tool_card_states(self) -> None:
        for tool_id, card in self._tool_cards.items():
            card.setProperty("active", tool_id == self._selected_tool_id)
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        if watched is self.book_list.viewport() and event.type() == QEvent.MouseButtonPress:
            item = self.book_list.itemAt(event.pos())
            if item is None:
                return False
            if self._book_check_syncing:
                return False
            if self._is_book_check_indicator_hit(item, event.pos()):
                return False
            self._toggle_book_item_from_click(item)
            return True
        if event.type() == QEvent.MouseButtonPress:
            parent_card = self._find_tool_card(watched)
            if parent_card is not None:
                tool_id = str(parent_card.property("tool_id") or "")
                if tool_id:
                    self._select_tool(tool_id)
        return super().eventFilter(watched, event)

    def _find_tool_card(self, widget: QWidget) -> Optional[QFrame]:
        current: Optional[QWidget] = widget
        while current is not None:
            if current in self._tool_cards.values():
                return current  # type: ignore[return-value]
            current = current.parentWidget()
        return None

    def _register_tool_card(self, tool_id: str, card: QFrame) -> QFrame:
        card.setProperty("tool_id", tool_id)
        self._tool_cards[tool_id] = card
        self._install_tool_card_event_filters(card)
        return card

    def _install_tool_card_event_filters(self, card: QFrame) -> None:
        for child in card.findChildren(QWidget):
            if isinstance(child, QToolButton):
                continue
            child.installEventFilter(self)

    def _remember_select_all_state(self) -> None:
        self._select_all_was_partial = self.select_all_books_checkbox.checkState() == Qt.PartiallyChecked

    def _on_select_all_books_clicked(self, checked: bool) -> None:
        if self._select_all_was_partial:
            self._select_all_was_partial = False
            self._toggle_all_books(False)
            self._book_check_syncing = True
            self.select_all_books_checkbox.setTristate(False)
            self.select_all_books_checkbox.setCheckState(Qt.Unchecked)
            self._book_check_syncing = False
            return
        self._toggle_all_books(checked)

    def _toggle_all_books(self, checked: bool) -> None:
        if self._book_check_syncing:
            return
        self._book_check_syncing = True
        for index in range(self.book_list.count()):
            self.book_list.item(index).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._book_check_syncing = False
        self._refresh_book_item_backgrounds()

    def _sync_select_all_checkbox(self, _item: QListWidgetItem) -> None:
        if self._book_check_syncing:
            return
        self._refresh_select_all_checkbox_state()

    def _refresh_select_all_checkbox_state(self) -> None:
        self._book_check_syncing = True
        all_checked = self.book_list.count() > 0
        any_checked = False
        for index in range(self.book_list.count()):
            checked = self.book_list.item(index).checkState() == Qt.Checked
            all_checked = all_checked and checked
            any_checked = any_checked or checked
        self.select_all_books_checkbox.setChecked(all_checked)
        self.select_all_books_checkbox.setTristate(any_checked and not all_checked)
        if any_checked and not all_checked:
            self.select_all_books_checkbox.setCheckState(Qt.PartiallyChecked)
        else:
            self.select_all_books_checkbox.setTristate(False)
        self._book_check_syncing = False
        self._refresh_book_item_backgrounds()

    def _toggle_book_item_from_click(self, item: QListWidgetItem) -> None:
        if self._book_check_syncing:
            return
        self._book_check_syncing = True
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self._book_check_syncing = False
        self._refresh_book_item_backgrounds()
        self._sync_select_all_checkbox(item)

    def _is_book_check_indicator_hit(self, item: QListWidgetItem, pos) -> bool:
        index = self.book_list.indexFromItem(item)
        if not index.isValid():
            return False
        option = QStyleOptionViewItem()
        option.initFrom(self.book_list)
        option.rect = self.book_list.visualItemRect(item)
        check_rect = self.book_list.style().subElementRect(
            QStyle.SE_ItemViewItemCheckIndicator,
            option,
            self.book_list,
        )
        return check_rect.contains(pos)

    def _refresh_book_item_backgrounds(self) -> None:
        checked_bg = QColor("#f3f4f6")
        default_bg = QColor("#ffffff")
        for index in range(self.book_list.count()):
            item = self.book_list.item(index)
            item.setBackground(checked_bg if item.checkState() == Qt.Checked else default_bg)
