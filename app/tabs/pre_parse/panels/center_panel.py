from __future__ import annotations

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QKeySequence
from typing import Any, Dict, List, Optional

from app.tabs.pre_parse.features.base_state import BASE_STATE_NORMAL, is_error_base_state


def _truncate_chars(text: str, max_chars: int) -> str:
    value = str(text or "")
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


_HEADERS = ["도서명", "페이지", "라벨ID", "라벨", "값", "오류 세부 내용"]
_COL_COUNT = len(_HEADERS)

_COL_BOOK = 0
_COL_PAGE = 1
_COL_LABEL_ID = 2
_COL_LABEL = 3
_COL_VALUE = 4
_COL_DETAIL = 5


class CopyableTableView(QTableView):
    copy_requested = pyqtSignal()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.matches(QKeySequence.Copy):
            self.copy_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
        col = index.column()

        if role == Qt.DisplayRole:
            return self._display_text(row_data, col)

        if role == Qt.TextAlignmentRole:
            if col == _COL_DETAIL:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignCenter)

        if role == Qt.ToolTipRole:
            return self._display_text(row_data, col)

        if role == Qt.BackgroundRole:
            return QColor("#fee2e2") if bool(row_data.get("is_problem", False)) else QColor("#ffffff")

        if role == Qt.UserRole:
            if col == _COL_BOOK:
                return str(row_data.get("page_no", ""))
            if col == _COL_LABEL_ID:
                try:
                    return int(str(row_data.get("shape_index", -1)).strip())
                except Exception:
                    return -1
            return None

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
            return str(row_data.get("error_type", ""))

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self.endResetModel()

    def get_rows(self) -> List[Dict[str, Any]]:
        return self._rows

    def row_data(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    @staticmethod
    def _display_text(row_data: Dict, col: int) -> str:
        if col == _COL_BOOK:
            return str(row_data.get("book_id", ""))
        if col == _COL_PAGE:
            return str(row_data.get("page", row_data.get("file_name", "")))
        if col == _COL_LABEL_ID:
            return str(row_data.get("label_id", row_data.get("shape_index", "")))
        if col == _COL_LABEL:
            return str(row_data.get("label", ""))
        if col == _COL_VALUE:
            return str(row_data.get("value", row_data.get("flags_value", "")))
        if col == _COL_DETAIL:
            return str(row_data.get("error_detail", row_data.get("message", "")))
        return ""


class ResultFilterProxy(QSortFilterProxyModel):

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._query = ""
        self._error_only = True
        self._field_filters: Dict[str, set] = {"book": set(), "label": set(), "detail": set()}

    def set_query(self, query: str) -> None:
        self._query = query.strip().lower()
        self.invalidateFilter()

    def set_error_only(self, enabled: bool) -> None:
        self._error_only = enabled
        self.invalidateFilter()

    def set_field_filters(self, filters: Dict[str, set]) -> None:
        self._field_filters = filters
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

        def _val(col: int) -> str:
            idx = model.index(source_row, col, source_parent)
            return str(model.data(idx, Qt.DisplayRole) or "").strip()

        base_state = model.data(model.index(source_row, _COL_BOOK, source_parent), Qt.UserRole + 20)
        if self._error_only and not is_error_base_state(base_state):
            return False

        if self._query:
            row_text = " ".join(_val(c) for c in range(_COL_COUNT)).lower()
            if self._query not in row_text:
                return False

        mapping = {"book": _COL_BOOK, "label": _COL_LABEL}
        for field, col in mapping.items():
            if field == ignore_field:
                continue
            values = self._field_filters.get(field, set())
            if not values:
                continue
            cell_text = _val(col).lower()
            if not any(str(v).lower() in cell_text for v in values):
                return False

        detail_values = set() if ignore_field == "detail" else self._field_filters.get("detail", set())
        if detail_values:
            detail_text = str(
                model.data(model.index(source_row, _COL_DETAIL, source_parent), Qt.UserRole + 24) or ""
            ).lower()
            if not any(str(v).lower() in detail_text for v in detail_values):
                return False

        return True

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        return self.row_matches_filters(source_row, source_parent)


class PersistentCheckMenu(QMenu):
    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        action = self.actionAt(event.pos())
        if action is not None and action.isCheckable() and action.isEnabled():
            action.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CenterPanelWidget(QWidget):
    ui_log_requested = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._book_count = 0
        self.data_title = QLabel("검사 결과 (도서 단위) - 0개")
        self.data_title.setStyleSheet("font-weight: 600;")

        self._model = ResultTableModel(self)
        self._proxy = ResultFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self.page_table = CopyableTableView()
        self.page_table.setModel(self._proxy)
        self.page_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.page_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.page_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.page_table.verticalHeader().setVisible(False)
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
                padding: 1px 6px;
            }
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
        )

        header = self.page_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(_COL_DETAIL, QHeaderView.Stretch)
        header.setDefaultSectionSize(90)
        header.resizeSection(_COL_BOOK, 110)
        header.resizeSection(_COL_PAGE, 90)
        header.resizeSection(_COL_LABEL_ID, 55)
        header.resizeSection(_COL_LABEL, 80)
        header.resizeSection(_COL_VALUE, 80)
        self.page_table.copy_requested.connect(self._copy_selected_cells)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("검색")
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_edit.setFixedWidth(170)
        self.search_edit.setMinimumHeight(26)
        self.search_edit.setClearButtonEnabled(True)
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
                border: 1px solid #d8dee8;
                background: #ffffff;
            }
            """
        )

        self.book_filter_btn = QToolButton()
        self.book_filter_btn.setText("도서 ▼")
        self.book_filter_btn.setPopupMode(QToolButton.InstantPopup)
        self.label_filter_btn = QToolButton()
        self.label_filter_btn.setText("라벨 ▼")
        self.label_filter_btn.setPopupMode(QToolButton.InstantPopup)
        self.detail_filter_btn = QToolButton()
        self.detail_filter_btn.setText("오류 유형 ▼")
        self.detail_filter_btn.setPopupMode(QToolButton.InstantPopup)
        self.problem_check_btn = QToolButton()
        self.problem_check_btn.setText("확인 필요 체크")
        self.problem_reset_btn = QToolButton()
        self.problem_reset_btn.setText("확인 필요 초기화 ▼")
        self.problem_reset_btn.setPopupMode(QToolButton.InstantPopup)

        for btn_name, btn in {
            "bookFilterBtn": self.book_filter_btn,
            "labelFilterBtn": self.label_filter_btn,
            "detailFilterBtn": self.detail_filter_btn,
            "problemCheckBtn": self.problem_check_btn,
            "problemResetBtn": self.problem_reset_btn,
        }.items():
            btn.setObjectName(btn_name)
            btn.setMinimumHeight(26)
            btn.setStyleSheet(
                f"""
                QToolButton#{btn_name} {{
                    background: #ffffff;
                    border: 1px solid #d8dee8;
                    border-radius: 8px;
                    padding: 3px 8px;
                    color: #334155;
                    font-size: 11px;
                    qproperty-toolButtonStyle: ToolButtonTextOnly;
                }}
                QToolButton#{btn_name}:hover {{
                    background: #f8fafc;
                    border: 1px solid #d8dee8;
                }}
                QToolButton#{btn_name}::menu-indicator {{
                    image: none;
                    width: 0px;
                }}
                """
            )

        self._error_only_mode = True
        self._selected_filters: Dict[str, set] = {"book": set(), "label": set(), "detail": set()}

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
        root.addWidget(self.page_table, 3)

        self._rows_cache: List[Dict] = []
        self._configure_field_filter_menus()

    # ------------------------------------------------------------------
    # 외부 호환 API
    # ------------------------------------------------------------------

    def source_row_data(self, proxy_row: int) -> Optional[Dict[str, Any]]:
        proxy_index = self._proxy.index(proxy_row, 0)
        source_index = self._proxy.mapToSource(proxy_index)
        return self._model.row_data(source_index.row())

    # ------------------------------------------------------------------
    # 검색
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._proxy.set_query(text)
        self._refresh_result_title()

    # ------------------------------------------------------------------
    # 필터
    # ------------------------------------------------------------------

    def _configure_field_filter_menus(self) -> None:
        menu_style = """
            QMenu {
                background: #ffffff;
                color: #334155;
                border: 1px solid #d8dee8;
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
            QMenu::separator {
                height: 1px;
                background: #d8dee8;
                margin: 4px 6px;
            }
        """
        for field, btn in {"book": self.book_filter_btn, "label": self.label_filter_btn, "detail": self.detail_filter_btn}.items():
            menu = PersistentCheckMenu(self)
            menu.setStyleSheet(menu_style)
            menu.aboutToShow.connect(lambda f=field, m=menu: self._rebuild_field_menu(f, m))
            btn.setMenu(menu)
        self._update_filter_button_texts()

    def _rebuild_field_menu(self, field: str, menu: QMenu) -> None:
        menu.clear()
        value_counts = self._collect_filter_value_counts(field)
        values = sorted(value_counts.keys())
        selected_set = self._selected_filters.get(field, set())
        if not values:
            empty_action = menu.addAction("선택 가능한 값 없음")
            empty_action.setEnabled(False)
        else:
            select_all_action = menu.addAction("전체 선택")
            select_all_action.triggered.connect(lambda _=False, f=field: self._select_all_field_filters(f))
            field_name = {"book": "도서", "label": "라벨", "detail": "오류 유형"}.get(field, "필터")
            clear_action = menu.addAction(f"{field_name} 필터 초기화")
            clear_action.triggered.connect(lambda _=False, f=field: self._clear_field_filters(f))
            menu.addSeparator()
            for value in values:
                count = int(value_counts.get(value, 0))
                value_label = _truncate_chars(value, 90)
                action_label = f"{value_label} ({count})"
                action = menu.addAction(action_label)
                action.setCheckable(True)
                action.setChecked(value in selected_set)
                action.setToolTip(f"{value} ({count})")
                action.toggled.connect(lambda checked, f=field, v=value: self._toggle_field_filter(f, v, checked))

    def _select_all_field_filters(self, field: str) -> None:
        values = set(self._collect_filter_values(field))
        self._selected_filters[field] = values
        field_name = {"book": "도서", "label": "라벨", "detail": "오류 유형"}.get(field, field)
        self.ui_log_requested.emit(f"{field_name} 필터 전체 선택")
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()

    def _collect_filter_values(self, field: str) -> List[str]:
        return sorted(self._collect_filter_value_counts(field).keys())

    def _collect_filter_value_counts(self, field: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        model = self._model
        source_parent = QModelIndex()
        for row_index in range(model.rowCount()):
            if not self._proxy.row_matches_filters(row_index, source_parent, ignore_field=field):
                continue
            row = model.row_data(row_index) or {}
            if field == "book":
                value = str(row.get("book_id", "")).strip()
            elif field == "label":
                value = str(row.get("label", "")).strip()
            else:
                value = str(row.get("error_type", "")).strip()
            if value:
                counts[value] = counts.get(value, 0) + 1
        return counts

    def _toggle_field_filter(self, field: str, value: str, checked: bool) -> None:
        selected_set = self._selected_filters.setdefault(field, set())
        if checked:
            selected_set.add(value)
        else:
            selected_set.discard(value)
        field_name = {"book": "도서", "label": "라벨", "detail": "오류 유형"}.get(field, field)
        self.ui_log_requested.emit(f"{field_name} 필터 {'추가' if checked else '해제'}: {value}")
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()

    def _clear_field_filters(self, field: str) -> None:
        self._selected_filters[field] = set()
        field_name = {"book": "도서", "label": "라벨", "detail": "오류 유형"}.get(field, field)
        self.ui_log_requested.emit(f"{field_name} 필터 초기화")
        self._update_filter_button_texts()
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()

    def _update_filter_button_texts(self) -> None:
        book_n = len(self._selected_filters.get("book", set()))
        label_n = len(self._selected_filters.get("label", set()))
        detail_n = len(self._selected_filters.get("detail", set()))
        self.book_filter_btn.setText(f"도서({book_n}) ▼" if book_n else "도서 ▼")
        self.label_filter_btn.setText(f"라벨({label_n}) ▼" if label_n else "라벨 ▼")
        self.detail_filter_btn.setText(f"오류 유형({detail_n}) ▼" if detail_n else "오류 유형 ▼")

    # ------------------------------------------------------------------
    # 데이터 수신
    # ------------------------------------------------------------------

    def set_error_only_mode(self, enabled: bool) -> None:
        self._error_only_mode = bool(enabled)
        self._proxy.set_error_only(self._error_only_mode)
        self._refresh_result_title()

    def set_books(self, rows: List[Dict]) -> None:
        self._book_count = len(rows)
        self._refresh_result_title()

    def set_pages(self, rows: List[Dict]) -> None:
        self._rows_cache = [dict(row) for row in rows]
        for field in ("book", "label", "detail"):
            existing = set(self._collect_filter_values(field))
            self._selected_filters[field] = {v for v in self._selected_filters.get(field, set()) if v in existing}
        self._update_filter_button_texts()
        self._model.set_rows(rows)
        self._proxy.set_field_filters(dict(self._selected_filters))
        self._refresh_result_title()

    def _refresh_result_title(self) -> None:
        has_real_rows = any(
            int(str(row.get("shape_index", -1)).strip() or -1) >= 0
            for row in self._rows_cache
        )
        if not self._rows_cache or not has_real_rows:
            unit_text = "도서 단위"
            count = self._book_count
            suffix = "개"
            self.data_title.setText(f"검사 결과 ({unit_text}) - {count}{suffix}")
            return

        unit_text = "라벨 단위" if self._error_only_mode else "페이지 단위"
        if self._error_only_mode:
            count = self._proxy.rowCount()
            suffix = "개"
        else:
            count = self._proxy.rowCount()
            suffix = "개"

        self.data_title.setText(f"검사 결과 ({unit_text}) - {count}{suffix}")

    # ------------------------------------------------------------------
    # 외부 조회 API
    # ------------------------------------------------------------------

    def selected_row_keys(self) -> List[str]:
        keys = set()
        selection = self.page_table.selectionModel()
        if selection is None:
            return []
        selected_rows = {idx.row() for idx in selection.selectedIndexes()}
        for row in sorted(selected_rows):
            row_key = str(self._proxy.index(row, _COL_BOOK).data(Qt.UserRole + 10) or "")
            if row_key:
                keys.add(row_key)
        return sorted(keys)

    def current_page_key(self) -> Optional[str]:
        index = self.page_table.currentIndex()
        if not index.isValid():
            return None
        book_index = self._proxy.index(index.row(), _COL_BOOK)
        return str(book_index.data(Qt.UserRole + 12) or "") or None

    def current_book_id(self) -> Optional[str]:
        index = self.page_table.currentIndex()
        if not index.isValid():
            return None
        book_index = self._proxy.index(index.row(), _COL_BOOK)
        return str(book_index.data(Qt.UserRole + 11) or "") or None

    def _copy_selected_cells(self) -> None:
        selection = self.page_table.selectionModel()
        if selection is None:
            return
        indexes = selection.selectedIndexes()
        if not indexes:
            return

        rows = sorted({idx.row() for idx in indexes})
        cols = sorted({idx.column() for idx in indexes})
        if not rows or not cols:
            return

        selected_set = {(idx.row(), idx.column()) for idx in indexes}
        lines: List[str] = []
        for row in rows:
            cells: List[str] = []
            for col in cols:
                if (row, col) in selected_set:
                    text = str(self._proxy.index(row, col).data(Qt.DisplayRole) or "")
                else:
                    text = ""
                cells.append(text)
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))
        self.ui_log_requested.emit("선택 영역 텍스트 복사 완료")

    def visible_row_keys(self) -> List[str]:
        keys: List[str] = []
        for r in range(self._proxy.rowCount()):
            row_key = str(self._proxy.index(r, _COL_BOOK).data(Qt.UserRole + 10) or "")
            if row_key:
                keys.append(row_key)
        return keys
