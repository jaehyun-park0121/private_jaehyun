from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from app.tabs.misc_tools.base import BaseMiscToolApp


class App(BaseMiscToolApp):
    APP_ID = "table_viewer"
    APP_NAME = "테이블 검수 뷰어"
    CATEGORY = "검수"
    SUMMARY = "TABLE을 검수하기 위한 뷰어입니다. 테이블을 직접 수정하고 결과를 저장할 수 있습니다."
    DESCRIPTION = (
        "JSON과 원본 이미지를 함께 열어 BBOX 위치, TABLE 목록, "
        "HTML/Markdown 표 렌더링 및 편집 결과를 검수하는 PyQt6 뷰어입니다. "
        "로컬 폴더, S3, SSH/SFTP 서버 파일시스템을 입력 소스로 사용할 수 있습니다.\n\n"
        "현재 PyQt5 기반 메인 앱과 Qt 런타임을 분리하기 위해 별도 프로세스로 실행합니다."
    )
    STATUS_TEXT = "실행 가능"
    STATUS_TONE = "active"
    ACCENT_START = "#ffffff"
    ACCENT_END = "#f8fafc"
    META_LINE = "json/image bbox -> table review"
    TAGS = ["Table", "Review", "BBOX"]
    PRIMARY_ACTION = "뷰어 실행"
    SECONDARY_ACTION = "상세 보기"
    OWNER = "검수 운영"
    ENTRY_KIND = "external"
    MODULE_PATH = "app/tabs/misc_tools/apps/table_viewer/code/viewer.py"
    DISPLAY_ORDER = 20

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None

    def run_tool(self, repo_root: Path) -> str:
        del repo_root

        if self._process is not None and self._process.poll() is None:
            QMessageBox.information(
                None,
                self.APP_NAME,
                "테이블 검수 뷰어가 이미 실행 중입니다.",
            )
            return "테이블 검수 뷰어가 이미 실행 중입니다."

        viewer_root = self._viewer_root()
        viewer_py = viewer_root / "viewer.py"
        if not viewer_py.exists():
            QMessageBox.critical(
                None,
                self.APP_NAME,
                f"viewer.py를 찾을 수 없습니다.\n\n{viewer_py}",
            )
            return "테이블 검수 뷰어 실행 파일을 찾을 수 없습니다."

        python_path, install_reason = self._suitable_python_path(viewer_root)
        if python_path is None:
            python_path = self._install_venv_if_confirmed(viewer_root, install_reason)
            if python_path is None:
                return "테이블 검수 뷰어 실행 준비가 취소되었습니다."

        try:
            self._process = subprocess.Popen(
                [str(python_path), str(viewer_py)],
                cwd=str(viewer_root),
                close_fds=True,
                creationflags=self._creation_flags(),
                env=self._process_env(),
            )
        except OSError as exc:
            QMessageBox.critical(
                None,
                self.APP_NAME,
                f"테이블 검수 뷰어 실행에 실패했습니다.\n\n{exc}",
            )
            return "테이블 검수 뷰어 실행에 실패했습니다."

        return "테이블 검수 뷰어를 실행했습니다."

    def _viewer_root(self) -> Path:
        return Path(__file__).resolve().parent / "code"

    def _suitable_python_path(self, viewer_root: Path) -> tuple[Optional[Path], str]:
        errors: list[str] = []
        candidates = self._candidate_python_paths(viewer_root)
        if not candidates:
            return None, "전용 가상환경이 아직 없습니다."

        for candidate in candidates:
            missing = self._missing_requirements(candidate)
            if not missing:
                return candidate, ""
            errors.append(f"{candidate}: {missing}")

        detail = "\n\n".join(errors)
        return None, f"실행 가능한 Python을 찾았지만 필수 패키지 확인에 실패했습니다.\n\n{detail}"

    def _candidate_python_paths(self, viewer_root: Path) -> list[Path]:
        candidates: list[Path] = []
        env_python = os.environ.get("TABLE_VIEWER_PYTHON", "").strip()
        if env_python:
            env_path = Path(env_python)
            if env_path.exists():
                candidates.append(env_path)

        for candidate in [
            viewer_root / ".venv" / "Scripts" / "pythonw.exe",
            viewer_root / ".venv" / "Scripts" / "python.exe",
            viewer_root / ".venv-1" / "Scripts" / "pythonw.exe",
            viewer_root / ".venv-1" / "Scripts" / "python.exe",
        ]:
            if candidate.exists():
                candidates.append(candidate)
        return candidates

    def _install_venv_if_confirmed(self, viewer_root: Path, reason: str) -> Optional[Path]:
        requirements_path = viewer_root / "requirements.txt"
        if not requirements_path.exists():
            QMessageBox.critical(
                None,
                self.APP_NAME,
                f"설치 기준 파일을 찾을 수 없습니다.\n\n{requirements_path}",
            )
            return None

        answer = QMessageBox.question(
            None,
            self.APP_NAME,
            (
                "테이블 검수 뷰어를 실행할 수 있는 전용 가상환경이 없습니다.\n\n"
                f"{reason}\n\n"
                f"아래 경로에 가상환경을 만들고 필요한 패키지를 설치할까요?\n\n"
                f"{viewer_root / '.venv'}"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return None

        return self._install_venv(viewer_root)

    def _install_venv(self, viewer_root: Path) -> Optional[Path]:
        venv_dir = viewer_root / ".venv"
        requirements_path = viewer_root / "requirements.txt"
        progress = QProgressDialog("테이블 검수 뷰어 가상환경을 준비하는 중입니다.", "취소", 0, 0)
        progress.setWindowTitle(self.APP_NAME)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        log_path = viewer_root / ".install.log"
        try:
            base_python = self._validation_python(Path(sys.executable))
            install_python = self._local_venv_python(viewer_root, windowed=False)
            if install_python is None:
                progress.setLabelText("가상환경을 생성하는 중입니다.")
                error = self._run_install_command(
                    [str(base_python), "-m", "venv", str(venv_dir)],
                    viewer_root,
                    progress,
                    log_path,
                )
                if error:
                    self._show_install_error("가상환경 생성에 실패했습니다.", error, log_path)
                    return None
                install_python = self._local_venv_python(viewer_root, windowed=False)

            if install_python is None:
                self._show_install_error(
                    "가상환경 Python을 찾을 수 없습니다.",
                    str(venv_dir / "Scripts" / "python.exe"),
                    log_path,
                )
                return None

            progress.setLabelText("필요 패키지를 설치하는 중입니다.")
            error = self._run_install_command(
                [str(install_python), "-m", "pip", "install", "-r", str(requirements_path)],
                viewer_root,
                progress,
                log_path,
                timeout_seconds=1800,
            )
            if error:
                self._show_install_error("필요 패키지 설치에 실패했습니다.", error, log_path)
                return None

            launch_python = self._local_venv_python(viewer_root, windowed=True)
            if launch_python is None:
                self._show_install_error(
                    "실행용 Python을 찾을 수 없습니다.",
                    str(venv_dir / "Scripts" / "pythonw.exe"),
                    log_path,
                )
                return None

            missing = self._missing_requirements(launch_python)
            if missing:
                self._show_install_error("설치 후에도 필수 패키지를 불러올 수 없습니다.", missing, log_path)
                return None

            QMessageBox.information(
                None,
                self.APP_NAME,
                "테이블 검수 뷰어 실행 준비가 완료되었습니다.",
            )
            return launch_python
        finally:
            progress.close()

    def _local_venv_python(self, viewer_root: Path, *, windowed: bool) -> Optional[Path]:
        scripts_dir = viewer_root / ".venv" / "Scripts"
        candidates = (
            [scripts_dir / "pythonw.exe", scripts_dir / "python.exe"]
            if windowed
            else [scripts_dir / "python.exe", scripts_dir / "pythonw.exe"]
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _run_install_command(
        self,
        args: list[str],
        cwd: Path,
        progress: QProgressDialog,
        log_path: Path,
        *,
        timeout_seconds: int = 600,
    ) -> str:
        start = time.monotonic()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            log_file.write("\n$ " + subprocess.list2cmdline(args) + "\n")
            log_file.flush()
            try:
                process = subprocess.Popen(
                    args,
                    cwd=str(cwd),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=self._process_env(),
                )
            except OSError as exc:
                return str(exc)

            while process.poll() is None:
                QApplication.processEvents()
                if progress.wasCanceled():
                    process.terminate()
                    return "사용자가 설치를 취소했습니다."
                if time.monotonic() - start > timeout_seconds:
                    process.terminate()
                    return f"명령 실행 시간이 {timeout_seconds}초를 초과했습니다."
                time.sleep(0.1)

            if process.returncode != 0:
                return self._log_tail(log_path) or f"명령이 종료 코드 {process.returncode}로 실패했습니다."
        return ""

    def _show_install_error(self, title: str, detail: str, log_path: Path) -> None:
        QMessageBox.critical(
            None,
            self.APP_NAME,
            f"{title}\n\n{detail}\n\n설치 로그: {log_path}",
        )

    def _log_tail(self, log_path: Path, max_chars: int = 4000) -> str:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text[-max_chars:].strip()

    def _missing_requirements(self, python_path: Path) -> str:
        validation_python = self._validation_python(python_path)
        script = "import PyQt6.QtWebEngineWidgets; import boto3; import paramiko"
        try:
            result = subprocess.run(
                [str(validation_python), "-c", script],
                cwd=str(self._viewer_root()),
                capture_output=True,
                text=True,
                timeout=20,
                env=self._process_env(),
            )
        except OSError as exc:
            return str(exc)
        except subprocess.TimeoutExpired:
            return "dependency check timed out"

        if result.returncode == 0:
            return ""
        return (result.stderr or result.stdout or "unknown import error").strip()

    def _validation_python(self, python_path: Path) -> Path:
        if python_path.name.lower() == "pythonw.exe":
            python_exe = python_path.with_name("python.exe")
            if python_exe.exists():
                return python_exe
        return python_path

    def _creation_flags(self) -> int:
        flags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        return flags

    def _process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        for key in (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_QPA_PLATFORMTHEME",
        ):
            env.pop(key, None)
        return env
