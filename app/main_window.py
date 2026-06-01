from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabBar, QTabWidget, QVBoxLayout, QWidget

from app.common.aws_settings_dialog import AwsSettingsDialog
from app.common.config.config_manager import ConfigManager
from app.common.shared_status_bar import SharedStatusBarWidget, format_progress_status
from app.common.top_bar import TopBarWidget
from app.tabs.misc_tools import MiscToolsTabPage
from app.tabs.pre_parse import PreParseTabPage
from app.tabs.raw_data_analysis import RawDataAnalysisTabPage
from app.tabs.text_analysis import TextAnalysisTabPage


class MainTabBar(QTabBar):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setExpanding(False)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideRight)
        self.setDrawBase(False)

    def tabSizeHint(self, index: int) -> QSize:  # type: ignore[override]
        base = super().tabSizeHint(index)
        text = self.tabText(index)
        text_width = self.fontMetrics().horizontalAdvance(text)
        return QSize(max(base.width(), text_width + 40), max(base.height(), 22))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("품질 검수 도구")
        self.resize(1600, 900)

        self._initialize_state()
        self._create_tab_widgets()
        self._build_layout()
        self.menuBar().setVisible(False)
        self._wire_events()
        self._load_initial_data()
        self._apply_app_style()
        self._set_progress("대기", 0, 1)

    def _initialize_state(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.config_manager = ConfigManager(self.project_root / "config" / "default.yaml")
        self.config = self.config_manager.load()

    def _create_tab_widgets(self) -> None:
        self.top_bar = TopBarWidget()
        self.raw_data_tab = RawDataAnalysisTabPage()
        self.pre_parse_tab = PreParseTabPage(
            project_root=self.project_root,
            config=self.config,
            top_bar=self.top_bar,
            status_callback=self._set_recent_log,
        )
        self.text_analysis_tab = TextAnalysisTabPage(
            project_root=self.project_root,
            config=self.config,
            status_callback=self._set_recent_log,
        )
        self.misc_tools_tab = MiscToolsTabPage()

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.top_bar)

        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")
        self.main_tabs.setTabBar(MainTabBar(self.main_tabs))
        self.main_tabs.addTab(self.raw_data_tab, "원시 데이터 분석")
        self.main_tabs.addTab(self.text_analysis_tab, "텍스트 분석")
        self.main_tabs.addTab(self.pre_parse_tab, "파싱 전 검사")
        self.main_tabs.addTab(self.misc_tools_tab, "기타 도구")
        for index in range(self.main_tabs.count()):
            self.main_tabs.setTabToolTip(index, self.main_tabs.tabText(index))
        layout.addWidget(self.main_tabs, 1)

        self.shared_status_bar = SharedStatusBarWidget()
        layout.addWidget(self.shared_status_bar)
        self.setCentralWidget(root)

    def _wire_events(self) -> None:
        self.top_bar.settings_btn.clicked.connect(self._open_settings_dialog)
        self.raw_data_tab.status_message_requested.connect(self._set_recent_log)
        self.raw_data_tab.status_progress_requested.connect(self._set_progress)
        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)

    def _load_initial_data(self) -> None:
        self._refresh_top_project_info()
        self.raw_data_tab.apply_shared_settings(self.config)
        self.pre_parse_tab.refresh_books_from_s3(show_message=False)
        self.text_analysis_tab.refresh_books_from_s3(show_message=False)
        self._on_main_tab_changed(self.main_tabs.currentIndex())

    def _on_main_tab_changed(self, index: int) -> None:
        widget = self.main_tabs.widget(index)
        if widget is None:
            return
        ensure_sizes = getattr(widget, "_ensure_initial_splitter_sizes", None)
        if callable(ensure_sizes):
            ensure_sizes()

    def _open_settings_dialog(self) -> None:
        if self.pre_parse_tab.is_running():
            QMessageBox.information(
                self,
                "검사 실행 중",
                "파싱 전 검사가 실행 중입니다. 완료되거나 중지된 뒤 다시 시도해 주세요.",
            )
            return

        dialog = AwsSettingsDialog(self.config, self)
        if dialog.exec_() != dialog.Accepted:
            return

        updates = dialog.to_config()
        previous_config = copy.deepcopy(self.config)
        self.config = self._merged_config(self.config, updates)
        self.config_manager.save(self.config)
        should_refresh_s3 = self._s3_settings_changed(previous_config, self.config)

        self._refresh_top_project_info()
        self.raw_data_tab.apply_shared_settings(self.config)
        self.pre_parse_tab.apply_shared_settings(
            self.config,
            show_message=True,
            refresh_s3=should_refresh_s3,
        )
        self.text_analysis_tab.apply_shared_settings(
            self.config,
            show_message=True,
            refresh_s3=should_refresh_s3,
        )
        if not should_refresh_s3:
            self._set_recent_log("S3 설정 변경 없음: 기존 도서/페이지 목록을 유지합니다.")

    def _refresh_top_project_info(self) -> None:
        project = self.config.get("project", {})
        self.top_bar.update_project_settings(
            s3_path=str(project.get("s3_path", "")),
            output_path=str(project.get("output_path", "")),
        )

    def _set_recent_log(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return
        now = datetime.now().strftime("%H:%M:%S")
        self.shared_status_bar.set_message(f"[{now}] {text}")

    def _set_progress(self, desc: str, current: int, total: int) -> None:
        self._set_recent_log(format_progress_status(desc, current, total))

    def _s3_settings_changed(self, previous: dict, current: dict) -> bool:
        previous_project = previous.get("project", {}) if isinstance(previous, dict) else {}
        current_project = current.get("project", {}) if isinstance(current, dict) else {}
        previous_aws = previous.get("aws", {}) if isinstance(previous, dict) else {}
        current_aws = current.get("aws", {}) if isinstance(current, dict) else {}

        project_keys = ["s3_path"]
        aws_keys = [
            "access_key",
            "secret_key",
            "session_token",
            "region",
            "default_bucket",
            "default_prefix",
        ]

        for key in project_keys:
            if str(previous_project.get(key, "") or "").strip() != str(current_project.get(key, "") or "").strip():
                return True
        for key in aws_keys:
            if str(previous_aws.get(key, "") or "").strip() != str(current_aws.get(key, "") or "").strip():
                return True
        return False

    def _merged_config(self, base: dict, updates: dict) -> dict:
        merged = copy.deepcopy(base)
        for key, value in updates.items():
            if isinstance(value, dict):
                if key == "parallel":
                    merged[key] = copy.deepcopy(value)
                    continue
                section = merged.get(key, {})
                if not isinstance(section, dict):
                    section = {}
                section.update(value)
                merged[key] = section
            else:
                merged[key] = value
        return merged

    def _apply_app_style(self) -> None:
        app_style = """
            QMainWindow {
                background: #f2f4f7;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 8px;
                margin-top: 8px;
                font-weight: 600;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QTableWidget, QListWidget, QTextEdit {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 6px;
                gridline-color: #edf1f7;
            }
            QHeaderView::section {
                background: #f6f8fc;
                border: 0;
                border-right: 1px solid #edf1f7;
                border-bottom: 1px solid #edf1f7;
                padding: 6px;
                font-weight: 600;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: #f8fafc;
            }
            QToolButton {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QToolButton:hover {
                background: #f8fafc;
            }
            QTabWidget#mainTabs::pane {
                border: none;
                border-radius: 0px;
                top: 0px;
                border-left: 1px solid #dfe5ef;
                border-right: 1px solid #dfe5ef;
                border-bottom: 1px solid #dfe5ef;
                background: #ffffff;
            }
            QTabWidget#mainTabs QTabBar {
                left: 6px;
                background: transparent;
                border: none;
                border-top: none;
            }
            QTabWidget#mainTabs QTabBar::tab {
                background: #eef1f5;
                color: #1f2937;
                border: 1px solid #d8dee8;
                border-radius: 0px;
                font-weight: 600;
                padding: 4px 14px;
                min-width: 56px;
                margin-right: 2px;
            }
            QTabWidget#mainTabs QTabBar::tab:selected {
                background: #ffffff;
                border-bottom: 1px solid #ffffff;
            }
            QTabWidget#mainTabs QTabBar::tab:!selected {
                margin-top: 1px;
            }
            QMenuBar {
                background: #efefef;
            }
            QMenuBar::item:selected {
                background: #d8eafe;
            }
            #bottomLogBar {
                background: #f7f8fa;
                border-top: 1px solid #e5e7eb;
            }
            #recentLogLabel {
                color: #9ca3af;
                font-size: 11px;
                padding: 2px 0;
            }
            QToolTip {
                background-color: #ffffff;
                color: #94a3b8;
                border: 1px solid #cbd5e1;
                padding: 6px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
        """
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(app_style)
