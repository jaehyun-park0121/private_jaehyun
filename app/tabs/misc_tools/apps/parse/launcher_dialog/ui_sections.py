from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.tabs.pre_parse.widgets.info_dot_button import InfoDotButton


def build_info_button(tooltip: str) -> QToolButton:
    info_btn = InfoDotButton()
    info_btn.setText("i")
    info_btn.setToolTip(str(tooltip))
    info_btn.setCursor(Qt.PointingHandCursor)
    info_btn.setFixedSize(16, 16)
    info_btn.setStyleSheet(
        """
        QToolButton {
            color: #64748b;
            background: #e5e7eb;
            border: 1px solid #d8dee8;
            border-radius: 8px;
            font-size: 10px;
            font-weight: 700;
            padding: 0;
        }
        QToolButton:hover {
            background: #dce3ea;
        }
        """
    )
    return info_btn


def section_header(title: str, tooltip: str) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    title_label = QLabel(title)
    title_label.setStyleSheet("color: #0f172a; font-size: 13px; font-weight: 700;")
    row.addWidget(title_label)
    row.addWidget(build_info_button(tooltip))
    row.addStretch(1)
    return holder


def build_toggle_card(
    checkbox: QCheckBox, description: str, extra: Optional[QWidget] = None
) -> QFrame:
    card = QFrame()
    card.setObjectName("parseOptionCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(6)
    layout.addWidget(checkbox)
    desc = QLabel(description)
    desc.setWordWrap(True)
    desc.setStyleSheet("color: #64748b; font-size: 11px;")
    layout.addWidget(desc)
    if extra is not None:
        layout.addWidget(extra)
    layout.addStretch(1)
    set_toggle_card_checked(card, checkbox.isChecked())
    checkbox.toggled.connect(
        lambda checked, target=card: set_toggle_card_checked(target, checked)
    )
    return card


def set_toggle_card_checked(card: QFrame, checked: bool) -> None:
    card.setProperty("checked", "true" if checked else "false")
    card.style().unpolish(card)
    card.style().polish(card)
    card.update()


def line_with_button(line_edit: QLineEdit, button_text: str, on_click) -> QWidget:
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    button = QPushButton(button_text)
    button.setMaximumWidth(72)
    button.clicked.connect(on_click)
    row.addWidget(line_edit, 1)
    row.addWidget(button)
    return wrapper


def clear_grid_layout(layout: QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
