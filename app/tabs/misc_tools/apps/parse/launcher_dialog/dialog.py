from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .widgets import FocusWheelSpinBox, LabelRuleCard
from .styles import DIALOG_STYLESHEET
from .ui_sections import (
    build_toggle_card,
    clear_grid_layout,
    line_with_button,
    section_header,
)
from .config_io import (
    absolute_text,
    base_directory,
    build_merged_config,
    discover_schema_fields,
    load_config_file,
    load_program_default_workers,
)
from .log_handler import LogHandler
from .process_runner import ProcessRunner


OUTPUT_FIELD_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("문서 레벨", [
        ("work_id", "work_id"),
        ("title", "title"),
        ("identifiers.isbn", "isbn"),
        ("source_format", "source_format"),
        ("category_1", "category_1"),
        ("category_2", "category_2"),
        ("category_3", "category_3"),
        ("author", "author"),
        ("publisher", "publisher"),
        ("published_date", "published_date"),
        ("contents", "contents"),
    ]),
    ("페이지 레벨 (contents[])", [
        ("contents[].page", "page"),
        ("contents[].chapter", "chapter"),
        ("contents[].page_contents", "page_contents"),
        ("contents[].add_info", "add_info"),
    ]),
    ("태그 레벨 (add_info[])", [
        ("contents[].add_info[].tag", "tag"),
        ("contents[].add_info[].type", "type"),
        ("contents[].add_info[].description.value", "description.value"),
        ("contents[].add_info[].caption", "caption"),
        ("contents[].add_info[].file_path", "file_path"),
    ]),
]

_OUTPUT_STATE_PROP = ["optional", "required", "nonempty"]


def _get_output_field_display_name(field_key: str) -> str:
    for _, fields in OUTPUT_FIELD_GROUPS:
        for key, name in fields:
            if key == field_key:
                return name
    return field_key


def _apply_output_btn_state(button: QPushButton, state: int) -> None:
    button.setProperty("fieldState", _OUTPUT_STATE_PROP[state])
    button.style().unpolish(button)
    button.style().polish(button)
    button.update()


EXCEL_COLUMN_KEYS = [
    "work_id",
    "title",
    "isbn",
    "source_format",
    "category_1",
    "category_2",
    "category_3",
    "author",
    "publisher",
    "published_date",
]

DEFAULT_SCHEMA_FIELD_CHOICES = [
    "label",
    "points",
    "flags",
    "flags.text",
    "group_id",
    "shape_type",
]


class ParseLauncherDialog(QDialog):

    def __init__(self, parse_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.parse_root = parse_root
        self.config_path = self.parse_root / "config" / "parser_config.json"
        self._raw_config: dict[str, Any] = {}
        self._schema_field_buttons: dict[str, QPushButton] = {}
        self._schema_field_choice_order: list[str] = []
        self._extra_excel_columns: dict[str, str] = {}
        self._schema_top_level_shapes_key = "shapes"
        self._schema_required_shape_fields: list[str] = [
            "label", "points", "flags", "flags.text",
        ]
        self._label_cards: list[LabelRuleCard] = []
        self._active_label_card: Optional[LabelRuleCard] = None
        self._next_label_index = 1
        self._program_default_workers = load_program_default_workers(self.parse_root)
        self._post_parse_config_path = self.parse_root / "post_parse" / "post_parse_config.json"
        self._post_parse_raw_config: dict[str, Any] = {}
        self._output_field_states: dict[str, int] = {}
        self._output_field_buttons: dict[str, QPushButton] = {}

        self.setWindowTitle("문서 파서 실행")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.setMinimumSize(1200, 760)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self._build_ui()
        self._log = LogHandler(self.document_log_view, self.page_log_view)
        self._runner = ProcessRunner(self.parse_root, self._log, parent=self)
        self._runner.started.connect(self._on_runner_started)
        self._runner.finished.connect(self._on_runner_finished)
        self._runner.error_occurred.connect(self._on_runner_error)
        self._runner.status_changed.connect(self.status_label.setText)

        self.setStyleSheet(DIALOG_STYLESHEET)
        self._apply_label_styles()
        self._wire_signals()
        self._load_config(show_message=False)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        self.status_label = QLabel("설정 로드 중...")

        self.input_root_edit = QLineEdit()
        self.output_root_edit = QLineEdit()
        self.workbook_path_edit = QLineEdit()
        self.sheet_name_edit = QLineEdit()
        self.header_row_spin = FocusWheelSpinBox()
        self.header_row_spin.setRange(1, 100000)

        self.excel_column_inputs: dict[str, QLineEdit] = {}
        for key in EXCEL_COLUMN_KEYS:
            editor = QLineEdit()
            editor.setPlaceholderText(f"엑셀 헤더명 ({key})")
            self.excel_column_inputs[key] = editor

        self.strict_required_check = QCheckBox("필수 필드 엄격 검증")
        self.stop_on_validation_error_check = QCheckBox("검증 오류 시 중단")
        self.top_level_shapes_key_edit = QLineEdit()
        self.schema_fields_help_label = QLabel("")
        self.schema_fields_host = QWidget()
        self.schema_fields_grid = QGridLayout(self.schema_fields_host)
        self.schema_fields_grid.setContentsMargins(0, 0, 0, 0)
        self.schema_fields_grid.setHorizontalSpacing(6)
        self.schema_fields_grid.setVerticalSpacing(6)
        self.schema_refresh_btn = QPushButton("")
        self.schema_select_all_btn = QPushButton("")
        self.schema_clear_btn = QPushButton("")

        self.output_validation_enabled_check = QCheckBox("필수 필드 검증")
        self.output_tag_count_check = QCheckBox("태그 수 일치 검사")
        self.output_fields_host = QWidget()
        self.output_fields_layout = QVBoxLayout(self.output_fields_host)
        self.output_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.output_fields_layout.setSpacing(6)

        self.parallel_enabled_check = QCheckBox("문서 병렬 처리")
        self.max_workers_spin = FocusWheelSpinBox()
        self.max_workers_spin.setRange(1, max(1, int(os.cpu_count() or 1)))
        self.parallel_default_label = QLabel("-")

        self.export_pages_check = QCheckBox("pages/ 이미지 내보내기")

        self.labels_summary_label = QLabel("라벨 규칙: 0개")
        self.labels_error_label = QLabel("")
        self.labels_error_label.setVisible(False)
        self.labels_add_slot_btn = QPushButton("+")
        self.labels_add_slot_btn.setObjectName("labelAddSlotButton")
        self.labels_add_slot_btn.setToolTip("새 라벨 규칙 추가")
        self.labels_add_slot_btn.setCursor(Qt.PointingHandCursor)
        self.labels_add_slot_btn.setFixedHeight(LabelRuleCard.CARD_HEIGHT)
        self.labels_cards_host = QWidget()
        self.labels_cards_grid = QGridLayout(self.labels_cards_host)
        self.labels_cards_grid.setContentsMargins(0, 0, 0, 0)
        self.labels_cards_grid.setHorizontalSpacing(8)
        self.labels_cards_grid.setVerticalSpacing(8)
        self.labels_cards_grid.setAlignment(Qt.AlignTop)

        self.reload_btn = QPushButton("설정 다시 불러오기")
        self.save_btn = QPushButton("설정 저장")
        self.run_toggle_btn = QPushButton("실행")
        self.run_toggle_btn.setObjectName("primaryRunButton")
        self.run_toggle_btn.setMinimumHeight(36)
        self.run_toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.run_toggle_btn.setProperty("running", "false")
        self.clear_log_btn = QPushButton("로그 지우기")

        self.document_log_view = QPlainTextEdit()
        self.document_log_view.setReadOnly(True)
        self.document_log_view.setPlaceholderText("도서(폴더) 단위 실행 로그가 표시됩니다.")
        self.document_log_view.setViewportMargins(0, 0, 0, 8)
        self.page_log_view = QPlainTextEdit()
        self.page_log_view.setReadOnly(True)
        self.page_log_view.setPlaceholderText("페이지 단위 처리 로그가 표시됩니다.")
        self.page_log_view.setViewportMargins(0, 0, 0, 8)

        # ── Paths section ──
        paths_group = QGroupBox()
        paths_layout = QVBoxLayout(paths_group)
        paths_layout.setContentsMargins(8, 10, 8, 8)
        paths_layout.setSpacing(8)
        paths_layout.addWidget(
            section_header(
                "경로",
                "문서 스캔 대상 입력 경로와 결과 저장 경로를 설정합니다. 엑셀 파일은 메타데이터 조인을 위한 옵션입니다.",
            )
        )
        paths_form = QFormLayout()
        paths_form.addRow(
            "입력 루트",
            line_with_button(self.input_root_edit, "찾기", self._browse_input_root),
        )
        paths_form.addRow(
            "출력 루트",
            line_with_button(self.output_root_edit, "찾기", self._browse_output_root),
        )
        paths_form.addRow(
            "엑셀 파일",
            line_with_button(self.workbook_path_edit, "찾기", self._browse_workbook),
        )
        paths_layout.addLayout(paths_form)

        # ── Excel metadata section ──
        excel_group = QGroupBox()
        excel_layout = QVBoxLayout(excel_group)
        excel_layout.setContentsMargins(8, 10, 8, 8)
        excel_layout.setSpacing(8)
        excel_layout.addWidget(
            section_header(
                "메타데이터",
                "엑셀 시트에서 문서별 메타데이터를 읽어 결과 JSON 필드에 매핑합니다. 아래 컬럼명은 실제 엑셀 헤더와 동일해야 합니다.",
            )
        )
        excel_form = QFormLayout()
        excel_form.addRow("시트명", self.sheet_name_edit)
        excel_form.addRow("헤더 행", self.header_row_spin)
        excel_layout.addLayout(excel_form)
        columns_group = QGroupBox("컬럼 매핑")
        columns_group.setObjectName("titledCard")
        columns_layout = QHBoxLayout(columns_group)
        columns_layout.setContentsMargins(8, 8, 8, 8)
        columns_layout.setSpacing(10)
        left_form = QFormLayout()
        right_form = QFormLayout()
        left_keys = [
            "work_id", "title", "isbn", "source_format",
            "author", "publisher", "published_date",
        ]
        right_keys = ["category_1", "category_2", "category_3"]
        for key in left_keys:
            left_form.addRow(key, self.excel_column_inputs[key])
        for key in right_keys:
            right_form.addRow(key, self.excel_column_inputs[key])
        left_widget = QWidget()
        left_widget.setLayout(left_form)
        right_widget = QWidget()
        right_widget.setLayout(right_form)
        columns_layout.addWidget(left_widget, 2)
        columns_layout.addWidget(right_widget, 1)
        excel_layout.addWidget(columns_group)

        # ── Schema section ──
        schema_group = QGroupBox()
        schema_layout = QVBoxLayout(schema_group)
        schema_layout.setContentsMargins(8, 10, 8, 8)
        schema_layout.setSpacing(8)
        schema_layout.addWidget(
            section_header(
                "Input 스키마",
                (
                    "입력 JSON의 'shapes' 배열을 기준으로 shape를 검증합니다. "
                    "필수 검증 필드 [label, points, flags, flags.text]가 누락되거나 형식이 다르면 오류로 처리합니다. "
                    "이외 추가 필드는 무시하고 파서에 필요한 필드만 사용합니다."
                ),
            )
        )
        schema_options_grid = QGridLayout()
        schema_options_grid.setContentsMargins(0, 0, 0, 0)
        schema_options_grid.setHorizontalSpacing(8)
        schema_options_grid.setVerticalSpacing(8)
        schema_options_grid.addWidget(
            build_toggle_card(
                self.strict_required_check,
                "체크 시 필수 필드 누락/타입 불일치를 즉시 검증 오류로 판단합니다.",
            ),
            0, 0,
        )
        schema_options_grid.addWidget(
            build_toggle_card(
                self.stop_on_validation_error_check,
                "체크 시 검증 오류가 발생한 문서에서 실행을 중단합니다. 해제 시 다음 페이지 처리로 계속 진행합니다.",
            ),
            0, 1,
        )
        schema_options_grid.setColumnStretch(0, 1)
        schema_options_grid.setColumnStretch(1, 1)
        schema_layout.addLayout(schema_options_grid)

        # ── Output 스키마 section ──
        output_schema_group = QGroupBox()
        output_schema_layout = QVBoxLayout(output_schema_group)
        output_schema_layout.setContentsMargins(8, 10, 8, 8)
        output_schema_layout.setSpacing(8)
        output_schema_layout.addWidget(
            section_header(
                "파싱 후 검사",
                "파싱 완료 후 결과 JSON의 필드 존재/빈 값 여부를 검사합니다.\n"
                "버튼을 클릭할 때마다 상태가 순환합니다:\n"
                "기본(회색, 검사 안 함) → 필수(파란색, 존재해야 함) → 강조(노란색, 빈 값 비허용) → 기본",
            )
        )
        options_grid = QGridLayout()
        options_grid.setContentsMargins(0, 0, 0, 0)
        options_grid.setHorizontalSpacing(8)
        options_grid.setVerticalSpacing(8)
        options_grid.addWidget(
            build_toggle_card(
                self.output_validation_enabled_check,
                "파싱 완료 후 자동으로 필수 필드 존재/빈 값 여부를 검증합니다.",
            ),
            0, 0,
        )
        options_grid.addWidget(
            build_toggle_card(
                self.output_tag_count_check,
                "page_contents와 add_info의 태그 참조 수가 일치하는지 검사합니다.",
            ),
            0, 1,
        )
        options_grid.setColumnStretch(0, 1)
        options_grid.setColumnStretch(1, 1)
        output_schema_layout.addLayout(options_grid)

        self.output_options_widget = QWidget()
        output_options_layout = QVBoxLayout(self.output_options_widget)
        output_options_layout.setContentsMargins(0, 0, 0, 0)
        output_options_layout.setSpacing(8)
        output_options_layout.addWidget(self.output_fields_host)

        output_schema_layout.addWidget(self.output_options_widget)
        self.output_options_widget.setEnabled(False)

        # ── Execution section ──
        execution_group = QGroupBox()
        execution_layout = QVBoxLayout(execution_group)
        execution_layout.setContentsMargins(8, 10, 8, 8)
        execution_layout.setSpacing(8)
        execution_layout.addWidget(
            section_header(
                "실행",
                "병렬 처리와 pages/ 이미지 내보내기 옵션은 실행 시 동작 방식에만 영향을 주며, 파싱 로직 자체는 변경하지 않습니다.",
            )
        )
        parallel_extra = QWidget()
        parallel_extra_layout = QFormLayout(parallel_extra)
        parallel_extra_layout.setContentsMargins(0, 2, 0, 0)
        parallel_extra_layout.setHorizontalSpacing(6)
        parallel_extra_layout.setVerticalSpacing(6)
        parallel_extra_layout.addRow("최대 워커 수", self.max_workers_spin)
        parallel_extra_layout.addRow("", self.parallel_default_label)

        execution_options_grid = QGridLayout()
        execution_options_grid.setContentsMargins(0, 0, 0, 0)
        execution_options_grid.setHorizontalSpacing(8)
        execution_options_grid.setVerticalSpacing(8)
        execution_options_grid.addWidget(
            build_toggle_card(
                self.parallel_enabled_check,
                "여러 문서를 동시에 처리합니다. CPU/메모리 사용량을 고려해 워커 수를 조절하세요.",
                extra=parallel_extra,
            ),
            0, 0,
        )
        execution_options_grid.addWidget(
            build_toggle_card(
                self.export_pages_check,
                "체크 시 결과 출력 시 pages/ 이미지 복사본을 함께 생성합니다.",
            ),
            0, 1,
        )
        execution_options_grid.setColumnStretch(0, 1)
        execution_options_grid.setColumnStretch(1, 1)
        execution_layout.addLayout(execution_options_grid)

        # ── Labels section ──
        labels_group = QGroupBox()
        labels_layout = QVBoxLayout(labels_group)
        labels_layout.setContentsMargins(8, 10, 8, 8)
        labels_layout.setSpacing(8)
        labels_layout.addWidget(
            section_header(
                "라벨 설정",
                "라벨 규칙을 카드 단위로 추가/수정/삭제합니다. + 슬롯으로 새 규칙을 만들 수 있습니다.",
            )
        )
        labels_top_row = QHBoxLayout()
        labels_top_row.setContentsMargins(0, 0, 0, 0)
        labels_top_row.setSpacing(8)
        labels_top_row.addWidget(self.labels_summary_label, 1)
        labels_layout.addLayout(labels_top_row)
        labels_layout.addWidget(self.labels_error_label)
        self.labels_cards_scroll = QScrollArea()
        self.labels_cards_scroll.setWidgetResizable(True)
        self.labels_cards_scroll.setFrameShape(QFrame.NoFrame)
        self.labels_cards_scroll.setWidget(self.labels_cards_host)
        self.labels_cards_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        visible_height = self._label_cards_viewport_height(visible_rows=4)
        self.labels_cards_scroll.setMinimumHeight(visible_height)
        self.labels_cards_scroll.setMaximumHeight(visible_height)
        labels_layout.addWidget(self.labels_cards_scroll)

        # ── Settings panel (left) ──
        settings_panel = QWidget()
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(10)
        settings_layout.addWidget(paths_group)
        settings_layout.addWidget(excel_group)
        # Input 스키마 UI는 요청에 따라 화면에서 숨기되,
        # 기존 config 로드/실행 옵션 참조를 위해 위젯 객체는 유지한다.
        schema_group.setVisible(False)
        settings_layout.addWidget(schema_group)
        settings_layout.addWidget(output_schema_group)
        settings_layout.addWidget(execution_group)
        settings_layout.addWidget(labels_group)
        settings_layout.addStretch(1)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setWidget(settings_panel)

        left_panel = QWidget()
        left_panel.setObjectName("parseLeftPanel")
        left_panel_min_width = (
            (LabelRuleCard.CARD_MIN_WIDTH * 3)
            + (self.labels_cards_grid.horizontalSpacing() * 2)
            + 64
        )
        left_panel.setMinimumWidth(left_panel_min_width)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.settings_scroll, 1)
        left_layout.addWidget(self.run_toggle_btn)

        # ── Logs panel (right) ──
        logs_group = QGroupBox("실행 로그")
        logs_group.setObjectName("titledCard")
        logs_layout = QVBoxLayout(logs_group)
        logs_layout.setContentsMargins(10, 12, 10, 10)
        logs_layout.setSpacing(8)
        log_actions = QHBoxLayout()
        log_actions.setContentsMargins(0, 0, 0, 0)
        log_actions.addStretch(1)
        log_actions.addWidget(self.clear_log_btn)
        logs_layout.addLayout(log_actions)
        def _log_section(title: str, view: QPlainTextEdit) -> QWidget:
            w = QWidget()
            w.setStyleSheet("background: #ffffff;")
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 4, 0, 4)
            lay.setSpacing(4)
            lbl = QLabel(title)
            lbl.setStyleSheet(
                "color: #64748b; font-size: 11px; font-weight: 600;"
                " padding: 0px 2px;"
            )
            lay.addWidget(lbl)
            lay.addWidget(view, 1)
            return w

        log_splitter = QSplitter(Qt.Vertical)
        log_splitter.addWidget(_log_section("도서 단위 로그", self.document_log_view))
        log_splitter.addWidget(_log_section("페이지 단위 로그", self.page_log_view))
        log_splitter.setStretchFactor(0, 1)
        log_splitter.setStretchFactor(1, 1)
        log_splitter.setSizes([320, 320])
        logs_layout.addWidget(log_splitter, 1)

        # ── Main layout ──
        logs_wrapper = QWidget()
        logs_wrapper.setStyleSheet("background: #ffffff;")
        logs_wrapper_layout = QVBoxLayout(logs_wrapper)
        logs_wrapper_layout.setContentsMargins(8, 0, 0, 0)
        logs_wrapper_layout.setSpacing(0)
        logs_wrapper_layout.addWidget(logs_group)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(logs_wrapper)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([900, 560])

        status_row_wrap = QWidget()
        status_row_wrap.setObjectName("parseStatusRow")
        status_row = QHBoxLayout(status_row_wrap)
        status_row.setContentsMargins(10, 8, 10, 8)
        status_row.setSpacing(8)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.reload_btn)
        status_row.addWidget(self.save_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        root.addWidget(status_row_wrap)
        root.addWidget(self.main_splitter, 1)
        self._rebuild_label_cards_layout()

    def _apply_label_styles(self) -> None:
        self.status_label.setStyleSheet(
            "color: #94a3b8; font-size: 12px; font-weight: 400;"
        )
        self.parallel_default_label.setStyleSheet("color: #94a3b8;")
        self.labels_summary_label.setStyleSheet("color: #475569; font-weight: 600;")
        self.labels_error_label.setStyleSheet("color: #dc2626; font-size: 11px;")

    # ── Signals ──────────────────────────────────────────────────

    def _wire_signals(self) -> None:
        self.reload_btn.clicked.connect(lambda: self._load_config(show_message=True))
        self.save_btn.clicked.connect(lambda: self._save_config(show_message=True))
        self.run_toggle_btn.clicked.connect(self._on_run_toggle_clicked)
        self.clear_log_btn.clicked.connect(self._log.clear)
        self.labels_add_slot_btn.clicked.connect(self._on_add_label_slot_clicked)
        self.output_validation_enabled_check.toggled.connect(
            self._set_output_field_controls_enabled
        )

        self.parallel_enabled_check.toggled.connect(self.max_workers_spin.setEnabled)
        self.input_root_edit.editingFinished.connect(
            lambda edit=self.input_root_edit: self._normalize_path_line_edit(edit)
        )
        self.output_root_edit.editingFinished.connect(
            lambda edit=self.output_root_edit: self._normalize_path_line_edit(edit)
        )
        self.workbook_path_edit.editingFinished.connect(
            lambda edit=self.workbook_path_edit: self._normalize_path_line_edit(edit)
        )

    def _on_run_toggle_clicked(self) -> None:
        if self._runner.is_running:
            self._runner.stop()
            return
        self._run_parser()

    def _normalize_path_line_edit(self, line_edit: QLineEdit) -> None:
        normalized = absolute_text(self.config_path.parent, line_edit.text())
        if not normalized:
            line_edit.setText("")
            return
        if normalized != line_edit.text().strip():
            line_edit.setText(normalized)

    # ── Browse dialogs ───────────────────────────────────────────

    def _browse_input_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "입력 루트 선택",
            base_directory(
                self.input_root_edit.text(), self.config_path.parent, self.parse_root
            ),
        )
        if selected:
            self.input_root_edit.setText(
                absolute_text(self.config_path.parent, str(selected))
            )

    def _browse_output_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "출력 루트 선택",
            base_directory(
                self.output_root_edit.text(), self.config_path.parent, self.parse_root
            ),
        )
        if selected:
            self.output_root_edit.setText(
                absolute_text(self.config_path.parent, str(selected))
            )

    def _browse_workbook(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "엑셀 파일 선택",
            base_directory(
                self.workbook_path_edit.text(),
                self.config_path.parent,
                self.parse_root,
            ),
            "Excel Files (*.xlsx *.xlsm *.xls)",
        )
        if selected:
            self.workbook_path_edit.setText(
                absolute_text(self.config_path.parent, str(selected))
            )

    # ── Schema fields ────────────────────────────────────────────

    def _set_schema_field_buttons(self, selected_values: list[str]) -> None:
        selected = {
            value.strip() for value in selected_values if str(value).strip()
        }
        shapes_key = self.top_level_shapes_key_edit.text().strip() or "shapes"
        discovered = discover_schema_fields(
            self.input_root_edit.text(), shapes_key, self.config_path.parent
        )

        choices: list[str] = []
        for value in DEFAULT_SCHEMA_FIELD_CHOICES + discovered + list(selected):
            norm = str(value).strip()
            if not norm or norm == "description" or norm in choices:
                continue
            choices.append(norm)

        self._schema_field_choice_order = choices
        self._schema_field_buttons = {}
        clear_grid_layout(self.schema_fields_grid)

        columns = 4
        for index, choice in enumerate(choices):
            button = QPushButton(choice)
            button.setCheckable(True)
            button.setChecked(choice in selected)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(30)
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
                QPushButton:hover { background: #e2e8f0; }
                QPushButton:checked {
                    background: #dbeafe;
                    border: 1px solid #60a5fa;
                    color: #1d4ed8;
                    font-weight: 600;
                }
                """
            )
            button.toggled.connect(self._update_schema_fields_help_text)
            self._schema_field_buttons[choice] = button
            self.schema_fields_grid.addWidget(
                button, index // columns, index % columns
            )

        self._update_schema_fields_help_text()

    def _selected_schema_fields(self) -> list[str]:
        return [
            value
            for value in self._schema_field_choice_order
            if self._schema_field_buttons.get(value, None)
            and self._schema_field_buttons[value].isChecked()
        ]

    def _update_schema_fields_help_text(self) -> None:
        total = len(self._schema_field_buttons)
        selected = len(self._selected_schema_fields())
        self.schema_fields_help_label.setText(f"필수 필드 선택: {selected} / {total}")

    def _select_all_schema_fields(self) -> None:
        for button in self._schema_field_buttons.values():
            button.setChecked(True)
        self._update_schema_fields_help_text()

    def _clear_schema_fields(self) -> None:
        for button in self._schema_field_buttons.values():
            button.setChecked(False)
        self._update_schema_fields_help_text()

    def _refresh_schema_field_buttons(self) -> None:
        selected = self._selected_schema_fields()
        self._set_schema_field_buttons(selected)

    def _label_cards_viewport_height(self, visible_rows: int) -> int:
        rows = max(1, int(visible_rows))
        spacing = max(0, self.labels_cards_grid.verticalSpacing())
        margins = self.labels_cards_grid.contentsMargins()
        return (
            (LabelRuleCard.CARD_HEIGHT * rows)
            + (spacing * (rows - 1))
            + margins.top()
            + margins.bottom()
            + 2
        )

    def _on_add_label_slot_clicked(self) -> None:
        new_key = self._generate_new_label_key()
        card = self._create_label_card()
        card.set_rule(
            new_key,
            {
                "type": new_key.lower(),
                "use_in_contents": "text",
                "marker": "",
                "crop": False,
                "description_mode": "none",
                "chapter_source": False,
            },
        )
        self._label_cards.append(card)
        self._rebuild_label_cards_layout()
        self._set_active_label_card(card)
        card.label_key_edit.setFocus()
        card.label_key_edit.selectAll()

    def _generate_new_label_key(self) -> str:
        while True:
            candidate = f"NEW_LABEL_{self._next_label_index}"
            self._next_label_index += 1
            exists = any(
                card.label_key_edit.text().strip().upper() == candidate
                for card in self._label_cards
            )
            if not exists:
                return candidate

    def _create_label_card(self) -> LabelRuleCard:
        card = LabelRuleCard(self)
        card.remove_requested.connect(self._on_label_card_remove_requested)
        card.changed.connect(self._on_label_card_changed)
        card.activated.connect(self._on_label_card_activated)
        return card

    def _set_active_label_card(self, card: Optional[LabelRuleCard]) -> None:
        if card not in self._label_cards:
            card = None
        self._active_label_card = card
        for candidate in self._label_cards:
            candidate.set_active(candidate is self._active_label_card)

    def _on_label_card_activated(self, card_obj: object) -> None:
        if not isinstance(card_obj, LabelRuleCard):
            return
        self._set_active_label_card(card_obj)

    def _on_label_card_remove_requested(self, card_obj: object) -> None:
        if not isinstance(card_obj, LabelRuleCard):
            return
        if card_obj not in self._label_cards:
            return
        removed_index = self._label_cards.index(card_obj)
        self._label_cards.remove(card_obj)
        card_obj.deleteLater()
        if self._active_label_card is card_obj:
            self._active_label_card = None
            if self._label_cards:
                fallback_index = min(removed_index, len(self._label_cards) - 1)
                self._active_label_card = self._label_cards[fallback_index]
        self._rebuild_label_cards_layout()
        self._set_active_label_card(self._active_label_card)
        self._clear_label_validation()

    def _on_label_card_changed(self) -> None:
        self._clear_label_validation()
        self._update_labels_summary()

    def _clear_label_validation(self) -> None:
        self.labels_error_label.clear()
        self.labels_error_label.setVisible(False)
        for card in self._label_cards:
            card.set_invalid(False, "")

    def _clear_labels_grid_layout(self) -> None:
        while self.labels_cards_grid.count():
            self.labels_cards_grid.takeAt(0)

    def _rebuild_label_cards_layout(self) -> None:
        self._clear_labels_grid_layout()
        columns = 3
        for idx, card in enumerate(self._label_cards):
            self.labels_cards_grid.addWidget(card, idx // columns, idx % columns)
        add_index = len(self._label_cards)
        self.labels_cards_grid.addWidget(
            self.labels_add_slot_btn, add_index // columns, add_index % columns
        )
        for col in range(columns):
            self.labels_cards_grid.setColumnStretch(col, 1)
        self._set_active_label_card(self._active_label_card)
        self._update_labels_summary()

    def _set_label_cards_from_config(self, labels: Any) -> None:
        for card in self._label_cards:
            card.deleteLater()
        self._label_cards = []
        self._active_label_card = None
        self._next_label_index = 1

        if isinstance(labels, dict):
            for raw_key, raw_rule in labels.items():
                if not isinstance(raw_rule, dict):
                    continue
                key = str(raw_key or "").strip().upper()
                if not key:
                    continue
                card = self._create_label_card()
                card.set_rule(key, raw_rule)
                self._label_cards.append(card)
                if key.startswith("NEW_LABEL_"):
                    try:
                        seq = int(key.split("_")[-1]) + 1
                        self._next_label_index = max(self._next_label_index, seq)
                    except Exception:
                        pass

        self._rebuild_label_cards_layout()
        self._set_active_label_card(None)
        self._clear_label_validation()

    def _update_labels_summary(self) -> None:
        self.labels_summary_label.setText(f"라벨 규칙: {len(self._label_cards)}개")

    def _collect_label_rules(self) -> Optional[dict[str, dict[str, Any]]]:
        key_cards: dict[str, list[LabelRuleCard]] = {}
        rules_by_key: dict[str, dict[str, Any]] = {}
        missing_key_cards: list[LabelRuleCard] = []

        for card in self._label_cards:
            card.set_invalid(False, "")
            key, rule = card.to_rule()
            normalized = str(key or "").strip().upper()
            if not normalized:
                missing_key_cards.append(card)
                continue
            key_cards.setdefault(normalized, []).append(card)
            rules_by_key[normalized] = rule

        duplicate_keys = [key for key, cards in key_cards.items() if len(cards) > 1]

        if missing_key_cards or duplicate_keys:
            for card in missing_key_cards:
                card.set_invalid(True, "라벨 키를 입력해 주세요.")
            for key in duplicate_keys:
                for card in key_cards.get(key, []):
                    card.set_invalid(True, f"중복 라벨 키: {key}")

            messages: list[str] = []
            if missing_key_cards:
                messages.append("빈 라벨 키가 있습니다.")
            if duplicate_keys:
                messages.append(f"중복 라벨 키: {', '.join(sorted(duplicate_keys))}")
            self.labels_error_label.setText(" ".join(messages))
            self.labels_error_label.setVisible(True)
            return None

        if not rules_by_key:
            self.labels_error_label.setText("최소 1개 이상의 라벨 규칙이 필요합니다.")
            self.labels_error_label.setVisible(True)
            return None

        self.labels_error_label.clear()
        self.labels_error_label.setVisible(False)
        return rules_by_key

    # ── Config load / save ───────────────────────────────────────

    def _load_config(self, show_message: bool) -> None:
        try:
            raw = load_config_file(self.config_path)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(
                self, "설정 로드 실패", f"설정 파일을 불러오지 못했습니다.\n{exc}"
            )
            self.status_label.setText("설정 로드 실패")
            return

        self._raw_config = raw
        self._apply_config_to_inputs(raw)
        self._load_post_parse_config()
        self.status_label.setText(f"설정 로드 완료: {self.config_path}")
        if show_message:
            QMessageBox.information(self, "설정 로드", "설정을 다시 불러왔습니다.")

    def _apply_config_to_inputs(self, raw: dict[str, Any]) -> None:
        paths = raw.get("paths", {})
        excel = raw.get("excel", {})
        schema = raw.get("schema", {})
        parser = raw.get("parser", {})
        execution = raw.get("execution", {})
        labels = raw.get("labels", {})

        cfg = self.config_path.parent
        self.input_root_edit.setText(
            absolute_text(cfg, str(paths.get("input_root", "")))
        )
        self.output_root_edit.setText(
            absolute_text(cfg, str(paths.get("output_root", "")))
        )
        self.workbook_path_edit.setText(
            absolute_text(cfg, str(excel.get("workbook_path", "")))
        )
        self.sheet_name_edit.setText(str(excel.get("sheet_name", "")))
        self.header_row_spin.setValue(max(1, int(excel.get("header_row", 1) or 1)))

        columns = excel.get("columns", {})
        if not isinstance(columns, dict):
            columns = {}
        self._extra_excel_columns = {
            str(key): str(value)
            for key, value in columns.items()
            if str(key) not in EXCEL_COLUMN_KEYS
        }
        for key in EXCEL_COLUMN_KEYS:
            self.excel_column_inputs[key].setText(str(columns.get(key, "")))

        self._schema_top_level_shapes_key = (
            str(schema.get("top_level_shapes_key", "shapes")).strip() or "shapes"
        )
        required_fields = schema.get("required_shape_fields", [])
        if not isinstance(required_fields, list):
            required_fields = []
        normalized_required_fields = []
        for value in required_fields:
            norm = str(value).strip()
            if not norm or norm == "description":
                continue
            normalized_required_fields.append(norm)
        if not normalized_required_fields:
            normalized_required_fields = ["label", "points", "flags", "flags.text"]
        self._schema_required_shape_fields = list(normalized_required_fields)
        self.strict_required_check.setChecked(
            bool(schema.get("strict_required_fields", True))
        )
        self.stop_on_validation_error_check.setChecked(
            bool(schema.get("stop_on_validation_error", True))
        )

        self.export_pages_check.setChecked(bool(parser.get("export_pages", True)))

        parallel_enabled = bool(
            execution.get("parallel_enabled", self._program_default_workers > 1)
        )
        # 앱별 저장값보다 프로그램 전역 실행 기본값을 초기값으로 우선 적용한다.
        max_workers = max(1, int(self._program_default_workers))
        self.parallel_enabled_check.setChecked(parallel_enabled)
        self.max_workers_spin.setValue(max_workers)
        self.max_workers_spin.setEnabled(parallel_enabled)
        self.parallel_default_label.setText(
            f"프로그램 실행 기본값(max_workers): {self._program_default_workers}"
        )

        self._set_label_cards_from_config(labels)

    def _collect_inputs(self) -> Optional[dict[str, Any]]:
        cfg = self.config_path.parent
        input_root = absolute_text(cfg, self.input_root_edit.text())
        output_root = absolute_text(cfg, self.output_root_edit.text())
        if not input_root:
            QMessageBox.warning(self, "입력 확인", "입력 루트를 입력해 주세요.")
            return None
        if not output_root:
            QMessageBox.warning(self, "입력 확인", "출력 루트를 입력해 주세요.")
            return None

        required_shape_fields = list(self._schema_required_shape_fields)
        if not required_shape_fields:
            required_shape_fields = ["label", "points", "flags", "flags.text"]

        excel_columns: dict[str, str] = {}
        for key in EXCEL_COLUMN_KEYS:
            value = self.excel_column_inputs[key].text().strip()
            if not value:
                QMessageBox.warning(
                    self, "입력 확인", f"엑셀 컬럼 매핑 값이 비어 있습니다: {key}"
                )
                return None
            excel_columns[key] = value
        excel_columns.update(self._extra_excel_columns)

        label_rules = self._collect_label_rules()
        if label_rules is None:
            QMessageBox.warning(
                self,
                "입력 확인",
                "라벨 설정에 오류가 있습니다. 빨간 테두리 카드와 안내 문구를 확인해 주세요.",
            )
            return None

        return {
            "paths": {
                "input_root": input_root,
                "output_root": output_root,
            },
            "excel": {
                "workbook_path": absolute_text(cfg, self.workbook_path_edit.text()),
                "sheet_name": self.sheet_name_edit.text().strip(),
                "header_row": self.header_row_spin.value(),
                "columns": excel_columns,
            },
            "schema": {
                "top_level_shapes_key": self._schema_top_level_shapes_key or "shapes",
                "required_shape_fields": required_shape_fields,
                "strict_required_fields": self.strict_required_check.isChecked(),
                "stop_on_validation_error": self.stop_on_validation_error_check.isChecked(),
            },
            "parser": {
                "export_pages": self.export_pages_check.isChecked(),
            },
            "execution": {
                "parallel_enabled": self.parallel_enabled_check.isChecked(),
                "max_workers": self.max_workers_spin.value(),
            },
            "labels": label_rules,
        }

    def _save_config(self, show_message: bool) -> bool:
        collected = self._collect_inputs()
        if collected is None:
            return False

        raw = build_merged_config(self._raw_config, collected)

        try:
            self.config_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.warning(
                self, "설정 저장 실패", f"설정 파일 저장 중 오류가 발생했습니다.\n{exc}"
            )
            return False

        self._raw_config = raw
        self.status_label.setText(f"설정 저장 완료: {self.config_path}")
        if show_message:
            QMessageBox.information(self, "설정 저장", "설정을 저장했습니다.")
        return True

    # ── Run / Stop ───────────────────────────────────────────────

    def _set_running(self, running: bool) -> None:
        self.reload_btn.setEnabled(not running)
        self.save_btn.setEnabled(not running)
        self.run_toggle_btn.setText("중지" if running else "실행")
        self.run_toggle_btn.setProperty("running", "true" if running else "false")
        self.run_toggle_btn.style().unpolish(self.run_toggle_btn)
        self.run_toggle_btn.style().polish(self.run_toggle_btn)
        self.run_toggle_btn.update()
        self.settings_scroll.setEnabled(not running)

    def _run_parser(self) -> None:
        if self._runner.is_running:
            QMessageBox.information(self, "실행 중", "이미 실행 중입니다.")
            return

        collected = self._collect_inputs()
        if collected is None:
            return
        runtime_config = build_merged_config(self._raw_config, collected)

        post_parse_enabled = self._is_post_parse_enabled()
        post_parse_config_path = (
            self._post_parse_config_path if post_parse_enabled else None
        )
        self._save_post_parse_config()

        cfg = self.config_path.parent
        output_root = absolute_text(cfg, self.output_root_edit.text())

        if not self._runner.run(
            runtime_config,
            post_parse_config_path=post_parse_config_path,
            post_parse_enabled=post_parse_enabled,
            output_root=output_root,
        ):
            QMessageBox.warning(
                self, "실행 준비 실패", "임시 실행 설정 파일 생성 중 오류가 발생했습니다."
            )
            return
        self._set_running(True)

    def _on_runner_started(self) -> None:
        pass  # status_changed 시그널이 status_label을 직접 업데이트

    def _on_runner_finished(self, exit_code: int) -> None:
        # status_label은 runner.status_changed 시그널로 이미 업데이트됨
        self._set_running(False)

    def _on_runner_error(self, error_msg: str) -> None:
        self._set_running(False)

    # ── Output 스키마 (post_parse) ───────────────────────────────

    def _load_post_parse_config(self) -> None:
        try:
            raw = json.loads(
                self._post_parse_config_path.read_text(encoding="utf-8-sig")
            )
        except (OSError, json.JSONDecodeError):
            raw = {}
        self._post_parse_raw_config = raw
        self._apply_post_parse_config(raw)

    def _apply_post_parse_config(self, raw: dict[str, Any]) -> None:
        field_validation_enabled = bool(
            raw.get("field_validation_enabled", raw.get("enabled", False))
        )
        self.output_validation_enabled_check.setChecked(field_validation_enabled)
        self.output_tag_count_check.setChecked(bool(raw.get("tag_count_check", True)))
        saved_fields = raw.get("fields", {})
        self._output_field_states = {
            str(k): max(0, min(2, int(v)))
            for k, v in saved_fields.items()
        }
        self._rebuild_output_field_buttons()
        self._set_output_field_controls_enabled(
            self.output_validation_enabled_check.isChecked()
        )

    def _rebuild_output_field_buttons(self) -> None:
        # 기존 버튼 제거
        while self.output_fields_layout.count():
            item = self.output_fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._output_field_buttons.clear()

        # 모든 필드 key에 대해 상태 기본값 초기화
        for _, fields in OUTPUT_FIELD_GROUPS:
            for key, _ in fields:
                self._output_field_states.setdefault(key, 0)

        # 범례 — 각 항목을 실제 색으로 표시
        legend_row = QWidget()
        legend_layout = QHBoxLayout(legend_row)
        legend_layout.setContentsMargins(2, 0, 0, 4)
        legend_layout.setSpacing(14)
        _LEGEND = [
            ("●", "#94a3b8", "기본 (검사 안 함)"),
            ("●", "#1d4ed8", "필수 (존재해야 함)"),
            ("●", "#92400e", "강조 (빈 값 비허용)"),
        ]
        for dot, color, label_text in _LEGEND:
            item = QLabel(f'<span style="color:{color};">{dot}</span> {label_text}')
            item.setStyleSheet("font-size: 11px; color: #475569;")
            legend_layout.addWidget(item)
        legend_layout.addStretch(1)
        self.output_fields_layout.addWidget(legend_row)

        for group_name, fields in OUTPUT_FIELD_GROUPS:
            group_label = QLabel(group_name)
            group_label.setObjectName("outputFieldGroupLabel")
            group_label.setContentsMargins(2, 6, 0, 2)
            self.output_fields_layout.addWidget(group_label)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            for field_key, display_name in fields:
                state = self._output_field_states.get(field_key, 0)
                btn = QPushButton(display_name)
                btn.setObjectName("outputFieldButton")
                btn.setCursor(Qt.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                btn.setMinimumHeight(28)
                _apply_output_btn_state(btn, state)
                btn.clicked.connect(
                    lambda _, k=field_key, b=btn: self._on_output_field_clicked(k, b)
                )
                self._output_field_buttons[field_key] = btn
                row_layout.addWidget(btn)

            self.output_fields_layout.addWidget(row_widget)

        self._set_output_field_controls_enabled(
            self.output_validation_enabled_check.isChecked()
        )

    def _on_output_field_clicked(self, field_key: str, button: QPushButton) -> None:
        current = self._output_field_states.get(field_key, 0)
        next_state = (current + 1) % 3
        self._output_field_states[field_key] = next_state
        _apply_output_btn_state(button, next_state)

    def _save_post_parse_config(self) -> None:
        field_validation_enabled = self.output_validation_enabled_check.isChecked()
        tag_count_check = self.output_tag_count_check.isChecked()
        raw = {
            "enabled": field_validation_enabled or tag_count_check,
            "field_validation_enabled": field_validation_enabled,
            "tag_count_check": tag_count_check,
            "fields": dict(self._output_field_states),
        }
        try:
            self._post_parse_config_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass  # 저장 실패는 실행을 막지 않음

    def _is_post_parse_enabled(self) -> bool:
        return (
            self.output_validation_enabled_check.isChecked()
            or self.output_tag_count_check.isChecked()
        )

    def _set_output_field_controls_enabled(self, enabled: bool) -> None:
        if not enabled:
            for field_key in list(self._output_field_states.keys()):
                self._output_field_states[field_key] = 0
            for button in self._output_field_buttons.values():
                _apply_output_btn_state(button, 0)
        self.output_options_widget.setEnabled(enabled)
        for button in self._output_field_buttons.values():
            button.setEnabled(enabled)

    # ── Lifecycle ────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._runner.is_running:
            answer = QMessageBox.question(
                self,
                "실행 중",
                "문서 파서가 실행 중입니다. 창을 닫으면 작업을 중지합니다. 계속할까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._runner.stop()
        self._runner.cleanup()
        super().closeEvent(event)
