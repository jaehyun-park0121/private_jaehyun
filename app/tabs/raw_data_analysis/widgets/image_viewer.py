from typing import List

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QLabel, QSizePolicy


class ImageViewerWidget(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pixmap = QPixmap()
        self._bboxes: List[dict] = []
        self._selected_index = -1
        self._empty_message = "미리보기 이미지 없음"
        self.scale_factor = 1.0
        self._min_scale_factor = 1.0
        self._max_scale_factor = 8.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_start_offset = QPointF(0.0, 0.0)
        self.setMouseTracking(True)

    def set_empty_message(self, text: str) -> None:
        self._empty_message = str(text or "").strip() or "미리보기 이미지 없음"
        self.update()

    def set_image(self, image_path: str) -> None:
        if image_path:
            self._pixmap = QPixmap(image_path)
        else:
            self._pixmap = QPixmap()
        self.scale_factor = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._dragging = False
        self.update()

    def set_bboxes(self, bboxes: List[dict], selected_index: int = -1) -> None:
        self._bboxes = bboxes
        self._selected_index = selected_index
        self.update()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if self._pixmap.isNull():
            event.ignore()
            return

        angle_delta = event.angleDelta().y()
        if angle_delta == 0:
            event.ignore()
            return

        step = 1.15 if angle_delta > 0 else (1.0 / 1.15)
        old_scale = float(self.scale_factor)
        new_scale = max(self._min_scale_factor, min(self._max_scale_factor, old_scale * step))
        if abs(new_scale - old_scale) < 1e-9:
            event.accept()
            return

        before_rect = self._image_draw_rect()
        cursor_pos = QPointF(event.pos())
        image_anchor = self._widget_to_image_point(cursor_pos, before_rect)

        self.scale_factor = new_scale
        after_rect = self._image_draw_rect(raw=True)
        new_left = cursor_pos.x() - image_anchor.x() * after_rect.width()
        new_top = cursor_pos.y() - image_anchor.y() * after_rect.height()
        centered_left = (self.width() - after_rect.width()) / 2.0
        centered_top = (self.height() - after_rect.height()) / 2.0
        self._pan_offset = QPointF(new_left - centered_left, new_top - centered_top)
        self._clamp_pan_offset(after_rect)
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and not self._pixmap.isNull():
            self._dragging = True
            self._drag_start_pos = event.pos()
            self._drag_start_offset = QPointF(self._pan_offset)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging and not self._pixmap.isNull():
            delta = event.pos() - self._drag_start_pos
            raw_rect = self._image_draw_rect(raw=True)
            self._pan_offset = QPointF(
                self._drag_start_offset.x() + delta.x(),
                self._drag_start_offset.y() + delta.y(),
            )
            self._clamp_pan_offset(raw_rect)
            self.update()
            event.accept()
            return

        if not self._pixmap.isNull():
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            if self._pixmap.isNull():
                self.unsetCursor()
            else:
                self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        if not self._dragging:
            self.unsetCursor()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._pixmap.isNull():
            return
        self._clamp_pan_offset(self._image_draw_rect(raw=True))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._pixmap.isNull():
            self.setText(self._empty_message)
            return

        self.setText("")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        target = self._image_draw_rect()
        if target.width() <= 0 or target.height() <= 0:
            return

        scaled = self._pixmap.scaled(
            max(1, int(round(target.width()))),
            max(1, int(round(target.height()))),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        draw_x = int(round(target.x()))
        draw_y = int(round(target.y()))
        painter.drawPixmap(draw_x, draw_y, scaled)

        sx = scaled.width() / self._pixmap.width()
        sy = scaled.height() / self._pixmap.height()

        for idx, bbox_info in enumerate(self._bboxes):
            bbox = bbox_info.get("bbox", [0, 0, 0, 0])
            severity = str(bbox_info.get("severity", "ERROR")).upper()
            color_value = str(bbox_info.get("color", "")).strip()
            if color_value.startswith("#"):
                color = QColor(color_value)
            else:
                color = QColor(255, 0, 0) if severity == "ERROR" else QColor(255, 140, 0)

            tone_down = bool(bbox_info.get("tone_down", False))
            if tone_down and idx != self._selected_index:
                color.setAlpha(90)
                pen_width = 1
            else:
                color.setAlpha(220)
                pen_width = 2
            if idx == self._selected_index:
                color.setAlpha(255)
                pen_width = 3

            painter.setPen(QPen(color, pen_width))
            rect = QRect(
                int(draw_x + bbox[0] * sx),
                int(draw_y + bbox[1] * sy),
                int((bbox[2] - bbox[0]) * sx),
                int((bbox[3] - bbox[1]) * sy),
            )
            painter.drawRect(rect)

    def _image_draw_rect(self, *, raw: bool = False) -> QRectF:
        if self._pixmap.isNull():
            return QRectF()

        viewport = QRectF(self.rect())
        if viewport.width() <= 0 or viewport.height() <= 0:
            return QRectF()

        pixmap_width = float(self._pixmap.width())
        pixmap_height = float(self._pixmap.height())
        if pixmap_width <= 0 or pixmap_height <= 0:
            return QRectF()

        fit_scale = min(viewport.width() / pixmap_width, viewport.height() / pixmap_height)
        fit_scale = max(fit_scale, 0.0001)
        draw_width = pixmap_width * fit_scale * float(self.scale_factor)
        draw_height = pixmap_height * fit_scale * float(self.scale_factor)
        left = (viewport.width() - draw_width) / 2.0 + self._pan_offset.x()
        top = (viewport.height() - draw_height) / 2.0 + self._pan_offset.y()
        rect = QRectF(left, top, draw_width, draw_height)
        if raw:
            return rect
        self._clamp_pan_offset(rect)
        left = (viewport.width() - draw_width) / 2.0 + self._pan_offset.x()
        top = (viewport.height() - draw_height) / 2.0 + self._pan_offset.y()
        return QRectF(left, top, draw_width, draw_height)

    def _clamp_pan_offset(self, rect: QRectF) -> None:
        viewport = QRectF(self.rect())
        if viewport.width() <= 0 or viewport.height() <= 0:
            self._pan_offset = QPointF(0.0, 0.0)
            return

        centered_left = (viewport.width() - rect.width()) / 2.0
        centered_top = (viewport.height() - rect.height()) / 2.0

        if rect.width() <= viewport.width():
            clamped_x = 0.0
        else:
            min_x = viewport.width() - rect.width() - centered_left
            max_x = -centered_left
            clamped_x = min(max(self._pan_offset.x(), min_x), max_x)

        if rect.height() <= viewport.height():
            clamped_y = 0.0
        else:
            min_y = viewport.height() - rect.height() - centered_top
            max_y = -centered_top
            clamped_y = min(max(self._pan_offset.y(), min_y), max_y)

        self._pan_offset = QPointF(clamped_x, clamped_y)

    def _widget_to_image_point(self, pos: QPointF, rect: QRectF) -> QPointF:
        if rect.width() <= 0 or rect.height() <= 0:
            return QPointF(0.5, 0.5)
        x = (pos.x() - rect.left()) / rect.width()
        y = (pos.y() - rect.top()) / rect.height()
        return QPointF(min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0))
