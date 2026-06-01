"""이미지 + BBOX 오버레이 뷰어 (줌/패닝 지원)."""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..constants import (
    COLOR_BG,
    COLOR_PRIMARY,
    COLOR_SELECT,
    LABEL_BORDERS,
    LABEL_COLORS,
)


class BBoxItem(QGraphicsRectItem):
    def __init__(self, rect, label, shape_index, on_click):
        super().__init__(rect)
        self.label = label
        self.shape_index = shape_index
        self._on_click = on_click
        self._selected = False
        self._update_style()
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _update_style(self):
        fill = LABEL_COLORS.get(self.label, QColor(150, 150, 150, 60))
        border = LABEL_BORDERS.get(self.label, QColor(180, 180, 180))
        if self._selected:
            pen = QPen(QColor(COLOR_SELECT), 4)
        else:
            pen = QPen(border, 2)
        self.setPen(pen)
        self.setBrush(QBrush(fill))

    def set_selected(self, sel):
        self._selected = sel
        self._update_style()

    def hoverEnterEvent(self, event):
        if not self._selected:
            self.setPen(QPen(QColor(COLOR_PRIMARY), 3))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._update_style()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.shape_index)
        super().mousePressEvent(event)


class ImageView(QGraphicsView):
    """이미지 + BBOX를 표시하는 뷰. 외부에서는 add_bbox/select_bbox로 제어."""

    bbox_clicked = pyqtSignal(int)  # shape_index

    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(COLOR_BG)))
        self._zoom = 1.0
        self.pixmap_item = None
        self._original_pixmap = QPixmap()
        self._rotation_degrees = 0
        self._bbox_items: dict[int, BBoxItem] = {}
        self._selected_index: int = -1

    # --- 이미지 ---
    def set_image(self, pixmap):
        self._original_pixmap = QPixmap(pixmap)
        self._rotation_degrees = 0
        self._selected_index = -1
        self._set_scene_pixmap()

    def rotate_left(self):
        self._rotate(-90)

    def rotate_right(self):
        self._rotate(90)

    def rotation_degrees(self) -> int:
        return self._rotation_degrees

    def _rotate(self, degrees: int):
        if self._original_pixmap.isNull():
            return
        self._rotation_degrees = (self._rotation_degrees + degrees) % 360
        self._set_scene_pixmap()

    def _set_scene_pixmap(self):
        self._scene.clear()
        self._bbox_items = {}
        if self._original_pixmap.isNull():
            self.pixmap_item = None
            self._scene.setSceneRect(QRectF())
            self.reset_zoom()
            return

        pixmap = self._rotated_pixmap()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self.pixmap_item)
        self._scene.setSceneRect(QRectF(pixmap.rect().toRectF()))
        self.reset_zoom()

    def has_image(self) -> bool:
        return self.pixmap_item is not None

    # --- BBOX ---
    def clear_bboxes(self):
        if self.pixmap_item is None:
            return
        for item in list(self._bbox_items.values()):
            self._scene.removeItem(item)
        self._bbox_items = {}

    def add_bbox(self, rect: QRectF, label: str, shape_index: int):
        item = BBoxItem(self._map_bbox_rect(rect), label, shape_index, self.bbox_clicked.emit)
        self._scene.addItem(item)
        self._bbox_items[shape_index] = item
        if shape_index == self._selected_index:
            item.set_selected(True)
        return item

    def select_bbox(self, shape_index: int):
        prev = self._bbox_items.get(self._selected_index)
        if prev is not None:
            prev.set_selected(False)
        self._selected_index = shape_index
        cur = self._bbox_items.get(shape_index)
        if cur is not None:
            cur.set_selected(True)

    def center_on_bbox(self, shape_index: int):
        item = self._bbox_items.get(shape_index)
        if item is not None:
            self.centerOn(item)

    # --- 줌 ---
    def reset_zoom(self):
        self.resetTransform()
        self._zoom = 1.0
        if self.pixmap_item is not None:
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self._zoom *= factor
        self.scale(factor, factor)

    def _rotated_pixmap(self) -> QPixmap:
        if self._rotation_degrees == 0:
            return QPixmap(self._original_pixmap)
        transform = QTransform().rotate(self._rotation_degrees)
        return self._original_pixmap.transformed(
            transform,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _map_bbox_rect(self, rect: QRectF) -> QRectF:
        if self._rotation_degrees == 0 or self._original_pixmap.isNull():
            return rect
        raw_transform = QTransform().rotate(self._rotation_degrees)
        true_transform = QPixmap.trueMatrix(
            raw_transform,
            self._original_pixmap.width(),
            self._original_pixmap.height(),
        )
        return true_transform.mapRect(rect).normalized()
