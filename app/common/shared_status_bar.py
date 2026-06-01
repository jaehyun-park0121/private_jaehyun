from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def format_progress_status(desc: str, current: int, total: int, bar_width: int = 20) -> str:
    if total <= 0:
        return f"{desc}: 0/0"
    pct = int((current / total) * 100)
    filled = int((current / total) * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    return f"{desc}: {pct}%|{bar}| {current}/{total}"


class SharedStatusBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.container = QFrame()
        self.container.setObjectName("bottomLogBar")

        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        self.message_label = QLabel(f"최근 작업 로그: {format_progress_status('대기 중', 0, 1)}")
        self.message_label.setObjectName("recentLogLabel")
        self.message_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addStretch(1)
        layout.addWidget(self.message_label, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.container)

    def set_message(self, text: str) -> None:
        message = str(text or "").strip()
        if not message:
            message = f"최근 작업 로그: {format_progress_status('대기 중', 0, 1)}"
        elif not message.startswith("최근 작업 로그:"):
            message = f"최근 작업 로그: {message}"
        self.message_label.setText(message)

    def set_progress(self, desc: str, current: int, total: int) -> None:
        self.set_message(format_progress_status(desc, current, total))
