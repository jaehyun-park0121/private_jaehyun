from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.common.config.parallel_settings import (
    build_parallel_config,
    cpu_core_count,
    default_parallel_workers,
    get_parallel_config,
)


class AwsSettingsDialog(QDialog):
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AWS 정보 설정")
        self.setModal(True)
        self.setMinimumWidth(560)

        aws_config = config.get("aws", {})
        project_config = config.get("project", {})
        parallel_config = get_parallel_config(config)
        self._cpu_core_count = cpu_core_count()
        self._default_parallel_workers = default_parallel_workers()

        self.access_key_input = QLineEdit(str(aws_config.get("access_key", "")))
        self.access_key_input.setPlaceholderText("AWS Access Key")

        self.secret_key_input = QLineEdit(str(aws_config.get("secret_key", "")))
        self.secret_key_input.setPlaceholderText("AWS Secret Key")

        self.region_input = QLineEdit(str(aws_config.get("region", "ap-northeast-2")))
        self.region_input.setPlaceholderText("ap-northeast-2")

        default_bucket = str(aws_config.get("default_bucket", "")).strip()
        default_prefix = str(aws_config.get("default_prefix", "")).strip()
        configured_s3_path = str(project_config.get("s3_path", "")).strip()
        if configured_s3_path:
            self._existing_s3_path = configured_s3_path
        elif default_bucket:
            self._existing_s3_path = f"s3://{default_bucket}/{default_prefix}".rstrip("/")
        else:
            self._existing_s3_path = ""

        self.s3_path_input = QLineEdit(self._existing_s3_path)
        self.s3_path_input.setStyleSheet("color: #111111;")
        self.s3_path_input.setPlaceholderText("s3://project-25-ss-001/project0000/storage/")

        self.project_path_input = QLineEdit(str(project_config.get("output_path", "")))
        self.project_path_input.setPlaceholderText("프로젝트 결과 경로")

        browse_btn = QPushButton("찾아보기")
        browse_btn.clicked.connect(self._browse_project_path)
        project_row = QHBoxLayout()
        project_row.setContentsMargins(0, 0, 0, 0)
        project_row.addWidget(self.project_path_input, 1)
        project_row.addWidget(browse_btn)

        self.parallel_workers_input = QSpinBox()
        self.parallel_workers_input.setRange(1, self._cpu_core_count)
        self.parallel_workers_input.setValue(int(parallel_config.get("max_workers", self._default_parallel_workers)))
        self.parallel_workers_input.setToolTip("모든 멀티프로세스/멀티스레드 풀에서 공통으로 사용할 작업 수입니다.")

        parallel_input_wrap = QWidget()
        parallel_input_layout = QVBoxLayout(parallel_input_wrap)
        parallel_input_layout.setContentsMargins(0, 0, 0, 0)
        parallel_input_layout.setSpacing(4)
        parallel_input_layout.addWidget(self.parallel_workers_input)

        self.parallel_help_label = QLabel(
            f"(CPU 코어 최대값: {self._cpu_core_count}, 기본값: {self._default_parallel_workers})"
        )
        self.parallel_help_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        parallel_input_layout.addWidget(self.parallel_help_label)

        form = QFormLayout()
        form.addRow("Access", self.access_key_input)
        form.addRow("Secret", self.secret_key_input)
        form.addRow("Region", self.region_input)
        form.addRow("S3", self.s3_path_input)
        form.addRow("Project Path", project_row)
        form.addRow("병렬 작업 수", parallel_input_wrap)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Save).setText("저장")
        self.button_box.button(QDialogButtonBox.Cancel).setText("취소")
        self.button_box.accepted.connect(self._on_save_clicked)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(form)
        layout.addWidget(self.button_box)
        self.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

    def _on_save_clicked(self) -> None:
        if not self.access_key_input.text().strip() or not self.secret_key_input.text().strip():
            QMessageBox.warning(self, "입력 필요", "Access Key와 Secret Key는 필수입니다.")
            return
        self.accept()

    def _browse_project_path(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "프로젝트 결과 경로 선택",
            self.project_path_input.text().strip() or str(Path.cwd()),
        )
        if selected:
            self.project_path_input.setText(selected)

    def to_config(self) -> Dict[str, Any]:
        s3_path = self.s3_path_input.text().strip() or self._existing_s3_path
        bucket = ""
        prefix = ""
        if s3_path.startswith("s3://"):
            without_scheme = s3_path[5:]
            if "/" in without_scheme:
                bucket, prefix = without_scheme.split("/", 1)
            else:
                bucket = without_scheme

        config = {
            "project": {
                "s3_path": s3_path,
                "output_path": self.project_path_input.text().strip(),
            },
            "aws": {
                "access_key": self.access_key_input.text().strip(),
                "secret_key": self.secret_key_input.text().strip(),
                "session_token": "",
                "region": self.region_input.text().strip() or "ap-northeast-2",
                "default_bucket": bucket.strip(),
                "default_prefix": prefix.strip(),
            },
        }
        config.update(build_parallel_config(max_workers=self.parallel_workers_input.value()))
        return config
