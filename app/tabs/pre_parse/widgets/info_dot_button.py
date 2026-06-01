from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QToolButton

from .custom_tooltip import hide_tooltip, show_tooltip


class InfoDotButton(QToolButton):
    """
    OCR/BBOX 공용 i 아이콘 버튼.
    setToolTip() + enterEvent/leaveEvent에서 커스텀 툴팁 사용.
    텍스트 길이에 맞는 크기, 줄바꿈, 최대 너비 제한이 적용된다.
    """

    def enterEvent(self, event) -> None:  # type: ignore[override]
        if self.toolTip():
            show_tooltip(self, self.toolTip())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        hide_tooltip()
        super().leaveEvent(event)

    def event(self, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.ToolTip:
            return True
        return super().event(event)
