from __future__ import annotations

import statistics
from typing import List, Optional, Sequence

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..widgets.image_viewer import ImageViewerWidget
from ..ui_shared import (
    _PREVIEW_NAV_BTN_STYLE,
    _RIGHT_TAB_STYLE,
    _ZERO_THRESHOLD_HEADERS,
    _ZERO_THRESHOLD_RULE_KEYS,
    DistributionMiniChart,
    RESULT_HEADERS,
    _rank_boundaries,
    book_metric_numeric_value,
    format_metric_value,
    normalize_highlight_rules,
)

class RawDataAnalysisRightPanel(QWidget):
    preview_index_changed = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.highlight_rules = normalize_highlight_rules()
        self.preview_items: List[dict] = []
        self.preview_index = -1

        self.tabs = QTabWidget()
        self.tabs.setObjectName("rightTabs")
        self.tabs.setStyleSheet(_RIGHT_TAB_STYLE)

        self.image_viewer = ImageViewerWidget()
        self.preview_title_label = QLabel("페이지 미리보기")
        self.preview_title_label.setStyleSheet("font-weight: 600; color: #111827;")
        self.preview_meta_label = QLabel("셀을 선택하면 관련 페이지를 확인할 수 있습니다.")
        self.preview_meta_label.setWordWrap(True)
        self.preview_meta_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.preview_status_label = QLabel("0 / 0")
        self.preview_status_label.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
        self.preview_status_label.setFixedHeight(24)
        self.preview_status_label.setMinimumWidth(68)
        self.preview_status_label.setAlignment(Qt.AlignCenter)
        self.preview_prev_btn = QPushButton("이전")
        self.preview_next_btn = QPushButton("다음")
        self.preview_prev_btn.setStyleSheet(_PREVIEW_NAV_BTN_STYLE)
        self.preview_next_btn.setStyleSheet(_PREVIEW_NAV_BTN_STYLE)
        self.preview_prev_btn.setFixedHeight(24)
        self.preview_next_btn.setFixedHeight(24)
        self.preview_prev_btn.setMinimumWidth(72)
        self.preview_next_btn.setMinimumWidth(72)
        self.preview_prev_btn.clicked.connect(self._show_prev_preview)
        self.preview_next_btn.clicked.connect(self._show_next_preview)
        self.preview_prev_btn.setEnabled(False)
        self.preview_next_btn.setEnabled(False)

        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)

        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(4)
        nav_row.addStretch(1)
        nav_row.addWidget(self.preview_prev_btn, 0, Qt.AlignVCenter)
        nav_row.addWidget(self.preview_status_label, 0, Qt.AlignVCenter)
        nav_row.addWidget(self.preview_next_btn, 0, Qt.AlignVCenter)
        nav_row.addStretch(1)

        preview_layout.addWidget(self.image_viewer, 1)
        preview_layout.addLayout(nav_row)

        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(0)
        self.stats_scroll = QScrollArea()
        self.stats_scroll.setWidgetResizable(True)
        self.stats_scroll.setFrameShape(QFrame.NoFrame)
        self.stats_scroll.setStyleSheet(
            """
            QScrollArea { background: #ffffff; border: none; }
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
            """
        )
        self.stats_container = QWidget()
        self.stats_container.setStyleSheet("background: #ffffff;")
        self.stats_cards_layout = QVBoxLayout(self.stats_container)
        self.stats_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_cards_layout.setSpacing(8)
        self.stats_scroll.setWidget(self.stats_container)
        stats_layout.addWidget(self.stats_scroll)

        self.tabs.addTab(preview_tab, "미리보기")
        self.tabs.addTab(stats_tab, "통계")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.tabs)
        self.set_stats_rows([])

    def set_highlight_rules(self, rules: Optional[dict] = None) -> None:
        self.highlight_rules = normalize_highlight_rules(rules)

    def set_preview_items(self, items: List[dict], *, book_name: str, header: str) -> None:
        self.preview_items = list(items)
        self.preview_index = 0 if self.preview_items else -1
        if not self.preview_items:
            title = f"{book_name} · {header}" if book_name else header
            self.preview_title_label.setText(title or "페이지 미리보기")
            self.preview_meta_label.setText("셀을 선택하면 관련 페이지를 확인할 수 있습니다.")
            self.preview_status_label.setText("0 / 0")
            self.preview_prev_btn.setEnabled(False)
            self.preview_next_btn.setEnabled(False)
            self.image_viewer.set_empty_message("이미지 없음")
            self.image_viewer.set_image("")
            self.image_viewer.set_bboxes([])
            return
        self._update_preview_navigation()
        self.preview_index_changed.emit(self.preview_index)

    def set_preview_placeholder(self, *, title: str, meta_text: str, empty_message: str) -> None:
        self.preview_items = []
        self.preview_index = -1
        self.preview_title_label.setText(title)
        self.preview_meta_label.setText(meta_text)
        self.preview_status_label.setText("0 / 0")
        self.preview_prev_btn.setEnabled(False)
        self.preview_next_btn.setEnabled(False)
        self.image_viewer.set_empty_message(empty_message)
        self.image_viewer.set_image("")
        self.image_viewer.set_bboxes([])

    def show_preview_page(
        self,
        *,
        image_path: str,
        bboxes: List[dict],
        title: str,
        meta_text: str,
        empty_message: str = "이미지 없음",
    ) -> None:
        self.image_viewer.set_empty_message(empty_message)
        self.preview_title_label.setText(title)
        self.preview_meta_label.setText(meta_text)
        self.image_viewer.set_image(image_path)
        self.image_viewer.set_bboxes(bboxes)

    def _update_preview_navigation(self) -> None:
        total = len(self.preview_items)
        if total <= 0 or self.preview_index < 0:
            self.preview_status_label.setText("0 / 0")
            self.preview_prev_btn.setEnabled(False)
            self.preview_next_btn.setEnabled(False)
            return
        self.preview_status_label.setText(f"{self.preview_index + 1} / {total}")
        enabled = total > 1
        self.preview_prev_btn.setEnabled(enabled)
        self.preview_next_btn.setEnabled(enabled)

    def _show_prev_preview(self) -> None:
        total = len(self.preview_items)
        if total <= 0:
            return
        self.preview_index = (self.preview_index - 1) % total
        self._update_preview_navigation()
        self.preview_index_changed.emit(self.preview_index)

    def _show_next_preview(self) -> None:
        total = len(self.preview_items)
        if total <= 0:
            return
        self.preview_index = (self.preview_index + 1) % total
        self._update_preview_navigation()
        self.preview_index_changed.emit(self.preview_index)

    def set_stats_rows(self, rows: List[dict]) -> None:
        while self.stats_cards_layout.count():
            item = self.stats_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not rows:
            lower_rank_percent = int(self.highlight_rules["lower_rank_percent"])
            upper_rank_percent = int(self.highlight_rules["upper_rank_percent"])
            self.stats_cards_layout.addWidget(
                self._build_stats_card(
                    "전체 요약",
                    [
                        "도서 수, 페이지 수, 하이라이트 기준 요약",
                        f"분포 기준: 하위 {lower_rank_percent}% / 상위 {upper_rank_percent}%",
                    ],
                )
            )
            for header in RESULT_HEADERS[1:]:
                if header == "띄어쓰기":
                    lines = [
                        "분포 차트, 평균, 중앙값, 범위",
                        f"기준값: {self.highlight_rules['space_min']:.2f} ~ {self.highlight_rules['space_max']:.2f}",
                    ]
                elif header in _ZERO_THRESHOLD_HEADERS:
                    threshold = self.highlight_rules[_ZERO_THRESHOLD_RULE_KEYS[header]]
                    lines = [
                        "기준값 초과 건수와 비율",
                        f"기본 기준: {format_metric_value(header, threshold)}",
                    ]
                else:
                    lines = [
                        "분포 차트, 평균, 중앙값, 범위",
                        f"경계값: 하위 {lower_rank_percent}% / 상위 {upper_rank_percent}%",
                    ]
                self.stats_cards_layout.addWidget(self._build_stats_card(header, lines))
            self.stats_cards_layout.addStretch(1)
            return

        total_books = len(rows)
        total_pages = sum(int(row.get("pages", 0) or 0) for row in rows)
        lower_rank_percent = int(self.highlight_rules["lower_rank_percent"])
        upper_rank_percent = int(self.highlight_rules["upper_rank_percent"])
        self.stats_cards_layout.addWidget(
            self._build_stats_card(
                "전체 요약",
                [
                    f"도서 수: {total_books}권",
                    f"페이지 수: {total_pages}페이지",
                    f"하이라이팅 기준: 고정 기준이 없는 항목은 하위 {lower_rank_percent}% / 상위 {upper_rank_percent}% 기준으로 확인",
                ],
            )
        )

        for header in RESULT_HEADERS[1:]:
            values = [book_metric_numeric_value(header, row) for row in rows]
            if not values:
                continue
            book_labels = [str(row.get("book_name", "") or "") for row in rows]

            average = statistics.mean(values)
            median = statistics.median(values)
            minimum = min(values)
            maximum = max(values)
            lines = [
                f"분포: 평균 {format_metric_value(header, average)} | 중앙값 {format_metric_value(header, median)}",
                f"범위: 최소 {format_metric_value(header, minimum)} | 최대 {format_metric_value(header, maximum)}",
            ]

            if header == "띄어쓰기":
                space_min = self.highlight_rules["space_min"]
                space_max = self.highlight_rules["space_max"]
                outlier_count = sum(1 for value in values if not (space_min <= value <= space_max))
                lines.append(f"기준값: {space_min:.2f} ~ {space_max:.2f}")
                lines.append(f"이상치: 기준 밖 {outlier_count}권 ({outlier_count / total_books * 100:.1f}%)")
                threshold_lines = [space_min, space_max]
            elif header in _ZERO_THRESHOLD_HEADERS:
                threshold = self.highlight_rules[_ZERO_THRESHOLD_RULE_KEYS[header]]
                flagged_count = sum(1 for value in values if value > threshold)
                lines.append(f"기준값: {format_metric_value(header, threshold)}")
                lines.append(f"이상치: 기준 초과 {flagged_count}권 ({flagged_count / total_books * 100:.1f}%)")
                threshold_lines = [threshold]
            else:
                low_boundary, high_boundary = _rank_boundaries(
                    values,
                    lower_rank_percent=self.highlight_rules["lower_rank_percent"],
                    upper_rank_percent=self.highlight_rules["upper_rank_percent"],
                )
                lines.append("기준값: 고정 기준 없음")
                lines.append(
                    "분포 기준: "
                    f"하위 10% 경계 {format_metric_value(header, low_boundary)} | "
                    f"상위 10% 경계 {format_metric_value(header, high_boundary)}"
                )
                lines[-1] = (
                    lines[-1]
                    .replace("하위 10%", f"하위 {lower_rank_percent}%")
                    .replace("상위 10%", f"상위 {upper_rank_percent}%")
                    .replace("10%", f"{upper_rank_percent}%")
                )
                threshold_lines = []

            self.stats_cards_layout.addWidget(
                self._build_stats_card(
                    header,
                    lines,
                    values=values,
                    value_labels=book_labels,
                    threshold_lines=threshold_lines,
                )
            )

        self.stats_cards_layout.addStretch(1)

    def _build_stats_card(
        self,
        title: str,
        lines: List[str],
        *,
        values: Optional[Sequence[float]] = None,
        value_labels: Optional[Sequence[str]] = None,
        threshold_lines: Optional[Sequence[float]] = None,
    ) -> QWidget:
        card = QFrame()
        card.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 700; color: #111827; border: none; background: transparent;")
        layout.addWidget(title_label)

        if values:
            layout.addWidget(DistributionMiniChart(values, labels=value_labels, threshold_lines=threshold_lines))

        for line in lines:
            label = QLabel(line)
            label.setWordWrap(True)
            label.setStyleSheet("color: #475569; font-size: 11px; border: none; background: transparent;")
            layout.addWidget(label)

        return card
