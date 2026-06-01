"""
텍스트 길이에 맞게 크기가 자동 계산되는 커스텀 툴팁.
- 최대 너비 제한 내 자동 줄바꿈
- 짧은 텍스트는 최소 크기로 표시
- padding 포함 정확한 크기 계산
"""
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


_MAX_WIDTH = 280
_LABEL_MAX_WIDTH = _MAX_WIDTH - 14  # padding 6*2 + border 2
_STYLE = """
    QFrame {
        background-color: #ffffff;
        color: #94a3b8;
        border: 1px solid #cbd5e1;
        border-radius: 4px;
        padding: 6px 8px;
    }
"""


class CustomTooltip(QFrame):
    """텍스트 내용에 맞게 크기가 자동 계산되는 툴팁 위젯."""

    _instance: Optional["CustomTooltip"] = None

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(_STYLE)

        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(_LABEL_MAX_WIDTH)
        self._label.setStyleSheet(
            "QLabel { color: #94a3b8; font-size: 11px; background: transparent; border: none; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    @classmethod
    def instance(cls) -> "CustomTooltip":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def show_at(self, global_pos: tuple, text: str) -> None:
        if not text.strip():
            return
        self._label.setText(text)
        self._label.adjustSize()
        self.adjustSize()
        self.move(global_pos[0], global_pos[1])
        self.raise_()
        self.show()

    def hide_tooltip(self) -> None:
        self.hide()


def show_tooltip(widget: QWidget, text: str) -> None:
    """위젯 하단에 툴팁 표시."""
    if not text.strip():
        return
    tip = CustomTooltip.instance()
    pos = widget.mapToGlobal(widget.rect().bottomLeft())
    tip.show_at((pos.x(), pos.y()), text)


def hide_tooltip() -> None:
    """툴팁 숨김."""
    CustomTooltip.instance().hide_tooltip()
