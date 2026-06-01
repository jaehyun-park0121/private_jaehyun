from __future__ import annotations

from typing import Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QPushButton, QWidget


class MultiSelectButtonGroup(QWidget):
    def __init__(
        self,
        choices: List[str],
        default_values: Optional[List[str]] = None,
        columns: int = 3,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._buttons: Dict[str, QPushButton] = {}
        column_count = max(1, int(columns))
        selected = set(default_values or [])

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)

        for i, choice in enumerate(choices):
            value = str(choice).strip()
            if not value:
                continue
            button = QPushButton(value)
            button.setCheckable(True)
            button.setChecked(value in selected)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(30)
            button.setStyleSheet(
                """
                QPushButton {
                    background: #f3f4f6;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 3px 8px;
                    color: #334155;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #e2e8f0;
                }
                QPushButton:checked {
                    background: #dbeafe;
                    border: 1px solid #60a5fa;
                    color: #1d4ed8;
                    font-weight: 600;
                }
                """
            )
            row = i // column_count
            col = i % column_count
            layout.addWidget(button, row, col)
            self._buttons[value] = button

    def selected_values(self) -> List[str]:
        return [value for value, button in self._buttons.items() if button.isChecked()]
