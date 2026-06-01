from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..widgets.info_dot_button import InfoDotButton
from ..ui_shared import (
    _HEADER_COMPACT_THRESHOLD,
    _HEADER_LONG_MIN_WIDTH,
    _HEADER_SIDE_PADDING,
    _PANEL_MARGINS,
    _PANEL_SPACING,
    _TABLE_STYLE,
    _ZERO_THRESHOLD_RULE_KEYS,
    RESULT_HEADERS,
    _rank_boundaries,
    build_result_help_tooltip,
    normalize_highlight_rules,
)

class RawDataAnalysisCenterPanel(QWidget):
    cell_selected = pyqtSignal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.highlight_rules = normalize_highlight_rules()
        self.data_title = QLabel("\uAC80\uC0AC \uACB0\uACFC (\uB3C4\uC11C \uB2E8\uC704) - 0\uAD8C")
        self.data_title.setStyleSheet("font-weight: 600; color: #111827;")

        info_btn = InfoDotButton()
        info_btn.setText("i")
        info_btn.setToolTip(build_result_help_tooltip())
        info_btn.setFixedSize(18, 18)
        info_btn.setStyleSheet(
            """
            QToolButton {
                color: #64748b;
                background: #e5e7eb;
                border: 1px solid #d8dee8;
                border-radius: 9px;
                font-size: 10px;
                font-weight: 700;
                padding: 0;
            }
            QToolButton:hover {
                background: #dce3ea;
            }
            """
        )

        self.result_table = QTableWidget(0, len(RESULT_HEADERS))
        self.result_table.setHorizontalHeaderLabels(RESULT_HEADERS)
        self.result_table.setAlternatingRowColors(False)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.result_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.verticalHeader().setDefaultSectionSize(22)
        self.result_table.currentCellChanged.connect(self._emit_current_cell)
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(28)
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setTextElideMode(Qt.ElideRight)
        self.result_table.setStyleSheet(_TABLE_STYLE)
        for col_index, header_text in enumerate(RESULT_HEADERS):
            item = self.result_table.horizontalHeaderItem(col_index)
            if item is not None:
                item.setToolTip(str(header_text))

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title_row.addWidget(self.data_title)
        title_row.addWidget(info_btn, alignment=Qt.AlignVCenter)
        title_row.addStretch(1)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #d8dee8;")

        root = QVBoxLayout(self)
        root.setContentsMargins(*_PANEL_MARGINS)
        root.setSpacing(_PANEL_SPACING)
        root.addLayout(title_row)
        root.addWidget(divider)
        root.addWidget(self.result_table, 1)
        QTimer.singleShot(0, self._apply_header_width_policy)

    def set_highlight_rules(self, rules: Optional[dict] = None) -> None:
        self.highlight_rules = normalize_highlight_rules(rules)

    def _emit_current_cell(self, current_row: int, current_col: int, _previous_row: int, _previous_col: int) -> None:
        if current_row >= 0 and current_col >= 0:
            self.cell_selected.emit(current_row, current_col)

    def set_rows(self, rows: List[List[str]]) -> None:
        self.result_table.clearContents()
        self.result_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, cell in enumerate(row[: len(RESULT_HEADERS)]):
                item = QTableWidgetItem(str(cell))
                item.setTextAlignment(Qt.AlignCenter)
                self.result_table.setItem(row_index, col_index, item)
        self._apply_highlighting(rows)
        self._apply_header_width_policy()
        self.data_title.setText(
            f"\uAC80\uC0AC \uACB0\uACFC (\uB3C4\uC11C \uB2E8\uC704) - {len(rows)}\uAD8C"
        )

    def _apply_highlighting(self, rows: List[List[str]]) -> None:
        if not rows:
            return

        for col_index, header in enumerate(RESULT_HEADERS[1:], start=1):
            numeric_rows: List[tuple[int, float]] = []
            for row_index, row in enumerate(rows):
                if col_index >= len(row):
                    continue
                try:
                    numeric_rows.append((row_index, float(str(row[col_index]).strip())))
                except ValueError:
                    continue

            if not numeric_rows:
                continue

            sorted_rows = sorted(numeric_rows, key=lambda item: item[1])
            low_boundary, high_boundary = _rank_boundaries(
                [value for _, value in numeric_rows],
                lower_rank_percent=self.highlight_rules["lower_rank_percent"],
                upper_rank_percent=self.highlight_rules["upper_rank_percent"],
            )

            for row_index, value in sorted_rows:
                if value > low_boundary:
                    continue
                item = self.result_table.item(row_index, col_index)
                if item is not None:
                    item.setBackground(QBrush(QColor("#fee2e2")))

            for row_index, value in sorted_rows:
                if value < high_boundary:
                    continue
                item = self.result_table.item(row_index, col_index)
                if item is not None:
                    item.setBackground(QBrush(QColor("#dcfce7")))

            if header == "띄어쓰기":
                space_min = self.highlight_rules["space_min"]
                space_max = self.highlight_rules["space_max"]
                for row_index, value in numeric_rows:
                    if space_min <= value <= space_max:
                        continue
                    item = self.result_table.item(row_index, col_index)
                    if item is None:
                        continue
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QBrush(QColor("#b91c1c")))
            elif header in _ZERO_THRESHOLD_RULE_KEYS:
                threshold = self.highlight_rules[_ZERO_THRESHOLD_RULE_KEYS[header]]
                for row_index, value in numeric_rows:
                    if value <= threshold:
                        continue
                    item = self.result_table.item(row_index, col_index)
                    if item is None:
                        continue
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QBrush(QColor("#b45309")))

    def _apply_header_width_policy(self) -> None:
        available_width = max(0, self.result_table.viewport().width() - 2)
        if available_width <= 0:
            return

        header_font_metrics = self.result_table.horizontalHeader().fontMetrics()
        preferred_widths: List[int] = []
        minimum_widths: List[int] = []
        for col_index, title in enumerate(RESULT_HEADERS):
            header_width = header_font_metrics.horizontalAdvance(str(title)) + _HEADER_SIDE_PADDING
            preferred_widths.append(header_width)
            if header_width <= _HEADER_COMPACT_THRESHOLD:
                minimum_widths.append(header_width)
            else:
                minimum_widths.append(_HEADER_LONG_MIN_WIDTH)

        final_widths = list(preferred_widths)
        overflow = sum(final_widths) - available_width
        if overflow > 0:
            shrinkable_indices = [idx for idx, width in enumerate(preferred_widths) if width > _HEADER_COMPACT_THRESHOLD]
            while overflow > 0 and shrinkable_indices:
                changed = False
                for idx in sorted(shrinkable_indices, key=lambda i: final_widths[i], reverse=True):
                    if overflow <= 0:
                        break
                    if final_widths[idx] <= minimum_widths[idx]:
                        continue
                    final_widths[idx] -= 1
                    overflow -= 1
                    changed = True
                if not changed:
                    break

        for col_index, width in enumerate(final_widths):
            self.result_table.setColumnWidth(col_index, width)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_header_width_policy()
