from collections import defaultdict
from typing import Dict, List, Optional, Sequence

from PyQt5.QtCore import QRect, QRectF, Qt
from PyQt5.QtGui import QColor, QBrush, QKeySequence, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.tabs.pre_parse.features.base_state import is_error_base_state
from ..widgets.image_viewer import ImageViewerWidget

STAT_BOOKS = "도서 수"
STAT_PAGES = "페이지 수"
STAT_ERROR_PAGES = "오류 페이지"
STAT_TOTAL_ISSUES = "총 오류"
STAT_PASS_RATE = "통과율"
STAT_AVG_ERROR_RATE = "평균 오류율"

_RATIO_COLORS = [
    "#2563eb",
    "#0ea5e9",
    "#14b8a6",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#64748b",
]

STAT_TOTAL_LABELS = "__total_labels__"
STAT_ERROR_LABELS = "__error_labels__"

def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def _book_id_from_page_key(page_key: str) -> str:
    value = str(page_key or "").strip()
    if ":" in value:
        return value.split(":", 1)[0].strip()
    return value

def _book_id_from_row(row: dict) -> str:
    book_id = str(row.get("book_id", "")).strip()
    if book_id:
        return book_id
    return _book_id_from_page_key(str(row.get("page_no", "")))

def _book_id_from_issue(issue: dict) -> str:
    book_id = str(issue.get("book_id", "")).strip()
    if book_id:
        return book_id
    return _book_id_from_page_key(str(issue.get("page_no", "")))

def _issue_category(issue: dict) -> str:
    for key in ("error_type", "description", "check_id"):
        value = str(issue.get(key, "")).strip()
        if value:
            return value
    return "기타"

def _percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    q = max(0.0, min(1.0, q))
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)

def _display_range(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    lower = min(values)
    upper = max(values)
    if upper <= lower:
        upper = lower + 1.0
    return lower, upper

class CopyableStatsTableWidget(QTableWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(18)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: none;
                color: #111827;
            }
            QHeaderView::section {
                background: #ffffff;
                color: #334155;
                border: none;
                border-bottom: 1px solid #d8dee8;
                padding: 1px 5px;
                font-weight: 600;
                font-size: 11px;
            }
            QTableCornerButton::section {
                background: #ffffff;
                border: none;
                border-right: 1px solid #d8dee8;
                border-bottom: 1px solid #d8dee8;
            }
            QTableWidget::item {
                padding: 0px 3px;
                border: none;
            }
            QTableWidget::item:selected:active,
            QTableWidget::item:selected:!active {
                background: #dbeafe;
                color: #111827;
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
                height: 0px;
            }
            """
        )

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.matches(QKeySequence.Copy):
            self._copy_selected_cells()
            event.accept()
            return
        super().keyPressEvent(event)

    def _copy_selected_cells(self) -> None:
        indexes = self.selectedIndexes()
        if not indexes:
            return

        rows = sorted({index.row() for index in indexes})
        columns = sorted({index.column() for index in indexes})
        selected = {(index.row(), index.column()) for index in indexes}

        lines: List[str] = []
        for row in rows:
            cells: List[str] = []
            for column in columns:
                if (row, column) in selected:
                    item = self.item(row, column)
                    cells.append("" if item is None else str(item.text()))
                else:
                    cells.append("")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

class StackedHorizontalBarWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[dict] = []
        self._segment_regions: List[tuple[QRect, str]] = []
        self._empty_message = "데이터 없음"
        self.setMouseTracking(True)
        self.setMinimumHeight(20)
        self.setMaximumHeight(24)

    def set_empty_message(self, message: str) -> None:
        self._empty_message = str(message or "").strip() or "데이터 없음"
        self.update()

    @staticmethod
    def _compute_segment_widths(total_width: int, counts: Sequence[int]) -> List[int]:
        widths = [0] * len(counts)
        positive_indexes = [index for index, count in enumerate(counts) if count > 0]
        if total_width <= 0 or not positive_indexes:
            return widths

        visible_slots = min(total_width, len(positive_indexes))
        reserved = [0] * len(counts)
        for index in positive_indexes[:visible_slots]:
            reserved[index] = 1

        remaining_width = max(0, total_width - visible_slots)
        total_count = sum(counts[index] for index in positive_indexes) or 1
        raw_extras = [0.0] * len(counts)

        for index in positive_indexes:
            raw_extras[index] = remaining_width * (counts[index] / total_count)
            widths[index] = reserved[index] + int(raw_extras[index])

        assigned = sum(widths)
        remainder = max(0, total_width - assigned)
        order = sorted(
            positive_indexes,
            key=lambda index: (raw_extras[index] - int(raw_extras[index]), counts[index], -index),
            reverse=True,
        )
        for index in order[:remainder]:
            widths[index] += 1
        return widths

    def set_rows(self, rows: Sequence[dict]) -> None:
        self._rows = [dict(row) for row in rows]
        self._segment_regions = []
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._segment_regions = []

        rect = self.rect()
        painter.fillRect(rect, QColor("#ffffff"))

        if not self._rows:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(rect, Qt.AlignCenter, self._empty_message)
            return

        bar_height = 8
        top = max(0, (rect.height() - bar_height) // 2)
        bar_rect = QRect(rect.left(), top, rect.width(), bar_height)
        radius = bar_rect.height() / 2.0
        bar_path = QPainterPath()
        bar_path.addRoundedRect(QRectF(bar_rect), radius, radius)
        painter.setPen(Qt.NoPen)
        painter.fillPath(bar_path, QColor("#e5e7eb"))

        counts = [max(int(row.get("count", 0)), 0) for row in self._rows]
        widths = self._compute_segment_widths(bar_rect.width(), counts)
        positive_indexes = [index for index, width in enumerate(widths) if width > 0]

        left = bar_rect.left()
        painter.save()
        painter.setClipPath(bar_path)
        for index, row in enumerate(self._rows):
            label = str(row.get("label", "")).strip()
            count = counts[index]
            ratio = float(row.get("ratio", 0.0))
            color = QColor(str(row.get("color", _RATIO_COLORS[index % len(_RATIO_COLORS)])))
            width = widths[index]
            if width <= 0:
                continue
            if positive_indexes and index == positive_indexes[-1]:
                width = bar_rect.right() - left + 1

            segment_rect = QRect(left, bar_rect.top(), width, bar_rect.height())
            painter.fillRect(segment_rect, color)
            self._segment_regions.append((segment_rect, f"{label}\n오류 수: {count:,}건\n비율: {ratio:.1f}%"))
            left += width
        painter.restore()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        for rect, text in self._segment_regions:
            if rect.contains(event.pos()):
                QToolTip.showText(event.globalPos(), text, self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        QToolTip.hideText()
        super().leaveEvent(event)

class RateDistributionWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._values: List[float] = []
        self._labels: List[str] = []
        self._threshold_lines: List[tuple[float, str, str]] = []
        self._bar_regions: List[tuple[QRect, str]] = []
        self._empty_message = "도서별 데이터 없음"
        self.setMouseTracking(True)
        self.setMinimumHeight(148)
        self.setMaximumHeight(148)

    def set_empty_message(self, message: str) -> None:
        self._empty_message = str(message or "").strip() or "도서별 데이터 없음"
        self.update()

    def set_data(
        self,
        values: Sequence[float],
        labels: Sequence[str],
        threshold_lines: Sequence[tuple[float, str, str]],
    ) -> None:
        self._values = [float(value) for value in values]
        self._labels = [str(label or "") for label in labels]
        self._threshold_lines = [(float(value), str(text), str(color)) for value, text, color in threshold_lines]
        self._bar_regions = []
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._bar_regions = []

        rect = self.rect().adjusted(8, 8, -8, -12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f8fafc"))
        painter.drawRoundedRect(rect, 8, 8)

        if not self._values:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(rect, Qt.AlignCenter, self._empty_message)
            return

        display_min, display_max = _display_range(self._values)
        value_range = max(display_max - display_min, 1e-9)
        sorted_values = sorted(self._values)
        q1 = _percentile(sorted_values, 0.25)
        q3 = _percentile(sorted_values, 0.75)
        iqr = max(q3 - q1, 0.0)
        if iqr > 0:
            estimated_width = max(2 * iqr / max(len(self._values) ** (1 / 3), 1.0), value_range / 8)
            bin_count = max(5, min(10, int(round(value_range / estimated_width)) or 1))
        else:
            bin_count = max(5, min(10, len({round(value, 4) for value in self._values}) or len(self._values)))
        bin_width = value_range / max(bin_count, 1)
        counts = [0] * bin_count
        bins: List[List[str]] = [[] for _ in range(bin_count)]

        for value, label in zip(self._values, self._labels):
            clamped = min(max(value, display_min), display_max)
            index = min(int((clamped - display_min) / bin_width), bin_count - 1)
            counts[index] += 1
            if label:
                bins[index].append(label)

        chart_rect = rect.adjusted(12, 30, -12, -28)
        max_count = max(counts) or 1
        gap = 4
        usable_width = max(chart_rect.width() - gap * (bin_count - 1), bin_count)
        bar_width = max(8, usable_width // bin_count)

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(chart_rect.left(), chart_rect.bottom(), chart_rect.right(), chart_rect.bottom())
        painter.drawLine(chart_rect.left(), chart_rect.top(), chart_rect.left(), chart_rect.bottom())

        for index, count in enumerate(counts):
            bar_height = int((count / max_count) * chart_rect.height())
            x = chart_rect.left() + index * (bar_width + gap)
            y = chart_rect.bottom() - bar_height
            bar_rect = QRect(x, y, bar_width, max(1, bar_height))
            painter.fillRect(bar_rect, QColor("#93c5fd"))

            start_value = display_min + index * bin_width
            end_value = display_min + (index + 1) * bin_width
            tooltip_lines = [
                f"구간: {start_value:.1f}% ~ {end_value:.1f}%",
                f"도서 수: {count}권",
            ]
            if bins[index]:
                tooltip_lines.append("도서:")
                tooltip_lines.extend(sorted(set(bins[index])))
            self._bar_regions.append((bar_rect, "\n".join(tooltip_lines)))

        for value, label, color in self._threshold_lines:
            ratio = (value - display_min) / value_range
            ratio = max(0.0, min(1.0, ratio))
            x = int(chart_rect.left() + ratio * chart_rect.width())
            painter.setPen(QPen(QColor(color), 1, Qt.DashLine))
            painter.drawLine(x, chart_rect.top(), x, chart_rect.bottom())
            self._bar_regions.insert(0, (QRect(x - 4, chart_rect.top(), 8, chart_rect.height()), f"{label} 값({value:.1f}%)"))

        painter.setPen(QColor("#64748b"))
        painter.drawText(rect.adjusted(12, rect.height() - 18, -12, 0), Qt.AlignLeft | Qt.AlignVCenter, f"{display_min:.1f}%")
        painter.drawText(
            rect.adjusted(12, rect.height() - 18, -12, 0),
            Qt.AlignCenter | Qt.AlignVCenter,
            f"{((display_min + display_max) / 2):.1f}%",
        )
        painter.drawText(
            rect.adjusted(12, rect.height() - 18, -12, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            f"{display_max:.1f}%",
        )

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        for rect, text in self._bar_regions:
            if rect.contains(event.pos()):
                QToolTip.showText(event.globalPos(), text, self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        QToolTip.hideText()
        super().leaveEvent(event)

class StatsPanelWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kpi_title_labels: Dict[str, QLabel] = {}
        self._kpi_value_labels: Dict[str, QLabel] = {}
        self._kpi_detail_labels: Dict[str, QLabel] = {}
        self._section_title_labels: Dict[str, QLabel] = {}
        self._section_subtitle_labels: Dict[str, QLabel] = {}

        self.error_type_bar = StackedHorizontalBarWidget()
        self.error_type_table = CopyableStatsTableWidget()
        self.error_rate_chart = RateDistributionWidget()
        self.book_table = CopyableStatsTableWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #ffffff; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: #ffffff;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 0)
        content_layout.setSpacing(8)
        content_layout.addWidget(self._build_kpi_section())
        content_layout.addWidget(self._build_error_type_section())
        content_layout.addWidget(self._build_book_section())
        content_layout.addStretch(1)
        scroll.setWidget(content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def update_panel(
        self,
        stats: dict,
        rows: List[dict],
        issues: List[dict],
        label_rows: Optional[List[dict]] = None,
    ) -> None:
        label_rows = label_rows or []
        self._apply_panel_labels()
        error_type_rows = self._build_error_type_rows(issues)
        book_rows = self._build_book_rows(rows, issues)

        total_books = int(stats.get(STAT_BOOKS, 0))
        total_pages = int(stats.get(STAT_PAGES, len(rows)))
        error_pages = int(stats.get(STAT_ERROR_PAGES, 0))
        page_error_rate = (error_pages / total_pages * 100.0) if total_pages else 0.0

        total_labels = int(stats.get(STAT_TOTAL_LABELS, 0))
        if total_labels <= 0:
            total_labels = sum(1 for row in label_rows if _safe_int(row.get("shape_index", -1)) >= 0)
        error_labels = int(stats.get(STAT_ERROR_LABELS, 0))
        if error_labels <= 0:
            error_labels = sum(
                1
                for row in label_rows
                if _safe_int(row.get("shape_index", -1)) >= 0
                and (
                    is_error_base_state(row.get("base_state"))
                    or str(row.get("error_detail", "")).strip()
                )
            )
        if error_labels <= 0:
            error_labels = len(issues)
        if total_labels <= 0 and error_labels > 0:
            total_labels = error_labels
        label_error_rate = (error_labels / total_labels * 100.0) if total_labels else 0.0

        self._set_kpi_value("books", f"{total_books:,}")
        self._set_kpi_detail("books", "")
        self._set_kpi_value("pages", f"{page_error_rate:.1f}%")
        self._set_kpi_detail("pages", f"{error_pages:,}/{total_pages:,}")
        self._set_kpi_value("labels", f"{label_error_rate:.1f}%")
        self._set_kpi_detail("labels", f"{error_labels:,}/{total_labels:,}")

        self._populate_error_type_section(error_type_rows)
        self._populate_book_section(book_rows)

    def _apply_panel_labels(self) -> None:
        self._kpi_title_labels["books"].setText("전체 도서 수")
        self._kpi_title_labels["pages"].setText("오류율(페이지)")
        self._kpi_title_labels["labels"].setText("오류율(라벨)")
        self._section_title_labels["type"].setText("유형별 오류 통계")
        self._section_subtitle_labels["type"].setText("오류 비율과 집계를 함께 확인합니다.")
        self._section_title_labels["book"].setText("도서별 오류 통계")
        self._section_subtitle_labels["book"].setText("오류율 분포와 주요 지점을 그래프 안에서 함께 확인합니다.")
        self.error_type_bar.set_empty_message("오류 유형 데이터 없음")
        self.error_rate_chart.set_empty_message("도서별 오류율 데이터 없음")

    def _build_section_frame(self, section_id: str, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("statsSectionCard")
        frame.setStyleSheet(
            """
            QFrame#statsSectionCard {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 8px;
            }
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        self._section_title_labels[section_id] = title_label
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet("color: #64748b; font-size: 11px;")
        subtitle_label.setVisible(bool(subtitle))
        self._section_subtitle_labels[section_id] = subtitle_label
        layout.addWidget(subtitle_label)

        return frame, layout

    def _build_kpi_section(self) -> QWidget:
        section, layout = self._build_section_frame("overview", "개요", "")
        if "overview" in self._section_subtitle_labels:
            self._section_subtitle_labels["overview"].setVisible(False)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        cards = (
            ("books", "전체 도서 수"),
            ("pages", "오류율(페이지)"),
            ("labels", "오류율(라벨)"),
        )
        for index, (card_id, title) in enumerate(cards):
            grid.addWidget(self._build_overview_card(card_id, title), 0, index)
        layout.addLayout(grid)
        return section

    def _build_error_type_section(self) -> QWidget:
        section, layout = self._build_section_frame(
            "type",
            "유형별 오류 통계",
            "오류 비율과 집계를 함께 확인합니다.",
        )
        layout.addWidget(self.error_type_bar)
        layout.addWidget(self.error_type_table)
        return section

    def _build_book_section(self) -> QWidget:
        section, layout = self._build_section_frame(
            "book",
            "도서별 오류 통계",
            "오류율 분포와 주요 지점을 그래프 안에서 함께 확인합니다.",
        )
        layout.addWidget(self.error_rate_chart)
        layout.addWidget(self.book_table)
        return section

    def _build_overview_card(self, card_id: str, title: str) -> QWidget:
        card = QFrame()
        card.setObjectName("statsKpiCard")
        card.setStyleSheet(
            """
            QFrame#statsKpiCard {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
        value_label = QLabel("0")
        value_label.setStyleSheet("color: #111827; font-size: 16px; font-weight: 700;")
        detail_label = QLabel("")
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #64748b; font-size: 11px;")
        detail_label.setVisible(False)

        self._kpi_title_labels[card_id] = title_label
        self._kpi_value_labels[card_id] = value_label
        self._kpi_detail_labels[card_id] = detail_label

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(detail_label)
        layout.addStretch(1)
        return card

    def _set_kpi_value(self, key: str, value: str) -> None:
        self._kpi_value_labels[key].setText(value)

    def _set_kpi_detail(self, key: str, value: str) -> None:
        label = self._kpi_detail_labels[key]
        label.setText(value)
        label.setVisible(bool(value))

    def _build_error_type_rows(self, issues: List[dict]) -> List[dict]:
        counts: Dict[str, int] = defaultdict(int)
        page_sets: Dict[str, set] = defaultdict(set)
        total = len(issues)
        for issue in issues:
            category = _issue_category(issue)
            counts[category] += 1
            page_key = str(issue.get("page_no", "")).strip()
            if page_key:
                page_sets[category].add(page_key)

        rows: List[dict] = []
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        for index, (category, count) in enumerate(ordered):
            rows.append(
                {
                    "label": category,
                    "count": count,
                    "pages": len(page_sets.get(category, set())),
                    "ratio": (count / total * 100.0) if total else 0.0,
                    "color": _RATIO_COLORS[index % len(_RATIO_COLORS)],
                }
            )
        return rows

    def _build_book_rows(self, rows: List[dict], issues: List[dict]) -> List[dict]:
        page_counts: Dict[str, int] = defaultdict(int)
        error_page_counts: Dict[str, int] = defaultdict(int)
        total_errors: Dict[str, int] = defaultdict(int)
        error_type_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for row in rows:
            book_id = _book_id_from_row(row)
            if not book_id:
                continue
            page_counts[book_id] += 1
            issue_count = _safe_int(row.get("issue_count", 0))
            if issue_count > 0:
                error_page_counts[book_id] += 1
            total_errors[book_id] += issue_count

        for issue in issues:
            book_id = _book_id_from_issue(issue)
            if not book_id:
                continue
            error_type_counts[book_id][_issue_category(issue)] += 1

        book_rows: List[dict] = []
        for book_id in sorted(page_counts.keys()):
            pages = page_counts[book_id]
            error_pages = error_page_counts.get(book_id, 0)
            error_rate = (error_pages / pages * 100.0) if pages else 0.0
            book_rows.append(
                {
                    "book_id": book_id,
                    "pages": pages,
                    "error_pages": error_pages,
                    "total_errors": total_errors.get(book_id, 0),
                    "error_rate": error_rate,
                    "error_type_counts": dict(error_type_counts.get(book_id, {})),
                }
            )

        book_rows.sort(
            key=lambda item: (
                -float(item["error_rate"]),
                -int(item["total_errors"]),
                str(item["book_id"]),
            )
        )
        return book_rows

    def _populate_error_type_section(self, rows: List[dict]) -> None:
        self.error_type_bar.set_rows(rows)
        headers = ["", "오류 유형", "오류 수", "오류 페이지 수", "비중"]
        self._prepare_table(self.error_type_table, headers, len(rows), first_column_stretch=False)
        header = self.error_type_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.error_type_table.setColumnWidth(0, 22)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for column in range(2, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        for row_index, row in enumerate(rows):
            color_item = self._set_table_item(self.error_type_table, row_index, 0, "■")
            color_item.setForeground(QBrush(QColor(str(row.get("color", "#94a3b8")))))
            color_item.setToolTip(str(row["label"]))
            self._set_table_item(self.error_type_table, row_index, 1, str(row["label"]), align_left=True)
            self._set_table_item(self.error_type_table, row_index, 2, f"{int(row['count']):,}")
            self._set_table_item(self.error_type_table, row_index, 3, f"{int(row['pages']):,}")
            self._set_table_item(self.error_type_table, row_index, 4, f"{float(row['ratio']):.1f}%")

        self.error_type_table.setMinimumHeight(max(110, min(220, 30 + len(rows) * 18)))

    def _populate_book_section(self, rows: List[dict]) -> None:
        error_rates = [float(row.get("error_rate", 0.0)) for row in rows]
        labels = [str(row.get("book_id", "")) for row in rows]
        sorted_rates = sorted(error_rates)

        minimum = _percentile(sorted_rates, 0.0)
        q1 = _percentile(sorted_rates, 0.25)
        median = _percentile(sorted_rates, 0.5)
        q3 = _percentile(sorted_rates, 0.75)
        maximum = _percentile(sorted_rates, 1.0)

        self.error_rate_chart.set_data(
            error_rates,
            labels,
            threshold_lines=[
                (minimum, "최소", "#94a3b8"),
                (q1, "25%", "#f59e0b"),
                (median, "중앙값", "#2563eb"),
                (q3, "75%", "#ef4444"),
                (maximum, "최대", "#475569"),
            ],
        )

        headers = ["도서", "페이지 수", "오류 페이지 수", "오류율", "총 오류"]
        self._prepare_table(self.book_table, headers, len(rows), first_column_stretch=True)

        for row_index, row in enumerate(rows):
            item = self._set_table_item(self.book_table, row_index, 0, str(row["book_id"]), align_left=True)
            self._apply_error_rate_emphasis(item, float(row["error_rate"]), q1, q3)
            self._set_table_item(self.book_table, row_index, 1, f"{int(row['pages']):,}")
            error_pages_item = self._set_table_item(self.book_table, row_index, 2, f"{int(row['error_pages']):,}")
            breakdown = row.get("error_type_counts", {})
            if isinstance(breakdown, dict) and breakdown:
                tooltip_lines = [f"{key}: {int(value):,}건" for key, value in sorted(breakdown.items(), key=lambda item: (-int(item[1]), str(item[0])))]
                error_pages_item.setToolTip("\n".join(tooltip_lines))
            rate_item = self._set_table_item(self.book_table, row_index, 3, f"{float(row['error_rate']):.1f}%")
            self._apply_error_rate_emphasis(rate_item, float(row["error_rate"]), q1, q3)
            self._set_table_item(self.book_table, row_index, 4, f"{int(row['total_errors']):,}")

        self.book_table.setMinimumHeight(max(120, min(240, 30 + len(rows) * 18)))

    def _prepare_table(
        self,
        table: CopyableStatsTableWidget,
        headers: Sequence[str],
        row_count: int,
        *,
        first_column_stretch: bool,
    ) -> None:
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setRowCount(row_count)
        table.verticalHeader().setDefaultSectionSize(19)

        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        if first_column_stretch:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for column in range(1, len(headers)):
                header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        else:
            for column in range(len(headers)):
                header.setSectionResizeMode(column, QHeaderView.Stretch)

    def _set_table_item(
        self,
        table: CopyableStatsTableWidget,
        row: int,
        column: int,
        text: str,
        *,
        align_left: bool = False,
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(int((Qt.AlignLeft if align_left else Qt.AlignCenter) | Qt.AlignVCenter))
        item.setToolTip(text)
        table.setItem(row, column, item)
        return item

    def _apply_error_rate_emphasis(self, item: QTableWidgetItem, value: float, q1: float, q3: float) -> None:
        if value <= q1:
            item.setBackground(QBrush(QColor("#e0f2fe")))
            item.setForeground(QBrush(QColor("#075985")))
        elif value >= q3:
            item.setBackground(QBrush(QColor("#fee2e2")))
            item.setForeground(QBrush(QColor("#b91c1c")))

        font = item.font()
        if value <= q1 or value >= q3:
            font.setBold(True)
        item.setFont(font)

class RightPanelWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.image_viewer = ImageViewerWidget()
        self.stats_panel = StatsPanelWidget()

        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.image_viewer, 1)

        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.addWidget(self.stats_panel)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("rightTabs")
        self.tabs.addTab(preview_tab, "미리보기")
        self.tabs.addTab(stats_tab, "통계")
        self.tabs.setStyleSheet(
            """
            QTabWidget#rightTabs::pane {
                border: 1px solid #dfe5ef;
                border-radius: 0px;
                top: -1px;
                background: #ffffff;
            }
            QTabWidget#rightTabs QTabBar {
                left: 6px;
            }
            QTabWidget#rightTabs QTabBar::tab {
                background: #eef1f5;
                color: #1f2937;
                border: 1px solid #d8dee8;
                border-radius: 0px;
                font-weight: 600;
                padding: 4px 14px;
                min-width: 56px;
                margin-right: 2px;
            }
            QTabWidget#rightTabs QTabBar::tab:selected {
                background: #ffffff;
                border-bottom: 1px solid #ffffff;
            }
            QTabWidget#rightTabs QTabBar::tab:!selected {
                margin-top: 1px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tabs)

        self.update_dashboard(stats={}, rows=[], issues=[], label_rows=[])

    def update_dashboard(self, *, stats: dict, rows: List[dict], issues: List[dict], label_rows: Optional[List[dict]] = None) -> None:
        self.stats_panel.update_panel(stats, rows, issues, label_rows)
