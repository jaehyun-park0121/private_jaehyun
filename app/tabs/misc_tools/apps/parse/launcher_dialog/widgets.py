from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class FocusWheelSpinBox(QSpinBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._wheel_armed = False
        self.setFocusPolicy(Qt.ClickFocus)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._wheel_armed = True
        super().mousePressEvent(event)

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        self._wheel_armed = False
        super().focusOutEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._wheel_armed = False
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if self._wheel_armed and self.hasFocus():
            super().wheelEvent(event)
            return
        event.ignore()


class ChoiceButtonRow(QWidget):
    changed = pyqtSignal(str)

    def __init__(
        self, choices: list[str], parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("labelChoiceRow")
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._row_height = 30
        self._row_padding_v = 2

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)
        self._layout = layout
        self.setFixedHeight(self._row_height + self._row_padding_v)

        for choice in choices:
            self._add_choice(choice)

        if choices:
            self.set_value(choices[0], choices[0])

    def _add_choice(self, value: str) -> None:
        normalized = str(value or "").strip()
        if not normalized or normalized in self._buttons:
            return
        button = QPushButton(normalized)
        button.setObjectName("labelChoiceButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setFixedHeight(self._row_height)
        button.clicked.connect(
            lambda checked, option=normalized: self._on_button_clicked(
                checked, option
            )
        )
        self._buttons[normalized] = button
        self._group.addButton(button)
        self._layout.addWidget(button)

    def _on_button_clicked(self, checked: bool, option: str) -> None:
        if checked:
            self.changed.emit(option)

    def value(self) -> str:
        for value, button in self._buttons.items():
            if button.isChecked():
                return value
        return ""

    def set_value(self, value: str, default: str) -> None:
        normalized = str(value or "").strip()
        if not normalized:
            normalized = str(default or "").strip()
        if not normalized:
            return
        if normalized not in self._buttons:
            self._add_choice(normalized)

        old_block = self.blockSignals(True)
        for option, button in self._buttons.items():
            button.setChecked(option == normalized)
        self.blockSignals(old_block)

    def buttons(self) -> list[QPushButton]:
        return list(self._buttons.values())

    def set_row_height(self, height: int) -> None:
        self._row_height = max(24, int(height))
        self.setFixedHeight(self._row_height + self._row_padding_v)
        for button in self._buttons.values():
            button.setFixedHeight(self._row_height)


class LabelRuleCard(QFrame):
    remove_requested = pyqtSignal(object)
    changed = pyqtSignal()
    activated = pyqtSignal(object)

    CARD_HEIGHT = 252
    CARD_MIN_WIDTH = 320
    FIELD_HEIGHT = 30

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("labelRuleCard")
        self.setProperty("invalid", "false")
        self.setProperty("active", "false")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(self.CARD_MIN_WIDTH)
        self.setFixedHeight(self.CARD_HEIGHT)
        self._active = False

        self.label_key_edit = QLineEdit()
        self.label_key_edit.setPlaceholderText("LABEL (예: IMAGE)")
        self.label_key_edit.setFixedHeight(self.FIELD_HEIGHT)

        self.type_edit = QLineEdit()
        self.type_edit.setPlaceholderText("type")
        self.type_edit.setFixedHeight(self.FIELD_HEIGHT)

        self.use_in_contents_choice = ChoiceButtonRow(["text", "tag"])
        self.use_in_contents_choice.set_row_height(self.FIELD_HEIGHT)

        self.marker_edit = QLineEdit()
        self.marker_edit.setPlaceholderText("")
        self.marker_edit.setFixedHeight(self.FIELD_HEIGHT)

        self.description_mode_choice = ChoiceButtonRow(
            ["none", "flags_text", "children_rendered"]
        )
        self.description_mode_choice.set_row_height(self.FIELD_HEIGHT)

        self.crop_check = QCheckBox("crop")
        self.chapter_source_check = QCheckBox("chapter_source")

        self.remove_btn = QPushButton("x")
        self.remove_btn.setObjectName("labelCardDeleteButton")
        self.remove_btn.setFixedSize(24, 24)
        self.remove_btn.setCursor(Qt.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header_title = QLabel("라벨")
        header_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #0f172a;")
        header.addWidget(header_title)
        header.addWidget(self.label_key_edit, 1)
        header.addWidget(self.remove_btn)
        root.addLayout(header)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(12)
        form.addRow(self._form_label("type"), self.type_edit)
        form.addRow(
            self._form_label("use_in_contents"), self.use_in_contents_choice
        )
        form.addRow(self._form_label("marker"), self.marker_edit)
        form.addRow(
            self._form_label("description_mode"), self.description_mode_choice
        )
        root.addLayout(form)

        options_row = QHBoxLayout()
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.setSpacing(12)
        options_row.addWidget(self.crop_check)
        options_row.addWidget(self.chapter_source_check)
        options_row.addStretch(1)
        root.addLayout(options_row)

        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        self.remove_btn.clicked.connect(lambda: self.activated.emit(self))
        self.label_key_edit.editingFinished.connect(self._normalize_label_key)
        self.label_key_edit.textChanged.connect(lambda _text: self.changed.emit())
        self.type_edit.textChanged.connect(lambda _text: self.changed.emit())
        self.use_in_contents_choice.changed.connect(self._on_use_in_contents_changed)
        self.use_in_contents_choice.changed.connect(lambda _text: self.changed.emit())
        self.marker_edit.textChanged.connect(lambda _text: self.changed.emit())
        self.description_mode_choice.changed.connect(lambda _text: self.changed.emit())
        self.crop_check.toggled.connect(lambda _checked: self.changed.emit())
        self.chapter_source_check.toggled.connect(lambda _checked: self.changed.emit())
        self._on_use_in_contents_changed(self.use_in_contents_choice.value())

        self._interactive_widgets = [
            self,
            self.label_key_edit,
            self.type_edit,
            self.marker_edit,
            self.crop_check,
            self.chapter_source_check,
            self.remove_btn,
            *self.use_in_contents_choice.buttons(),
            *self.description_mode_choice.buttons(),
        ]
        for widget in self._interactive_widgets:
            widget.installEventFilter(self)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.activated.emit(self)
        super().mousePressEvent(event)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        event_type = event.type()
        if event_type in (QEvent.FocusIn, QEvent.MouseButtonPress):
            self.activated.emit(self)
        if event_type == QEvent.Wheel and not self._active:
            event.ignore()
            return False
        return super().eventFilter(watched, event)

    def _normalize_label_key(self) -> None:
        text = self.label_key_edit.text().strip().upper()
        if text != self.label_key_edit.text():
            self.label_key_edit.setText(text)

    def _form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedHeight(self.FIELD_HEIGHT)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return label

    def _on_use_in_contents_changed(self, value: str) -> None:
        use_tag = str(value or "").strip() == "tag"
        self.marker_edit.setEnabled(use_tag)

    def set_rule(self, label_key: str, rule: dict[str, object]) -> None:
        normalized_key = str(label_key or "").strip().upper()
        self.label_key_edit.setText(normalized_key)
        self.type_edit.setText(str(rule.get("type", "") or ""))
        self.use_in_contents_choice.set_value(
            str(rule.get("use_in_contents", "") or ""),
            default="text",
        )
        self.marker_edit.setText(str(rule.get("marker", "") or ""))
        self.description_mode_choice.set_value(
            str(rule.get("description_mode", "") or ""),
            default="none",
        )
        self.crop_check.setChecked(bool(rule.get("crop", False)))
        self.chapter_source_check.setChecked(bool(rule.get("chapter_source", False)))
        self._attach_choice_button_filters()
        self._on_use_in_contents_changed(self.use_in_contents_choice.value())
        self.set_invalid(False, "")

    def to_rule(self) -> tuple[str, dict[str, object]]:
        label_key = self.label_key_edit.text().strip().upper()
        use_in_contents = str(self.use_in_contents_choice.value() or "text").strip() or "text"
        marker = self.marker_edit.text().strip() if use_in_contents == "tag" else ""
        rule = {
            "type": self.type_edit.text().strip() or label_key.lower(),
            "use_in_contents": use_in_contents,
            "marker": marker,
            "crop": self.crop_check.isChecked(),
            "description_mode": (
                str(self.description_mode_choice.value() or "none").strip() or "none"
            ),
            "chapter_source": self.chapter_source_check.isChecked(),
        }
        return label_key, rule

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setProperty("active", "true" if self._active else "false")
        self._refresh_style()

    def set_invalid(self, invalid: bool, reason: str = "") -> None:
        self.setProperty("invalid", "true" if invalid else "false")
        self._refresh_style()
        self.setToolTip(reason if invalid else "")

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _attach_choice_button_filters(self) -> None:
        for button in (
            self.use_in_contents_choice.buttons()
            + self.description_mode_choice.buttons()
        ):
            if button in self._interactive_widgets:
                continue
            self._interactive_widgets.append(button)
            button.installEventFilter(self)
