"""우측 검수 패널 — TABLE 목록 + TableEditor + 검수 메모."""

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ..editor.table_editor import TableEditor
from ..editor.table_formats import (
    TABLE_FORMAT_HTML,
    TABLE_FORMAT_LABELS,
    TABLE_FORMAT_MARKDOWN,
    TABLE_SPANS_ATTR,
    TableFormatError,
    render_source_to_html,
)


_PROBLEM_TO_INDEX = {None: 0, False: 1, True: 2}
_INDEX_TO_PROBLEM = {0: None, 1: False, 2: True}
_HTML_TABLE_RE = re.compile(r"<\s*(table|thead|tbody|tfoot|tr|td|th)\b", re.IGNORECASE)


class ReviewPanel(QFrame):
    """검수 패널.

    외부에서 set_shapes(shapes)로 데이터를 주입하고,
    select_shape(idx)로 표시할 shape를 지정한다.
    사용자가 목록에서 클릭하면 shape_selected를 emit한다.
    """

    shape_selected = pyqtSignal(int)  # 사용자가 목록에서 선택
    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(430)
        self._shapes: list[dict] = []
        self._current_index: int = -1
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("TABLE 검수")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(QLabel("표 포맷"))
        self.table_format_combo = QComboBox()
        self.table_format_combo.addItem(TABLE_FORMAT_LABELS[TABLE_FORMAT_HTML], TABLE_FORMAT_HTML)
        self.table_format_combo.addItem(
            TABLE_FORMAT_LABELS[TABLE_FORMAT_MARKDOWN],
            TABLE_FORMAT_MARKDOWN,
        )
        title_row.addWidget(self.table_format_combo)
        layout.addLayout(title_row)

        self.table_list = QListWidget()
        self.table_list.itemClicked.connect(self._on_list_clicked)
        self.table_list.setMaximumHeight(150)
        layout.addWidget(self.table_list)

        # 표 편집기
        self.editor = TableEditor()
        self.editor.table_text_changed.connect(self._on_editor_text_changed)
        self.editor.table_spans_changed.connect(self._on_editor_spans_changed)
        self.editor.status_message.connect(self.status_message.emit)
        layout.addWidget(self.editor, 1)
        self.table_format_combo.currentIndexChanged.connect(self._on_format_changed)

        # 검수 메모
        self.meta_box = self._build_meta_box()
        layout.addWidget(self.meta_box)

    def _build_meta_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("sectionBox")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        title = QLabel("검수 메모")
        title.setObjectName("title")
        v.addWidget(title)

        prob_row = QHBoxLayout()
        prob_row.addWidget(QLabel("검수 상태"))
        self.problem_combo = QComboBox()
        self.problem_combo.addItems(["미검수", "정상", "문제"])
        self.problem_combo.currentIndexChanged.connect(self._on_meta_changed)
        prob_row.addWidget(self.problem_combo)
        prob_row.addStretch()
        v.addLayout(prob_row)

        reason_row = QHBoxLayout()
        reason_row.addWidget(QLabel("메모"))
        self.reason_edit = QLineEdit()
        self.reason_edit.editingFinished.connect(self._on_meta_changed)
        reason_row.addWidget(self.reason_edit, 1)
        v.addLayout(reason_row)

        return box

    # ---------- 외부 API ----------
    def set_shapes(self, shapes: list[dict], callback=None):
        def _then():
            self._shapes = shapes
            self._current_index = -1
            self._populate_table_list()
            self._apply_table_format(TABLE_FORMAT_HTML)
            self.editor.set_table_text("")
            self._set_meta(None, "")
            if callback is not None:
                callback()
        self.editor.ensure_pulled(_then)

    def toggle_edit_mode(self):
        """외부 호출 — 표 편집 모드 토글."""
        self.editor.toggle_edit_mode()

    def set_edit_mode(self, enabled: bool):
        self.editor.set_edit_mode(enabled)

    def set_focus_mode(self, enabled: bool):
        """표 집중 모드에서는 목록/메모를 숨기고 편집기를 크게 보여준다."""
        self.table_list.setVisible(not enabled)
        self.meta_box.setVisible(not enabled)

    def ensure_pulled(self, callback):
        """편집 중인 변경사항을 동기화한 뒤 callback. 외부 트리거(저장/이미지 전환)에서 사용."""
        self.editor.ensure_pulled(callback)

    def select_shape(self, idx: int):
        """외부 호출 — 시그널 emit 없이 표시 상태만 갱신.

        이전 shape에서 편집 중이던 변경사항을 먼저 풀백해 self._shapes에 반영한 뒤
        새 shape의 현재 포맷 원본 문자열을 로드한다.
        """
        if idx < 0 or idx >= len(self._shapes):
            return
        if idx == self._current_index:
            self._highlight_in_list(idx)
            return

        def _then():
            self._current_index = idx
            shape = self._shapes[idx]
            detected_format = self._detect_table_format(shape)
            self._apply_table_format(detected_format)
            attrs = shape.get("attributes") if isinstance(shape.get("attributes"), dict) else {}
            spans_attr = attrs.get(TABLE_SPANS_ATTR, "")
            self.editor.set_table_text(
                shape.get("flags", {}).get("text", "") or shape.get("latex") or "",
                spans_attr if isinstance(spans_attr, str) else "",
            )
            self._set_meta(shape.get("is_problem"), shape.get("problem_reason") or "")
            self._highlight_in_list(idx)

        self.editor.ensure_pulled(_then)

    # ---------- 내부 ----------
    def _populate_table_list(self):
        self.table_list.clear()
        for idx, shape in enumerate(self._shapes):
            if shape.get("label") != "TABLE":
                continue
            problem = shape.get("is_problem")
            badge = "문제" if problem is True else ("정상" if problem is False else "대기")
            item = QListWidgetItem(f"{badge}  TABLE #{idx}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            text_value = shape.get("flags", {}).get("text", "") or shape.get("latex") or ""
            if str(text_value).strip():
                item.setForeground(QBrush(QColor("#15803d")))
            else:
                item.setForeground(QBrush(QColor("#b91c1c")))
            self.table_list.addItem(item)
        self._highlight_in_list(self._current_index)

    def _highlight_in_list(self, idx: int):
        for i in range(self.table_list.count()):
            it = self.table_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == idx:
                self.table_list.setCurrentItem(it)
                return
        self.table_list.clearSelection()

    def _set_meta(self, problem, reason: str):
        self.problem_combo.blockSignals(True)
        self.problem_combo.setCurrentIndex(_PROBLEM_TO_INDEX.get(problem, 0))
        self.problem_combo.blockSignals(False)
        self.reason_edit.blockSignals(True)
        self.reason_edit.setText(reason)
        self.reason_edit.blockSignals(False)

    # ---------- 이벤트 ----------
    def _on_list_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        self.shape_selected.emit(idx)

    def _on_meta_changed(self):
        if self._current_index < 0 or self._current_index >= len(self._shapes):
            return
        shape = self._shapes[self._current_index]
        shape["is_problem"] = _INDEX_TO_PROBLEM[self.problem_combo.currentIndex()]
        shape["problem_reason"] = self.reason_edit.text()
        self._populate_table_list()

    def _on_editor_text_changed(self, text: str):
        if self._current_index < 0 or self._current_index >= len(self._shapes):
            return
        shape = self._shapes[self._current_index]
        shape.setdefault("flags", {})["text"] = text
        if "latex" in shape:
            shape["latex"] = text

    def _on_editor_spans_changed(self, spans_attr: str):
        if self._current_index < 0 or self._current_index >= len(self._shapes):
            return
        attrs = self._ensure_attributes(self._shapes[self._current_index])
        if spans_attr:
            attrs[TABLE_SPANS_ATTR] = spans_attr
        else:
            attrs.pop(TABLE_SPANS_ATTR, None)

    def _on_format_changed(self):
        table_format = self.table_format_combo.currentData() or TABLE_FORMAT_HTML

        def _then():
            self._apply_table_format(table_format, emit_status=True)

        self.editor.ensure_pulled(_then)

    @staticmethod
    def _ensure_attributes(shape: dict) -> dict:
        attrs = shape.get("attributes")
        if not isinstance(attrs, dict):
            attrs = {}
            shape["attributes"] = attrs
        return attrs

    def _apply_table_format(self, table_format: str, emit_status: bool = False):
        if table_format not in {TABLE_FORMAT_HTML, TABLE_FORMAT_MARKDOWN}:
            table_format = TABLE_FORMAT_HTML
        index = self.table_format_combo.findData(table_format)
        self.table_format_combo.blockSignals(True)
        if index >= 0:
            self.table_format_combo.setCurrentIndex(index)
        self.table_format_combo.blockSignals(False)
        self.editor.set_table_format(table_format)
        if emit_status:
            self.status_message.emit(f"표 포맷: {TABLE_FORMAT_LABELS[table_format]}")

    def _detect_table_format(self, shape: dict) -> str:
        attrs = shape.get("attributes") if isinstance(shape.get("attributes"), dict) else {}
        spans_attr = attrs.get(TABLE_SPANS_ATTR, "")
        if isinstance(spans_attr, str) and spans_attr.strip():
            return TABLE_FORMAT_MARKDOWN

        text = shape.get("flags", {}).get("text", "") or shape.get("latex") or ""
        text = str(text or "").strip()
        if not text:
            return TABLE_FORMAT_HTML
        if _HTML_TABLE_RE.search(text):
            return TABLE_FORMAT_HTML
        try:
            render_source_to_html(text, TABLE_FORMAT_MARKDOWN)
        except TableFormatError:
            return TABLE_FORMAT_HTML
        return TABLE_FORMAT_MARKDOWN
