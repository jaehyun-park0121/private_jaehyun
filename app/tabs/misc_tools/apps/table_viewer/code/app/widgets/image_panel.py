"""가운데 이미지 패널 — ImageView + 줌/필터 툴바."""

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..constants import COLOR_BODY_TEXT, LABELS
from .image_view import ImageView


class ImagePanel(QFrame):
    """이미지 + BBOX 뷰어를 감싸는 패널. 라벨 필터 토글을 자체 처리."""

    bbox_clicked = pyqtSignal(int)  # shape_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._shapes: list[dict] = []
        self._build_ui()
        self.image_view.bbox_clicked.connect(self.bbox_clicked.emit)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("이미지 / BBOX")
        title.setObjectName("title")
        layout.addWidget(title)

        control_group = QGroupBox("보기")
        control_layout = QHBoxLayout(control_group)
        control_layout.setContentsMargins(8, 8, 8, 8)
        control_layout.setSpacing(8)
        toolbar = QHBoxLayout()
        btn_zoom_reset = QPushButton("화면 맞춤")
        btn_zoom_reset.clicked.connect(lambda: self.image_view.reset_zoom())
        toolbar.addWidget(btn_zoom_reset)

        btn_rotate_left = QPushButton()
        btn_rotate_left.setIcon(_build_rotate_icon(clockwise=False))
        btn_rotate_left.setIconSize(QSize(20, 20))
        btn_rotate_left.setFixedWidth(36)
        btn_rotate_left.setToolTip("왼쪽으로 90도 회전")
        btn_rotate_left.clicked.connect(self.rotate_left)
        toolbar.addWidget(btn_rotate_left)

        btn_rotate_right = QPushButton()
        btn_rotate_right.setIcon(_build_rotate_icon(clockwise=True))
        btn_rotate_right.setIconSize(QSize(20, 20))
        btn_rotate_right.setFixedWidth(36)
        btn_rotate_right.setToolTip("오른쪽으로 90도 회전")
        btn_rotate_right.clicked.connect(self.rotate_right)
        toolbar.addWidget(btn_rotate_right)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("필터:"))
        self.filters: dict[str, QCheckBox] = {}
        for label in LABELS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.stateChanged.connect(self._refresh_bboxes)
            toolbar.addWidget(cb)
            self.filters[label] = cb
        control_layout.addLayout(toolbar)
        layout.addWidget(control_group, 0)

        self.image_view = ImageView()
        layout.addWidget(self.image_view, 1)

    # --- 외부 API ---
    def set_image(self, pixmap):
        self.image_view.set_image(pixmap)

    def set_shapes(self, shapes: list[dict]):
        self._shapes = shapes
        self._refresh_bboxes()

    def select_shape(self, idx: int):
        self.image_view.select_bbox(idx)

    def center_on(self, idx: int):
        self.image_view.center_on_bbox(idx)

    def reset_zoom(self):
        self.image_view.reset_zoom()

    def label_filter_states(self) -> dict[str, bool]:
        return {label: cb.isChecked() for label, cb in self.filters.items()}

    def set_label_filter_states(self, states: dict[str, bool]):
        for label, cb in self.filters.items():
            cb.blockSignals(True)
            cb.setChecked(bool(states.get(label, True)))
            cb.blockSignals(False)
        self._refresh_bboxes()

    def set_table_only_filter(self):
        for label, cb in self.filters.items():
            cb.blockSignals(True)
            cb.setChecked(label == "TABLE")
            cb.blockSignals(False)
        self._refresh_bboxes()

    def rotate_left(self):
        self.image_view.rotate_left()
        self._refresh_bboxes()

    def rotate_right(self):
        self.image_view.rotate_right()
        self._refresh_bboxes()

    # --- 내부 ---
    def _refresh_bboxes(self):
        if not self.image_view.has_image():
            return
        self.image_view.clear_bboxes()
        for idx, shape in enumerate(self._shapes):
            label = shape.get("label", "")
            if label in self.filters and not self.filters[label].isChecked():
                continue
            pts = shape.get("points", [])
            if len(pts) < 2:
                continue
            (x1, y1), (x2, y2) = pts[0], pts[1]
            rect = QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized()
            self.image_view.add_bbox(rect, label, idx)


def _build_rotate_icon(*, clockwise: bool) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(COLOR_BODY_TEXT), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    if clockwise:
        points = [
            QPointF(7, 5),
            QPointF(16, 5),
            QPointF(16, 14),
            QPointF(20, 10),
            QPointF(16, 14),
            QPointF(12, 10),
        ]
    else:
        points = [
            QPointF(17, 5),
            QPointF(8, 5),
            QPointF(8, 14),
            QPointF(4, 10),
            QPointF(8, 14),
            QPointF(12, 10),
        ]

    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)
    painter.end()
    return QIcon(pixmap)
