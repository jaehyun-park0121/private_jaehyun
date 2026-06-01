from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.common.panel_layout import DEFAULT_LEFT_PANEL_WIDTH
from ..widgets.multi_select_button_group import MultiSelectButtonGroup
from app.common.config.config_manager import ConfigManager
from ..ui_shared import (
    _ACTION_BTN_STYLE,
    _COMPACT_TAB_STYLE,
    _DEFAULT_HIGHLIGHT_RULES,
    _FORM_PAGE_MARGINS,
    _GROUP_BOX_STYLE,
    _GROUP_CONTENT_MARGINS,
    _GROUP_CONTENT_SPACING,
    _LINE_EDIT_STYLE,
    _PANEL_MARGINS,
    _PANEL_SPACING,
    load_text_label_options,
    normalize_highlight_rules,
)

class RawDataAnalysisLeftPanel(QWidget):
    run_requested = pyqtSignal()
    export_excel_requested = pyqtSignal()
    export_gsheet_requested = pyqtSignal()
    status_message = pyqtSignal(str)
    highlight_rules_applied = pyqtSignal(dict)

    def __init__(self, project_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.project_root = project_root
        self._text_label_options = load_text_label_options(project_root)

        self.output_tabs = QTabWidget()
        self.output_tabs.setObjectName("rawDataCompactTabs")
        self.output_tabs.setStyleSheet(_COMPACT_TAB_STYLE)
        self.output_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.s3_uri_input = self._build_line_edit()
        self.aws_access_key_input = self._build_line_edit()
        self.aws_secret_key_input = self._build_line_edit()
        self.aws_secret_key_input.setEchoMode(QLineEdit.Password)
        self.aws_region_input = self._build_line_edit()
        self.output_dir_input = self._build_line_edit(str((project_root / "outputs").resolve()))
        self.gsheet_url_input = self._build_line_edit()
        self.gsheet_url_input.setPlaceholderText("스프레드시트 URL")
        self.gsheet_tab_input = self._build_line_edit("2. 도서 정보")

        self.run_btn = QPushButton("분석 실행")
        self.run_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self.run_btn.clicked.connect(self.run_requested.emit)

        self.export_excel_btn = QPushButton("엑셀로 저장하기")
        self.export_excel_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self.export_excel_btn.setEnabled(False)
        self.export_excel_btn.clicked.connect(self.export_excel_requested.emit)

        self.export_gsheet_btn = QPushButton("구글 스프레드시트 입력")
        self.export_gsheet_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self.export_gsheet_btn.setEnabled(False)
        self.export_gsheet_btn.clicked.connect(self.export_gsheet_requested.emit)

        input_group = QGroupBox("텍스트 검사 대상 라벨")
        input_group.setStyleSheet(_GROUP_BOX_STYLE)
        input_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        input_layout = QVBoxLayout(input_group)
        input_layout.setContentsMargins(*_GROUP_CONTENT_MARGINS)
        input_layout.setSpacing(_GROUP_CONTENT_SPACING)
        self.text_label_selector = MultiSelectButtonGroup(
            self._text_label_options,
            default_values=self._default_selected_labels(),
            columns=3,
        )
        input_layout.addWidget(self.text_label_selector)
        input_layout.addWidget(self.run_btn)

        output_group = QGroupBox("출력")
        output_group.setStyleSheet(_GROUP_BOX_STYLE)
        output_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(*_GROUP_CONTENT_MARGINS)
        output_layout.setSpacing(_GROUP_CONTENT_SPACING)
        output_layout.addWidget(self._build_output_tabs())

        root = QVBoxLayout(self)
        root.setContentsMargins(*_PANEL_MARGINS)
        root.setSpacing(_PANEL_SPACING)
        root.addWidget(input_group, 0)
        root.addWidget(self._build_highlight_rules_box(), 0)
        root.addWidget(output_group, 0)
        root.addStretch(1)
        self.setMinimumWidth(DEFAULT_LEFT_PANEL_WIDTH)

        self._apply_config_defaults()

    def _default_selected_labels(self) -> List[str]:
        selected: List[str] = []
        for option in self._text_label_options:
            upper = option.upper()
            if any(keyword in upper for keyword in ("TEXT", "TITLE", "CAPTION", "FOOTNOTE")):
                selected.append(option)
        return selected or self._text_label_options[:4]

    def _build_line_edit(self, value: str = "") -> QLineEdit:
        line_edit = QLineEdit(value)
        line_edit.setStyleSheet(_LINE_EDIT_STYLE)
        line_edit.setFixedHeight(26)
        return line_edit

    def _build_highlight_rules_box(self) -> QWidget:
        group = QGroupBox("하이라이트 규칙")
        group.setStyleSheet(_GROUP_BOX_STYLE)
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        layout = QGridLayout(group)
        layout.setContentsMargins(*_FORM_PAGE_MARGINS)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(8)

        self.lower_rank_percent_input = self._build_line_edit(str(int(_DEFAULT_HIGHLIGHT_RULES["lower_rank_percent"])))
        self.upper_rank_percent_input = self._build_line_edit(str(int(_DEFAULT_HIGHLIGHT_RULES["upper_rank_percent"])))
        self.space_min_input = self._build_line_edit(f"{_DEFAULT_HIGHLIGHT_RULES['space_min']:.2f}")
        self.space_max_input = self._build_line_edit(f"{_DEFAULT_HIGHLIGHT_RULES['space_max']:.2f}")

        apply_btn = QPushButton("규칙 적용")
        apply_btn.setStyleSheet(_ACTION_BTN_STYLE)
        apply_btn.clicked.connect(self._emit_highlight_rules)

        layout.addWidget(self._form_label("하위 %"), 0, 0)
        layout.addWidget(self.lower_rank_percent_input, 0, 1)
        layout.addWidget(self._form_label("상위 %"), 0, 2)
        layout.addWidget(self.upper_rank_percent_input, 0, 3)
        layout.addWidget(self._form_label("띄어쓰기 최소"), 1, 0)
        layout.addWidget(self.space_min_input, 1, 1)
        layout.addWidget(self._form_label("띄어쓰기 최대"), 1, 2)
        layout.addWidget(self.space_max_input, 1, 3)
        layout.addWidget(apply_btn, 2, 0, 1, 4)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        return group

    def _emit_highlight_rules(self) -> None:
        rules = self.current_highlight_rules()
        self.lower_rank_percent_input.setText(str(int(rules["lower_rank_percent"])))
        self.upper_rank_percent_input.setText(str(int(rules["upper_rank_percent"])))
        self.space_min_input.setText(f"{rules['space_min']:.2f}")
        self.space_max_input.setText(f"{rules['space_max']:.2f}")
        self.highlight_rules_applied.emit(rules)
        self.status_message.emit("하이라이트 규칙을 적용했습니다.")

    def current_highlight_rules(self) -> dict:
        return normalize_highlight_rules(
            {
                "lower_rank_percent": self.lower_rank_percent_input.text().strip(),
                "upper_rank_percent": self.upper_rank_percent_input.text().strip(),
                "space_min": self.space_min_input.text().strip(),
                "space_max": self.space_max_input.text().strip(),
            }
        )

    def _form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedHeight(26)
        label.setStyleSheet("color: #475569; background: transparent; border: none;")
        return label

    def _build_output_tabs(self) -> QWidget:
        excel_page = QWidget()
        excel_layout = QGridLayout(excel_page)
        excel_layout.setContentsMargins(*_FORM_PAGE_MARGINS)
        excel_layout.setHorizontalSpacing(6)
        excel_layout.setVerticalSpacing(8)
        browse_output_btn = QPushButton("폴더 선택")
        browse_output_btn.setStyleSheet(_ACTION_BTN_STYLE)
        browse_output_btn.clicked.connect(self._browse_output_dir)
        excel_layout.addWidget(self._form_label("결과 폴더"), 0, 0)
        excel_layout.addWidget(self.output_dir_input, 0, 1)
        excel_layout.addWidget(browse_output_btn, 0, 2)
        excel_layout.setRowStretch(1, 1)
        excel_layout.addWidget(self.export_excel_btn, 2, 0, 1, 3)
        excel_layout.setColumnStretch(1, 1)

        gsheet_page = QWidget()
        gsheet_layout = QGridLayout(gsheet_page)
        gsheet_layout.setContentsMargins(*_FORM_PAGE_MARGINS)
        gsheet_layout.setHorizontalSpacing(6)
        gsheet_layout.setVerticalSpacing(8)

        gsheet_layout.addWidget(self._form_label("시트 URL"), 0, 0)
        gsheet_layout.addWidget(self.gsheet_url_input, 0, 1, 1, 2)
        gsheet_layout.addWidget(self._form_label("탭명"), 1, 0)
        gsheet_layout.addWidget(self.gsheet_tab_input, 1, 1, 1, 2)
        gsheet_layout.setRowStretch(2, 1)
        gsheet_layout.addWidget(self.export_gsheet_btn, 3, 0, 1, 3)
        gsheet_layout.setColumnStretch(1, 1)

        self.output_tabs.addTab(excel_page, "엑셀로 저장하기")
        self.output_tabs.addTab(gsheet_page, "구글 스프레드시트 입력")
        return self.output_tabs

    def apply_shared_settings(self, config: Optional[dict] = None) -> None:
        if config is None:
            config = ConfigManager(self.project_root / "config" / "default.yaml").load()
        project = config.get("project", {})
        aws = config.get("aws", {})

        s3_path = str(project.get("s3_path", "")).strip()
        output_path = str(project.get("output_path", "")).strip()
        access_key = str(aws.get("access_key", "")).strip()
        secret_key = str(aws.get("secret_key", "")).strip()
        region = str(aws.get("region", "")).strip() or "ap-northeast-2"

        self.s3_uri_input.setText(s3_path)
        self.aws_access_key_input.setText(access_key)
        self.aws_secret_key_input.setText(secret_key)
        self.aws_region_input.setText(region)

        resolved_output = ""
        if output_path:
            resolved_output = Path(output_path)
            if not resolved_output.is_absolute():
                resolved_output = (self.project_root / resolved_output).resolve()
            resolved_output = str(resolved_output)
        self.output_dir_input.setText(resolved_output)

    def _apply_config_defaults(self) -> None:
        self.apply_shared_settings()

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "결과 폴더 선택",
            self.output_dir_input.text().strip() or str((self.project_root / "outputs").resolve()),
        )
        if path:
            self.output_dir_input.setText(path)
            self.status_message.emit(f"결과 폴더를 선택했습니다: {path}")

