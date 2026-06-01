from typing import Dict, Iterable, List, Optional

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QStyleOptionComboBox,
    QStylePainter,
    QFormLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal

from app.common.panel_layout import DEFAULT_LEFT_PANEL_WIDTH
from ..widgets.info_dot_button import InfoDotButton

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


class ArrowTextComboBox(QComboBox):
    """우측에 텍스트 ▼를 고정 표시하는 콤보박스."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._index_before_popup = -1
        self._arrow_label = QLabel("▼", self)
        self._arrow_label.setAlignment(Qt.AlignCenter)
        self._arrow_label.setStyleSheet(
            "color: #64748b; font-size: 10px; background: transparent; border: none;"
        )
        self._arrow_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.activated.connect(self._on_activated)
        self.currentIndexChanged.connect(lambda _idx: self._sync_empty_state())
        self._sync_empty_state()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        arrow_w = 16
        self._arrow_label.setGeometry(self.width() - arrow_w - 6, 0, arrow_w, self.height())

    def paintEvent(self, event) -> None:  # type: ignore[override]
        # Qt/플랫폼에 따라 non-editable QComboBox의 placeholder 렌더링이 누락될 수 있어
        # 미선택 상태에서는 placeholder를 직접 그린다.
        if self.currentIndex() >= 0 or not self.placeholderText():
            super().paintEvent(event)
            return
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self.placeholderText()
        option.palette.setColor(QPalette.Text, QColor("#94a3b8"))
        option.palette.setColor(QPalette.ButtonText, QColor("#94a3b8"))
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)

    def showPopup(self) -> None:  # type: ignore[override]
        self._index_before_popup = self.currentIndex()
        super().showPopup()

    def _on_activated(self, index: int) -> None:
        # 같은 항목을 다시 선택하면 미선택 상태로 되돌린다.
        if index >= 0 and index == self._index_before_popup:
            self.setCurrentIndex(-1)

    def _sync_empty_state(self) -> None:
        is_empty = self.currentIndex() < 0
        self.setProperty("empty", is_empty)
        self._arrow_label.setStyleSheet(
            (
                "color: #94a3b8; font-size: 10px; background: transparent; border: none;"
                if is_empty
                else "color: #64748b; font-size: 10px; background: transparent; border: none;"
            )
        )
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()


class FixedHeightItemDelegate(QStyledItemDelegate):
    """콤보박스 popup 행 높이를 강제로 고정한다."""

    def __init__(self, row_height: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._row_height = max(1, int(row_height))

    def sizeHint(self, option, index):  # type: ignore[override]
        base = super().sizeHint(option, index)
        return QSize(base.width(), self._row_height)


class MultiSelectButtonGroup(QWidget):
    """버튼형 다중 선택 옵션 그룹."""

    def __init__(
        self,
        choices: List[str],
        default_values: Optional[List[str]] = None,
        columns: int = 3,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._buttons: Dict[str, QPushButton] = {}
        column_count = max(1, int(columns))
        selected = set(default_values or [])

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)

        for i, choice in enumerate(choices):
            value = str(choice).strip()
            if not value:
                continue
            button = QPushButton(value)
            button.setCheckable(True)
            button.setChecked(value in selected)
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
            row = i // column_count
            col = i % column_count
            layout.addWidget(button, row, col)
            self._buttons[value] = button

    def selected_values(self) -> List[str]:
        return [value for value, button in self._buttons.items() if button.isChecked()]


def _tag_badge_colors(tag: str) -> tuple:
    """태그 배지 (배경색, 텍스트색) — 눈에 띄지 않는 톤다운 색상."""
    normalized = tag.strip().lower()
    if normalized in {"필수", "required"}:
        return "#f5e8e8", "#a87070"
    if normalized in {"선택", "optional"}:
        return "#e8eef5", "#7088a8"
    return "#f0f2f4", "#909aaa"


class LeftPanelWidget(QWidget):
    checks_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._book_check_syncing = False
        self._select_all_was_partial = False
        self._check_syncing = False
        self._check_boxes: Dict[str, QCheckBox] = {}
        self._check_options: Dict[str, Dict[str, QWidget]] = {}
        self._check_cards: Dict[str, QFrame] = {}

        self.book_list = QListWidget()
        self.book_list.setAlternatingRowColors(False)
        self.book_list.setMinimumHeight(180)
        self.book_list.setStyleSheet(_SCROLLBAR_STYLE)
        self.select_all_books_checkbox = QCheckBox("전체")
        self.select_all_books_checkbox.setChecked(True)
        self.query_btn = QPushButton("조회")
        self.query_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self.run_btn = QPushButton("실행")
        self.run_btn.setStyleSheet(_ACTION_BTN_STYLE)

        self.book_box = QGroupBox("도서 목록(0)")
        self.book_box.setStyleSheet(_GROUP_BOX_STYLE)
        book_layout = QVBoxLayout(self.book_box)
        book_header = QHBoxLayout()
        book_header.addStretch(1)
        book_header.addWidget(self.select_all_books_checkbox)
        book_layout.addLayout(book_header)
        book_layout.addWidget(self.book_list)
        book_layout.addWidget(self.query_btn)

        self.check_box = QGroupBox("검수 목록(0)")
        self.check_box.setStyleSheet(_GROUP_BOX_STYLE)
        check_layout = QVBoxLayout(self.check_box)
        check_layout.setContentsMargins(8, 10, 8, 8)
        self.checks_scroll = QScrollArea()
        self.checks_scroll.setWidgetResizable(True)
        self.checks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.checks_scroll.setFrameShape(QFrame.NoFrame)
        self.checks_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }" + _SCROLLBAR_STYLE
        )
        self.checks_host = QWidget()
        self.checks_host.setStyleSheet("background: transparent; border: none;")
        self.checks_host.setMinimumWidth(0)
        self.checks_layout = QVBoxLayout(self.checks_host)
        self.checks_layout.setContentsMargins(0, 0, 0, 0)
        self.checks_layout.setSpacing(8)
        self.checks_layout.addStretch(1)
        self.checks_scroll.setWidget(self.checks_host)
        check_layout.addWidget(self.checks_scroll, 1)
        check_layout.addWidget(self.run_btn)

        root = QVBoxLayout(self)
        root.addWidget(self.book_box, 1)
        root.addWidget(self.check_box, 2)
        self.select_all_books_checkbox.pressed.connect(self._remember_select_all_state)
        self.select_all_books_checkbox.clicked.connect(self._on_select_all_books_clicked)
        self.book_list.itemChanged.connect(self._sync_select_all_checkbox)
        self.book_list.viewport().installEventFilter(self)
        self.refresh_width_constraints()

    def set_checks(self, checks: Iterable[dict]) -> None:
        checks_list = list(checks)
        while self.checks_layout.count() > 1:
            item = self.checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._check_boxes = {}
        self._check_options = {}
        self._check_cards = {}

        for check in checks_list:
            plugin_id = str(check.get("plugin_id", "")).strip()
            title = str(check.get("title", plugin_id))
            tag = str(check.get("tag", "")).strip()
            description = str(check.get("description", "")).strip()
            option_schema = check.get("options", [])
            card = self._build_check_card(plugin_id, title, tag, description, option_schema)
            self.checks_layout.insertWidget(self.checks_layout.count() - 1, card)
        self.check_box.setTitle(f"검수 목록({len(checks_list)})")
        self.refresh_width_constraints()
        self.checks_changed.emit()

    def refresh_width_constraints(self) -> None:
        self.checks_host.adjustSize()
        self.book_box.adjustSize()
        self.check_box.adjustSize()
        self.setMinimumWidth(DEFAULT_LEFT_PANEL_WIDTH)

    def _build_check_card(
        self, plugin_id: str, title: str, tag: str, description: str, option_schema
    ) -> QWidget:
        card = QFrame()
        card.setProperty("plugin_id", plugin_id)
        card.setProperty("selected", False)
        card.setMinimumWidth(0)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            """
            QFrame[selected="false"] {
                background: #f9fafb;
                border: 1px solid #d8dee8;
                border-radius: 8px;
            }
            QFrame[selected="true"] {
                background: #eef4ff;
                border: 1px solid #93c5fd;
                border-radius: 8px;
            }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(4)
        check = QCheckBox(title)
        check.setMinimumWidth(0)
        check.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        check.setChecked(False)
        check.toggled.connect(lambda checked, pid=plugin_id: self._on_check_toggled(pid, checked))
        self._check_boxes[plugin_id] = check
        header.addWidget(check)
        header.addStretch(1)
        if tag:
            badge = QLabel(tag)
            badge_bg, badge_fg = _tag_badge_colors(tag)
            badge.setStyleSheet(
                f"QLabel {{ background: {badge_bg}; color: {badge_fg};"
                f" border-radius: 2px; padding: 0px 1px;"
                f" font-size: 10px; font-weight: 500; }}"
            )
            header.addWidget(badge)
        info_btn = InfoDotButton()
        info_btn.setText("i")
        info_btn.setToolTip(description or "설명이 등록되지 않은 검수 항목입니다.")
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
        header.addWidget(info_btn)
        layout.addLayout(header)

        options_map: Dict[str, QWidget] = {}
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(8)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setVerticalSpacing(4)
        if isinstance(option_schema, list) and option_schema:
            for opt in option_schema:
                if not isinstance(opt, dict):
                    continue
                key = str(opt.get("key", "")).strip()
                title = str(opt.get("label", key)).strip()
                opt_type = str(opt.get("type", "text")).strip().lower()
                if not key:
                    continue
                if opt_type == "bool":
                    editor = QCheckBox()
                    editor.setChecked(bool(opt.get("default", False)))
                    editor.setStyleSheet(
                        "QCheckBox { color: #334155; font-size: 11px; background: transparent; }"
                    )
                    editor.setMinimumWidth(0)
                    editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    editor.setFixedHeight(26)
                elif opt_type == "select":
                    editor = ArrowTextComboBox()
                    choices = opt.get("choices", [])
                    if isinstance(choices, list):
                        for c in choices:
                            editor.addItem(str(c))
                    editor.setMinimumWidth(0)
                    editor.setMinimumContentsLength(1)
                    editor.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                    editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    editor.setItemDelegate(FixedHeightItemDelegate(24, editor.view()))
                    editor.setPlaceholderText(str(opt.get("placeholder", "")))
                    default = str(opt.get("default", "")).strip()
                    if default:
                        idx = editor.findText(default)
                        if idx >= 0:
                            editor.setCurrentIndex(idx)
                    else:
                        editor.setCurrentIndex(-1)
                    editor.setStyleSheet(
                        """
                        QComboBox {
                            background: #f3f4f6;
                            border: 1px solid #d8dee8;
                            border-radius: 8px;
                            padding: 3px 8px;
                            padding-right: 24px;
                            font-size: 11px;
                        }
                        QComboBox[empty="true"] {
                            color: #94a3b8;
                        }
                        QComboBox[empty="false"] {
                            color: #374151;
                        }
                        QComboBox:focus {
                            background: #ffffff;
                            border: 1px solid #d8dee8;
                        }
                        QComboBox::drop-down {
                            subcontrol-origin: padding;
                            subcontrol-position: top right;
                            width: 1px;
                            border: none;
                            background: transparent;
                        }
                        QComboBox::down-arrow {
                            image: none;
                            width: 0px;
                            height: 0px;
                        }
                        QComboBox QAbstractItemView {
                            background: #ffffff;
                            border: 1px solid #d8dee8;
                            selection-background-color: #e8f0ff;
                            selection-color: #1f2937;
                            outline: 0;
                            font-size: 11px;
                            color: #334155;
                        }
                        QComboBox QAbstractItemView::item {
                            min-height: 24px;
                            padding: 0px 8px;
                            border: none;
                        }
                        QComboBox QAbstractItemView::item:hover {
                            background: #f1f5f9;
                            color: #1f2937;
                        }
                        QComboBox QAbstractItemView::item:selected {
                            background: #e8f0ff;
                            color: #1f2937;
                        }
                        """
                    )
                    editor.setFixedHeight(26)
                elif opt_type in {"multi_select", "multi_select_buttons", "buttons"}:
                    raw_choices = opt.get("choices", [])
                    choices: List[str] = []
                    if isinstance(raw_choices, list):
                        choices = [str(c).strip() for c in raw_choices if str(c).strip()]
                    raw_default = opt.get("default", [])
                    default_values: List[str] = []
                    if isinstance(raw_default, list):
                        default_values = [str(v).strip() for v in raw_default if str(v).strip()]
                    elif isinstance(raw_default, str) and raw_default.strip():
                        default_values = [v.strip() for v in raw_default.split(",") if v.strip()]
                    try:
                        columns = int(opt.get("columns", 3))
                    except Exception:
                        columns = 3
                    editor = MultiSelectButtonGroup(
                        choices=choices,
                        default_values=default_values,
                        columns=columns,
                    )
                    editor.setMinimumWidth(0)
                    editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
                else:
                    editor = QLineEdit()
                    editor.setPlaceholderText(str(opt.get("placeholder", "")))
                    editor.setText(str(opt.get("default", "")))
                    editor.setMinimumWidth(0)
                    editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    editor.setFixedHeight(26)
                    editor.setStyleSheet(
                        """
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
                            border: 1px solid #d8dee8;
                        }
                        """
                    )
                self._bind_option_widget(plugin_id, editor)
                options_map[key] = editor
                title_label = QLabel(title)
                title_label.setWordWrap(True)
                title_label.setMinimumWidth(0)
                title_label.setMinimumHeight(26)
                title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
                title_label.setStyleSheet("color: #475569; background: transparent; border: none;")
                form.addRow(title_label, editor)
        else:
            empty = QLabel("옵션 없음")
            empty.setStyleSheet("color: #94a3b8; background: transparent; border: none;")
            form.addRow(empty)

        layout.addLayout(form)
        self._check_options[plugin_id] = options_map
        self._check_cards[plugin_id] = card

        # 카드의 빈 영역/라벨 영역 클릭으로도 선택되도록 이벤트 필터를 연결한다.
        for widget in [card] + card.findChildren(QWidget):
            if isinstance(widget, (QCheckBox, QLineEdit, QComboBox, QToolButton, QPushButton)):
                continue
            widget.setProperty("plugin_id", plugin_id)
            widget.installEventFilter(self)
            widget.setCursor(Qt.PointingHandCursor)

        return card

    def _on_check_toggled(self, plugin_id: str, checked: bool) -> None:
        if self._check_syncing:
            return
        self._check_syncing = True
        if checked:
            for pid, checkbox in self._check_boxes.items():
                if pid != plugin_id:
                    checkbox.setChecked(False)
        self._check_syncing = False
        self._refresh_check_card_states()
        self.checks_changed.emit()

    def _bind_option_widget(self, plugin_id: str, widget: QWidget) -> None:
        widget.setProperty("plugin_id", plugin_id)
        widget.setProperty("plugin_option_widget", True)
        widget.installEventFilter(self)
        if isinstance(widget, MultiSelectButtonGroup):
            for child in widget.findChildren(QPushButton):
                child.setProperty("plugin_id", plugin_id)
                child.setProperty("plugin_option_widget", True)
                child.installEventFilter(self)

    def _refresh_check_card_states(self) -> None:
        selected_ids = set(self.selected_check_ids())
        for pid, card in self._check_cards.items():
            card.setProperty("selected", pid in selected_ids)
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()

    def selected_check_ids(self) -> List[str]:
        return [pid for pid, checkbox in self._check_boxes.items() if checkbox.isChecked()]

    def selected_check_options(self) -> Dict[str, Dict[str, object]]:
        payload: Dict[str, Dict[str, object]] = {}
        for pid in self.selected_check_ids():
            option_map = self._check_options.get(pid, {})
            values: Dict[str, object] = {}
            for key, widget in option_map.items():
                if isinstance(widget, QCheckBox):
                    values[key] = widget.isChecked()
                elif isinstance(widget, QComboBox):
                    values[key] = widget.currentText()
                elif isinstance(widget, MultiSelectButtonGroup):
                    values[key] = widget.selected_values()
                elif isinstance(widget, QLineEdit):
                    values[key] = widget.text()
            payload[pid] = values
        return payload

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
            plugin_id = watched.property("plugin_id")
            if plugin_id and plugin_id in self._check_boxes:
                checkbox = self._check_boxes[str(plugin_id)]
                option_widget = bool(watched.property("plugin_option_widget"))
                if not checkbox.isChecked():
                    checkbox.setChecked(True)
                if option_widget:
                    return False
                return True
        return super().eventFilter(watched, event)

    def set_books(self, books: Iterable[dict], *, selected_book_ids: Optional[Iterable[str]] = None) -> None:
        self._book_check_syncing = True
        books_list = list(books)
        selected_ids = None if selected_book_ids is None else {str(book_id) for book_id in selected_book_ids}
        self.book_list.clear()
        for row in books_list:
            book_id = str(row.get("book_id", ""))
            total_pages = row.get("total_pages", 0)
            item = QListWidgetItem(f"{book_id} ({total_pages})")
            item.setData(Qt.UserRole, book_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if selected_ids is None or book_id in selected_ids else Qt.Unchecked)
            self.book_list.addItem(item)
        self._book_check_syncing = False
        self._refresh_book_item_backgrounds()
        self.book_box.setTitle(f"도서 목록({len(books_list)})")
        self._refresh_select_all_checkbox_state()

    def book_ids(self) -> List[str]:
        return [str(self.book_list.item(i).data(Qt.UserRole)) for i in range(self.book_list.count())]

    def selected_book_ids(self) -> List[str]:
        selected: List[str] = []
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(str(item.data(Qt.UserRole)))
        return selected

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
        for i in range(self.book_list.count()):
            self.book_list.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)
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
        for i in range(self.book_list.count()):
            checked = self.book_list.item(i).checkState() == Qt.Checked
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
        current = item.checkState()
        item.setCheckState(Qt.Unchecked if current == Qt.Checked else Qt.Checked)
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
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
            item.setBackground(checked_bg if item.checkState() == Qt.Checked else default_bg)

    # check_list 기반 이벤트는 카드형 UI 전환으로 제거됨
