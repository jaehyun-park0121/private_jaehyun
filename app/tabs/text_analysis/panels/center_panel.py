from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal, QSize, QPoint, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.tabs.text_analysis.features.row_builders import expand_label_rows_to_display_rows, deduplicate_display_rows_to_label_rows

from app.tabs.text_analysis.features.base_state import BASE_STATE_NORMAL, is_error_base_state

_HEADERS = ["도서명", "페이지", "라벨 ID", "라벨", "값", "비고"]
_COL_COUNT = len(_HEADERS)
_COL_BOOK = 0
_COL_PAGE = 1
_COL_LABEL_ID = 2
_COL_LABEL = 3
_COL_VALUE = 4
_COL_DETAIL = 5


def _detail_text(row_data: Dict[str, Any]) -> str:
    return str(row_data.get("tool_error_detail", "")).strip()


def _truncate_chars(text: str, max_chars: int) -> str:
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _filter_field_value(row_data: Dict[str, Any], field: str) -> str:
    if field == "book":
        return str(row_data.get("book_id", "")).strip()
    if field == "label":
        return str(row_data.get("label", "")).strip()
    if field == "detail":
        return _detail_text(row_data)
    return ""


def _render_filter_match_value(tool_id: str, value: str) -> str:
    text = str(value or "")
    if tool_id != "special_char_analysis":
        return text.strip()
    if text == "\n":
        return r"\n"
    if text == "\r":
        return r"\r"
    if text == "\t":
        return r"\t"
    if text == " ":
        return "<space>"
    return text.strip()


def _detail_filter_tool_id(row_data: Dict[str, Any]) -> str:
    detail_tool_id = str(row_data.get("detail_filter_tool_id", "")).strip()
    if detail_tool_id:
        return detail_tool_id
    return str(row_data.get("tool_id", "")).strip()


def _filter_field_values(row_data: Dict[str, Any], field: str) -> List[str]:
    if field != "detail":
        value = _filter_field_value(row_data, field)
        return [value] if value else []

    tool_id = _detail_filter_tool_id(row_data)
    explicit_values = _normalized_filter_values(row_data.get("detail_filter_values", []))
    if explicit_values:
        return [_render_filter_match_value(tool_id, value) for value in explicit_values if value]

    if tool_id not in {"search_tool", "special_char_analysis"}:
        value = _detail_text(row_data)
        return [value] if value else []

    rendered_values: List[str] = []
    for raw_value in list(row_data.get("tool_error_matches", []) or []):
        rendered = _render_filter_match_value(tool_id, str(raw_value))
        if not rendered:
            continue
        rendered_values.append(rendered)
    return rendered_values


def _normalized_filter_values(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        text = values.strip()
        return [text] if text else []

    normalized: List[str] = []
    try:
        iterator = list(values)
    except TypeError:
        text = str(values).strip()
        return [text] if text else []

    for value in iterator:
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


class CopyableTableView(QTableView):
    copy_requested = pyqtSignal()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.matches(QKeySequence.Copy):
            self.copy_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class FilterMenuButton(QToolButton):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._managed_menu: Optional[QWidget] = None
        self._menu_builder: Optional[Callable[[QWidget], None]] = None

    def setMenu(self, menu: Optional[QWidget]) -> None:  # type: ignore[override]
        self._managed_menu = menu

    def menu(self) -> Optional[QWidget]:  # type: ignore[override]
        return self._managed_menu

    def set_menu_builder(self, builder: Optional[Callable[[QWidget], None]]) -> None:
        self._menu_builder = builder

    def showMenu(self) -> None:  # type: ignore[override]
        menu = self._managed_menu
        if menu is None:
            return
        if menu.isVisible():
            menu.hide()
            return
        if self._menu_builder is not None:
            self._menu_builder(menu)
        anchor = self.mapToGlobal(QPoint(0, self.height()))
        if isinstance(menu, QMenu):
            menu.popup(anchor)
            return
        if hasattr(menu, "show_at"):
            menu.show_at(anchor, self.width())
            return
        menu.move(anchor)
        menu.show()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._managed_menu is not None:
            self.showMenu()
            event.accept()
            return
        super().mousePressEvent(event)


class FilterValueButton(QToolButton):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._base_text = text
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setAutoRaise(True)
        self.setCheckable(True)
        self.setObjectName("menuValueButton")
        self._apply_text(False)

    def setChecked(self, checked: bool) -> None:  # type: ignore[override]
        super().setChecked(checked)
        self._apply_text(bool(checked))

    def _apply_text(self, checked: bool) -> None:
        prefix = "\u2713  " if checked else "    "
        self.setText(f"{prefix}{self._base_text}")


class PersistentActionMenu(QMenu):
    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        action = self.actionAt(event.pos())
        if action is not None and action.isCheckable() and action.isEnabled():
            action.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class KwicHighlightDelegate(QStyledItemDelegate):
    _HIGHLIGHT_BG = QColor("#fde68a")
    _HIGHLIGHT_FG = QColor("#111827")
    _REPLACE_OLD_BG = QColor("#fef3c7")
    _REPLACE_OLD_FG = QColor("#92400e")
    _REPLACE_NEW_BG = QColor("#dbeafe")
    _REPLACE_NEW_FG = QColor("#1e3a8a")
    _ARROW_FG = QColor("#94a3b8")

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        row_data = index.data(Qt.UserRole + 40) or {}
        kwic_prefix = str(row_data.get("_kwic_prefix", ""))
        kwic_match = str(row_data.get("_kwic_match", ""))
        kwic_suffix = str(row_data.get("_kwic_suffix", ""))

        replace_preview_value = str(row_data.get("replace_preview_value", ""))
        match_start = int(row_data.get("_match_start", -1))
        match_end = int(row_data.get("_match_end", -1))

        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget).adjusted(4, 0, -4, 0)
        painter.save()
        painter.setClipRect(text_rect)
        font = opt.font
        painter.setFont(font)
        fm = QFontMetrics(font)
        y = text_rect.top() + (text_rect.height() + fm.ascent() - fm.descent()) // 2

        if replace_preview_value and kwic_match and match_start >= 0:
            self._paint_replace_preview(painter, text_rect, fm, y, kwic_prefix, kwic_match, kwic_suffix, row_data)
        elif kwic_match:
            x = text_rect.left()
            if kwic_prefix:
                painter.setPen(QPen(QColor("#374151")))
                painter.drawText(x, y, kwic_prefix)
                x += fm.horizontalAdvance(kwic_prefix)
            bg_w = fm.horizontalAdvance(kwic_match)
            painter.fillRect(x, text_rect.top() + 1, bg_w, text_rect.height() - 2, self._HIGHLIGHT_BG)
            bold_font = QFont(font)
            bold_font.setWeight(QFont.DemiBold)
            painter.setFont(bold_font)
            painter.setPen(QPen(self._HIGHLIGHT_FG))
            painter.drawText(x, y, kwic_match)
            painter.setFont(font)
            x += bg_w
            if kwic_suffix:
                painter.setPen(QPen(QColor("#374151")))
                painter.drawText(x, y, kwic_suffix)
        else:
            value_text = str(index.data(Qt.DisplayRole) or "")
            painter.setPen(QPen(QColor("#374151")))
            elided = fm.elidedText(value_text, Qt.ElideRight, text_rect.width())
            painter.drawText(text_rect.left(), y, elided)

        painter.restore()

    def _paint_replace_preview(self, painter, text_rect, fm, y, prefix, match, suffix, row_data):
        replace_segments = list(row_data.get("replace_preview_segments", []) or [])
        replacement_text = ""
        if replace_segments:
            replacement_text = str(replace_segments[0].get("replacement", "") if replace_segments else "")
        elif str(row_data.get("replace_preview_value", "")):
            replacement_text = str(row_data.get("_replace_target_text", ""))

        x = text_rect.left()
        font = painter.font()
        if prefix:
            painter.setPen(QPen(QColor("#374151")))
            painter.drawText(x, y, prefix)
            x += fm.horizontalAdvance(prefix)

        if match:
            old_w = fm.horizontalAdvance(match)
            painter.fillRect(x, text_rect.top() + 1, old_w, text_rect.height() - 2, self._REPLACE_OLD_BG)
            strike_font = QFont(font)
            strike_font.setStrikeOut(True)
            painter.setFont(strike_font)
            painter.setPen(QPen(self._REPLACE_OLD_FG))
            painter.drawText(x, y, match)
            painter.setFont(font)
            x += old_w

        arrow = " \u2192 "
        painter.setPen(QPen(self._ARROW_FG))
        painter.drawText(x, y, arrow)
        x += fm.horizontalAdvance(arrow)

        if replacement_text:
            new_w = fm.horizontalAdvance(replacement_text)
            painter.fillRect(x, text_rect.top() + 1, new_w, text_rect.height() - 2, self._REPLACE_NEW_BG)
            painter.setPen(QPen(self._REPLACE_NEW_FG))
            painter.drawText(x, y, replacement_text)
            x += new_w

        if suffix:
            painter.setPen(QPen(QColor("#374151")))
            painter.drawText(x, y, suffix)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # type: ignore[override]
        return QSize(option.rect.width(), 20)


class ResultTableModel(QAbstractTableModel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows) if not parent.isValid() else 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return _COL_COUNT if not parent.isValid() else 0

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < _COL_COUNT:
            return _HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        row_data = self._rows[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            return self._display_text(row_data, column)
        if role == Qt.ToolTipRole:
            return self._tooltip_text(row_data, column)
        if role == Qt.TextAlignmentRole:
            if column in {_COL_VALUE, _COL_DETAIL}:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignCenter)
        if role == Qt.BackgroundRole:
            if bool(row_data.get("replace_applied", False)):
                return QColor("#e0f2fe")
            if bool(row_data.get("is_problem", False)):
                return QColor("#fee2e2")
            if str(row_data.get("tool_id", "")).strip() in {"special_char_analysis", "search_tool"}:
                return QColor("#ffffff")
            return QColor("#fee2e2") if is_error_base_state(row_data.get("base_state")) else QColor("#ffffff")
        if role == Qt.UserRole + 10:
            return str(row_data.get("row_key", ""))
        if role == Qt.UserRole + 11:
            return str(row_data.get("book_id", ""))
        if role == Qt.UserRole + 12:
            return str(row_data.get("page_no", ""))
        if role == Qt.UserRole + 20:
            return str(row_data.get("base_state", BASE_STATE_NORMAL)).strip().lower()
        if role == Qt.UserRole + 22:
            return bool(row_data.get("is_problem", False))
        if role == Qt.UserRole + 23:
            return str(row_data.get("problem_reason", ""))
        if role == Qt.UserRole + 24:
            return str(row_data.get("tool_error_type", ""))
        if role == Qt.UserRole + 30:
            return str(row_data.get("highlight_text", ""))
        if role == Qt.UserRole + 31:
            return list(row_data.get("highlight_matches", []) or [])
        if role == Qt.UserRole + 32:
            return str(row_data.get("replace_preview_value", ""))
        if role == Qt.UserRole + 33:
            return list(row_data.get("replace_preview_segments", []) or [])
        if role == Qt.UserRole + 40:
            return row_data
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_data(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    @staticmethod
    def _display_text(row_data: Dict[str, Any], column: int) -> str:
        if column == _COL_BOOK:
            return str(row_data.get("book_id", ""))
        if column == _COL_PAGE:
            return str(row_data.get("page", row_data.get("page_display", "")))
        if column == _COL_LABEL_ID:
            return str(row_data.get("label_id", ""))
        if column == _COL_LABEL:
            return str(row_data.get("label", ""))
        if column == _COL_VALUE:
            return str(row_data.get("value", ""))
        if column == _COL_DETAIL:
            return _detail_text(row_data)
        return ""

    @staticmethod
    def _tooltip_text(row_data: Dict[str, Any], column: int) -> str:
        if column == _COL_VALUE:
            original_text = str(row_data.get("flags_text", "") or "")
            if original_text:
                return original_text
        return ResultTableModel._display_text(row_data, column)


class ResultFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._query = ""
        self._field_filters: Dict[str, set] = {"book": set(), "label": set(), "detail": set()}

    def set_query(self, query: str) -> None:
        self._query = str(query or "").strip().lower()
        self.invalidateFilter()

    def set_field_filters(self, filters: Dict[str, set]) -> None:
        self._field_filters = {key: set(values) for key, values in filters.items()}
        self.invalidateFilter()

    def row_matches_filters(
        self,
        source_row: int,
        source_parent: QModelIndex,
        *,
        ignore_field: Optional[str] = None,
    ) -> bool:
        model = self.sourceModel()
        if model is None:
            return False
        row_data = model.row_data(source_row) if hasattr(model, "row_data") else {}

        def text_at(column: int) -> str:
            index = model.index(source_row, column, source_parent)
            return str(model.data(index, Qt.DisplayRole) or "").strip()

        if self._query:
            row_text = " ".join(text_at(column) for column in range(_COL_COUNT)).lower()
            if self._query not in row_text:
                return False

        for field in ("book", "label", "detail"):
            if field == ignore_field:
                continue
            selected_values = set(_normalized_filter_values(self._field_filters.get(field, set())))
            if not selected_values:
                continue
            field_values = set(_normalized_filter_values(_filter_field_values(row_data, field)))
            if not field_values:
                return False
            if not (field_values & selected_values):
                return False

        return True

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        return self.row_matches_filters(source_row, source_parent)


class PersistentCheckMenu(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self._anchor_point: Optional[QPoint] = None
        self._preferred_height = 320
        self.setObjectName("persistentCheckMenu")
        self.setStyleSheet(
            """
            QFrame#persistentCheckMenu {
                background: #ffffff;
                color: #334155;
                border: 1px solid #d8dee8;
                border-radius: 8px;
            }
            QToolButton#menuActionButton {
                background: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                color: #334155;
                text-align: left;
            }
            QToolButton#menuActionButton:hover {
                background: #f8fafc;
            }
            QToolButton#menuActionButton:pressed {
                background: #eef2f7;
            }
            QToolButton#menuValueButton {
                background: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                color: #334155;
                text-align: left;
            }
            QToolButton#menuValueButton:hover {
                background: #f8fafc;
            }
            QToolButton#menuValueButton:checked {
                background: #f8fafc;
                color: #0f172a;
                font-weight: 400;
            }
            QScrollArea {
                border: 0;
                background: #ffffff;
            }
            QScrollArea > QWidget > QWidget {
                background: #ffffff;
            }
            QScrollBar:vertical {
                background: #f8fafc;
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
            """
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(0)

        self._select_all_btn = QToolButton(self)
        self._select_all_btn.setObjectName("menuActionButton")
        self._select_all_btn.setText("전체 선택")
        self._select_all_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._select_all_btn.setAutoRaise(True)
        root_layout.addWidget(self._select_all_btn)

        self._clear_btn = QToolButton(self)
        self._clear_btn.setObjectName("menuActionButton")
        self._clear_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._clear_btn.setAutoRaise(True)
        root_layout.addWidget(self._clear_btn)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet("border: 0; background: #d8dee8; min-height: 1px; max-height: 1px; margin: 4px 6px;")
        root_layout.addWidget(separator)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("background: #ffffff;")

        self._content = QWidget(self._scroll)
        self._content.setStyleSheet("background: #ffffff;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._scroll.setWidget(self._content)
        root_layout.addWidget(self._scroll)

    def set_anchor_point(self, point: QPoint) -> None:
        self._anchor_point = QPoint(point)

    def _clear_content(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def rebuild(
        self,
        *,
        field_name: str,
        value_counts: Dict[str, int],
        selected_values: set,
        on_select_all: Callable[[], None],
        on_clear: Callable[[], None],
        on_toggle: Callable[[str, bool], None],
    ) -> None:
        self._clear_content()
        self._clear_btn.setText(f"{field_name} 초기화")

        try:
            self._select_all_btn.clicked.disconnect()
        except TypeError:
            pass
        try:
            self._clear_btn.clicked.disconnect()
        except TypeError:
            pass

        self._select_all_btn.clicked.connect(lambda _=False: on_select_all())
        self._clear_btn.clicked.connect(lambda _=False: on_clear())

        if not value_counts:
            empty_label = QLabel("선택 가능한 항목이 없습니다", self._content)
            empty_label.setStyleSheet("color: #64748b; padding: 6px;")
            self._content_layout.addWidget(empty_label)
            self._select_all_btn.setEnabled(False)
            self._clear_btn.setEnabled(False)
            self._preferred_height = 120
            return

        self._select_all_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)

        row_heights: List[int] = []
        for value in sorted(value_counts.keys()):
            count = int(value_counts.get(value, 0))
            button = FilterValueButton(f"{_truncate_chars(value, 90)} ({count})", self._content)
            button.setChecked(value in selected_values)
            button.setToolTip(f"{value} ({count})")
            button.toggled.connect(lambda checked, v=value: on_toggle(v, checked))
            self._content_layout.addWidget(button)
            row_heights.append(max(28, button.sizeHint().height()))

        self._content_layout.addStretch(1)
        visible_rows = min(max(len(row_heights), 1), 10)
        list_height = sum(row_heights[:visible_rows])
        action_height = max(28, self._select_all_btn.sizeHint().height()) + max(28, self._clear_btn.sizeHint().height())
        self._preferred_height = min(max(action_height + list_height + 36, 120), 360)

    def show_at(self, point: QPoint, min_width: int = 0) -> None:
        self.set_anchor_point(point)
        width = max(int(min_width), 220)
        self.resize(width, self._preferred_height)
        self.move(point)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.PopupFocusReason)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._anchor_point is not None:
            QTimer.singleShot(0, lambda: self.move(self._anchor_point) if self.isVisible() else None)


class CenterPanelWidget(QWidget):
    ui_log_requested = pyqtSignal(str)
    filters_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._book_count = 0
        self._active_tool_id = "special_char_analysis"
        self._selected_filters: Dict[str, set] = {"book": set(), "label": set(), "detail": set()}
        self._label_rows_cache: List[Dict[str, Any]] = []
        self._rows_cache: List[Dict[str, Any]] = []
        self._results_only = False

        self.data_title = QLabel("검사 결과 (도서 단위) - 0개")
        self.data_title.setStyleSheet("font-weight: 600;")

        self._model = ResultTableModel(self)
        self._proxy = ResultFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self.page_table = CopyableTableView()
        self.page_table.setModel(self._proxy)
        self.page_table.setItemDelegateForColumn(_COL_VALUE, KwicHighlightDelegate(self.page_table))
        self.page_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.page_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.page_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.page_table.verticalHeader().setVisible(False)
        self.page_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.page_table.verticalHeader().setDefaultSectionSize(20)
        self.page_table.setWordWrap(False)
        self.page_table.setTextElideMode(Qt.ElideRight)
        self.page_table.setStyleSheet(
            """
            QTableView {
                border: 1px solid #d8dee8;
                border-radius: 6px;
                gridline-color: #edf1f7;
                background: #ffffff;
            }
            QTableView::item {
                padding: 2px 6px;
            }
            """
        )
        header = self.page_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(_COL_DETAIL, QHeaderView.Stretch)
        header.resizeSection(_COL_BOOK, 110)
        header.resizeSection(_COL_PAGE, 70)
        header.resizeSection(_COL_LABEL_ID, 70)
        header.resizeSection(_COL_LABEL, 95)
        header.resizeSection(_COL_VALUE, 260)
        self.page_table.copy_requested.connect(self._copy_selected_cells)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("검색")
        self.search_edit.setFixedWidth(170)
        self.search_edit.setMinimumHeight(26)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_edit.setStyleSheet(
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
            }
            """
        )

        self.book_filter_btn = self._build_filter_button("bookFilterBtn", "도서 ▼")
        self.label_filter_btn = self._build_filter_button("labelFilterBtn", "라벨 ▼")
        self.detail_filter_btn = self._build_filter_button("detailFilterBtn", "검색어 ▼")
        self.problem_check_btn = self._build_filter_button("problemCheckBtn", "확인 필요 체크")
        self.problem_reset_btn = self._build_filter_button("problemResetBtn", "확인 필요 초기화 ▼")
        self.problem_reset_btn.setPopupMode(QToolButton.InstantPopup)

        title_row = QHBoxLayout()
        title_row.addWidget(self.data_title)
        title_row.addStretch(1)
        title_row.addWidget(self.book_filter_btn)
        title_row.addWidget(self.label_filter_btn)
        title_row.addWidget(self.detail_filter_btn)
        title_row.addWidget(self.problem_check_btn)
        title_row.addWidget(self.problem_reset_btn)
        title_row.addWidget(self.search_edit)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #d8dee8;")

        root = QVBoxLayout(self)
        root.addLayout(title_row)
        root.addWidget(divider)
        root.addWidget(self.page_table, 1)

        self._configure_field_filter_menus()

    def set_active_tool_id(self, tool_id: str) -> None:
        self._active_tool_id = str(tool_id or "").strip() or "special_char_analysis"
        self._update_filter_button_texts()

    def source_row_data(self, proxy_row: int) -> Optional[Dict[str, Any]]:
        proxy_index = self._proxy.index(proxy_row, 0)
        source_index = self._proxy.mapToSource(proxy_index)
        return self._model.row_data(source_index.row())

    def set_books(self, rows: List[Dict[str, Any]]) -> None:
        self._book_count = len(rows)
        self._refresh_result_title()

    def set_pages(self, rows: List[Dict[str, Any]], *, results_only: Optional[bool] = None) -> None:
        if results_only is not None:
            self._results_only = bool(results_only)
        self._label_rows_cache = list(rows)
        filtered = [row for row in rows if is_error_base_state(row.get("base_state"))] if self._results_only else list(rows)
        display_rows = expand_label_rows_to_display_rows(filtered)
        self._rows_cache = display_rows
        self._model.set_rows(display_rows)
        for field in ("book", "label", "detail"):
            existing = set(self._collect_filter_values(field))
            self._selected_filters[field] = {
                value for value in self._selected_filters.get(field, set()) if value in existing
            }
        self._update_filter_button_texts()
        self._proxy.set_field_filters(self._selected_filters)
        self._refresh_result_title()

    def visible_source_rows(self) -> List[Dict[str, Any]]:
        display_rows: List[Dict[str, Any]] = []
        for row in range(self._proxy.rowCount()):
            row_data = self.source_row_data(row)
            if row_data:
                display_rows.append(row_data)
        return deduplicate_display_rows_to_label_rows(display_rows, self._label_rows_cache)

    def visible_display_rows(self) -> List[Dict[str, Any]]:
        display_rows: List[Dict[str, Any]] = []
        for row in range(self._proxy.rowCount()):
            row_data = self.source_row_data(row)
            if row_data:
                display_rows.append(row_data)
        return display_rows

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_query(text)
        self._refresh_result_title()
        self.filters_changed.emit()

    def _build_filter_button(self, object_name: str, text: str) -> QToolButton:
        button = FilterMenuButton()
        button.setObjectName(object_name)
        button.setText(text)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setMinimumHeight(26)
        button.setStyleSheet(
            f"""
            QToolButton#{object_name} {{
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 8px;
                padding: 3px 8px;
                color: #334155;
                font-size: 11px;
                qproperty-toolButtonStyle: ToolButtonTextOnly;
            }}
            QToolButton#{object_name}:hover {{
                background: #f8fafc;
            }}
            QToolButton#{object_name}::menu-indicator {{
                image: none;
                width: 0px;
            }}
            """
        )
        return button

    def _configure_field_filter_menus(self) -> None:
        menu_style = """
            QMenu {
                background: #ffffff;
                color: #334155;
                border: 1px solid #d8dee8;
                border-radius: 8px;
                padding: 6px;
                menu-scrollable: 1;
            }
            QMenu::item {
                padding: 6px 12px;
                margin: 2px 2px;
            }
            QMenu::item:selected {
                background: #f8fafc;
            }
            QMenu::separator {
                height: 1px;
                background: #d8dee8;
                margin: 4px 6px;
            }
        """

        for field, button in {
            "book": self.book_filter_btn,
            "label": self.label_filter_btn,
        }.items():
            menu = PersistentActionMenu(self)
            menu.setStyleSheet(menu_style)
            menu.setMaximumHeight(360)
            button.setMenu(menu)
            button.set_menu_builder(lambda m, f=field: self._rebuild_standard_field_menu(f, m))

        detail_menu = PersistentCheckMenu(self)
        self.detail_filter_btn.setMenu(detail_menu)
        self.detail_filter_btn.set_menu_builder(lambda m: self._rebuild_field_menu("detail", m))
        self._update_filter_button_texts()

    def _rebuild_standard_field_menu(self, field: str, menu: QMenu) -> None:
        menu.clear()
        value_counts = self._collect_filter_value_counts(field)
        values = sorted(value_counts.keys())
        selected = self._selected_filters.get(field, set())

        if not values:
            action = menu.addAction("선택 가능한 값 없음")
            action.setEnabled(False)
            return

        menu.addAction("전체 선택").triggered.connect(lambda _=False, f=field: self._select_all_field_filters(f))
        menu.addAction(f"{self._field_name(field)} 필터 초기화").triggered.connect(
            lambda _=False, f=field: self._clear_field_filters(f)
        )
        menu.addSeparator()

        for value in values:
            count = int(value_counts.get(value, 0))
            action = menu.addAction(f"{_truncate_chars(value, 90)} ({count})")
            action.setCheckable(True)
            action.setChecked(value in selected)
            action.setToolTip(f"{value} ({count})")
            action.toggled.connect(lambda checked, f=field, v=value: self._toggle_field_filter(f, v, checked))

    def _rebuild_field_menu(self, field: str, menu: PersistentCheckMenu) -> None:
        value_counts = self._collect_filter_value_counts(field)
        selected = self._selected_filters.get(field, set())
        menu.rebuild(
            field_name=self._field_name(field),
            value_counts=value_counts,
            selected_values=selected,
            on_select_all=lambda f=field: self._select_all_field_filters(f),
            on_clear=lambda f=field: self._clear_field_filters(f),
            on_toggle=lambda value, checked, f=field: self._toggle_field_filter(f, value, checked),
        )

    def _refresh_visible_filter_menus(self) -> None:
        mapping = {
            "book": self.book_filter_btn,
            "label": self.label_filter_btn,
            "detail": self.detail_filter_btn,
        }
        for field, button in mapping.items():
            menu = button.menu()
            if isinstance(menu, PersistentCheckMenu) and menu.isVisible():
                self._rebuild_field_menu(field, menu)

    def _select_all_field_filters(self, field: str) -> None:
        self._selected_filters[field] = set(self._collect_filter_values(field))
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()
        self._refresh_visible_filter_menus()
        self.filters_changed.emit()

    def _clear_field_filters(self, field: str) -> None:
        self._selected_filters[field] = set()
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()
        self._refresh_visible_filter_menus()
        self.filters_changed.emit()

    def _clear_all_filters(self, *, emit_changed: bool = True) -> None:
        self._selected_filters = {"book": set(), "label": set(), "detail": set()}
        previous = self.search_edit.blockSignals(True)
        try:
            self.search_edit.clear()
        finally:
            self.search_edit.blockSignals(previous)
        self._proxy.set_query("")
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()
        self._refresh_visible_filter_menus()
        if emit_changed:
            self.filters_changed.emit()

    def _toggle_field_filter(self, field: str, value: str, checked: bool) -> None:
        selected = self._selected_filters.setdefault(field, set())
        if checked:
            selected.add(value)
        else:
            selected.discard(value)
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()
        self._refresh_visible_filter_menus()
        self.filters_changed.emit()

    def _field_name(self, field: str) -> str:
        return {"book": "도서", "label": "라벨", "detail": self._detail_filter_name()}.get(field, field)

    def _detail_filter_name(self) -> str:
        return "검색어"

    def _collect_filter_values(self, field: str) -> List[str]:
        return sorted(self._collect_filter_value_counts(field).keys())

    def _collect_filter_value_counts(self, field: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row_index in range(self._model.rowCount()):
            if not self._proxy.row_matches_filters(row_index, QModelIndex(), ignore_field=field):
                continue
            row = self._model.row_data(row_index) or {}
            for value in _filter_field_values(row, field):
                if value:
                    counts[value] = counts.get(value, 0) + 1
        return counts

    def _refresh_result_title(self) -> None:
        if self._results_only:
            self.data_title.setText(f"검사 결과 (매치 단위) - {self._proxy.rowCount()}건")
            return
        if self._model.rowCount() == 0:
            self.data_title.setText(f"검사 결과 (도서 단위) - {self._book_count}개")
            return
        self.data_title.setText(f"검사 결과 (페이지 단위) - {self._proxy.rowCount()}p")

    def _update_filter_button_texts(self) -> None:
        self.book_filter_btn.setText(
            f"도서({len(self._selected_filters.get('book', set()))}) ▼"
            if self._selected_filters.get("book")
            else "도서 ▼"
        )
        self.label_filter_btn.setText(
            f"라벨({len(self._selected_filters.get('label', set()))}) ▼"
            if self._selected_filters.get("label")
            else "라벨 ▼"
        )
        detail_name = self._detail_filter_name()
        self.detail_filter_btn.setText(
            f"{detail_name}({len(self._selected_filters.get('detail', set()))}) ▼"
            if self._selected_filters.get("detail")
            else f"{detail_name} ▼"
        )

    def _copy_selected_cells(self) -> None:
        selection = self.page_table.selectionModel()
        if selection is None:
            return
        indexes = selection.selectedIndexes()
        if not indexes:
            return

        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        selected = {(index.row(), index.column()) for index in indexes}

        lines: List[str] = []
        for row in rows:
            cells: List[str] = []
            for column in columns:
                cells.append(
                    str(self._proxy.index(row, column).data(Qt.DisplayRole) or "") if (row, column) in selected else ""
                )
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
