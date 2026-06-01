from typing import Optional

from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class TopBarWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBarWidget")

        self.s3_tag_label = QLabel("S3")
        self.s3_tag_label.setObjectName("infoTag")
        self.s3_info_label = QLabel("-")
        self.s3_info_label.setObjectName("infoValue")
        self.s3_info_label.setToolTip("-")
        self.s3_info_label.setMinimumWidth(280)
        self.s3_info_label.setMaximumWidth(520)

        self.path_tag_label = QLabel("Output")
        self.path_tag_label.setObjectName("infoTag")
        self.path_info_label = QLabel("-")
        self.path_info_label.setObjectName("infoValue")
        self.path_info_label.setToolTip("-")
        self.path_info_label.setMinimumWidth(220)
        self.path_info_label.setMaximumWidth(440)

        self.settings_btn = QPushButton("설정")
        self.settings_btn.setObjectName("headerActionBtn")

        dark_title = QLabel("설정 정보")
        dark_title.setObjectName("darkTitle")

        dark_header = QFrame()
        dark_header.setObjectName("darkHeader")
        dark_header_layout = QHBoxLayout(dark_header)
        dark_header_layout.setContentsMargins(10, 8, 10, 8)
        dark_header_layout.setSpacing(12)
        dark_header_layout.addWidget(dark_title)
        dark_header_layout.addSpacing(16)
        dark_header_layout.addWidget(self.s3_tag_label)
        dark_header_layout.addWidget(self.s3_info_label, 1)
        dark_header_layout.addWidget(self.path_tag_label)
        dark_header_layout.addWidget(self.path_info_label, 1)
        dark_header_layout.addStretch(1)
        dark_header_layout.addWidget(self.settings_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(dark_header)

        self._output_hidden = False
        self.installEventFilter(self)
        self._update_responsive_state()
        self._apply_style()

    def update_stats(
        self, total_books: int, total_pages: int, error_pages: int, total_issues: int, pass_rate: float
    ) -> None:
        del total_books, total_pages, error_pages, total_issues, pass_rate

    def update_project_settings(self, s3_path: str, output_path: str) -> None:
        compact_s3 = self._compact_text(s3_path or "-")
        compact_path = self._compact_text(output_path or "-")
        self.s3_info_label.setText(compact_s3)
        self.s3_info_label.setToolTip(s3_path or "-")
        self.path_info_label.setText(compact_path)
        self.path_info_label.setToolTip(output_path or "-")
        self._update_responsive_state()

    def _compact_text(self, value: str, max_len: int = 48) -> str:
        if len(value) <= max_len:
            return value
        keep = max_len // 2 - 2
        return f"{value[:keep]}...{value[-keep:]}"

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self and event.type() == QEvent.Resize:
            self._update_responsive_state()
        return super().eventFilter(obj, event)

    def _update_responsive_state(self) -> None:
        should_hide_output = self.width() < 1320
        if should_hide_output == self._output_hidden:
            return
        self._output_hidden = should_hide_output
        self.path_tag_label.setVisible(not should_hide_output)
        self.path_info_label.setVisible(not should_hide_output)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            #darkHeader {
                background-color: #111217;
                border-bottom: none;
            }
            #darkTitle {
                color: #ffffff;
                font-weight: 700;
            }
            #darkHeader QLabel {
                color: #d7d9e0;
            }
            #infoTag {
                color: #a4adbe;
                font-weight: 600;
                padding: 2px 4px;
            }
            #infoValue {
                color: #f2f4f8;
                background: #1e2230;
                border: 1px solid #2f3647;
                border-radius: 4px;
                padding: 3px 8px;
            }
            #darkHeader QPushButton {
                background: transparent;
                color: #d7d9e0;
                border: none;
                padding: 4px 8px;
                text-align: left;
            }
            #darkHeader QPushButton:hover {
                color: #ffffff;
                background: #232834;
                border-radius: 4px;
            }
            #darkHeader #headerActionBtn {
                border: 1px solid #3c4355;
                border-radius: 8px;
                padding: 4px 8px;
            }
            #darkHeader #headerActionBtn:hover {
                border-color: #4d5670;
            }
            """
        )
