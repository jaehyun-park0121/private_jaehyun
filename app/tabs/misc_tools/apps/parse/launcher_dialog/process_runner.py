from __future__ import annotations

import codecs
import locale
import sys
from pathlib import Path
from typing import Any, Optional

from PyQt5.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from .config_io import cleanup_runtime_config_file, write_runtime_config
from .log_handler import LogHandler


class ProcessRunner(QObject):
    started = pyqtSignal()
    finished = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    def __init__(
        self,
        parse_root: Path,
        log_handler: LogHandler,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._parse_root = parse_root
        self._log = log_handler
        self._process: Optional[QProcess] = None
        self._runtime_config_path: Optional[Path] = None
        self._post_parse_config_path: Optional[Path] = None
        self._post_parse_runtime_path: Optional[Path] = None
        self._post_parse_enabled = False
        self._output_root = ""
        self._decoder: Optional[Any] = None

    @property
    def is_running(self) -> bool:
        return (
            self._process is not None
            and self._process.state() != QProcess.NotRunning
        )

    def run(
        self,
        runtime_config: dict[str, Any],
        post_parse_config_path: Optional[Path] = None,
        post_parse_enabled: bool = False,
        output_root: str = "",
    ) -> bool:
        if self.is_running:
            return False

        self._cleanup_runtime_config()
        try:
            run_config_path = write_runtime_config(self._parse_root, runtime_config)
        except OSError:
            return False
        self._runtime_config_path = run_config_path
        self._post_parse_config_path = post_parse_config_path
        self._post_parse_enabled = post_parse_enabled
        self._output_root = output_root

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.setProgram(sys.executable)
        process.setArguments(
            ["-u", "-m", "document_parser.cli", "--config", str(run_config_path)]
        )
        process.setWorkingDirectory(str(self._parse_root))
        process.setProcessEnvironment(self._make_env())

        process.started.connect(self._on_parse_started)
        process.readyReadStandardOutput.connect(self._on_output)
        process.finished.connect(self._on_parse_finished)
        process.errorOccurred.connect(self._on_parse_error)

        self._process = process
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._log.reset_buffer()
        self._log.append_log("문서 파서 실행을 시작합니다.")
        self._log.append_log(f"실행 설정(임시): {run_config_path}")
        process.start()
        return True

    def stop(self) -> None:
        if not self.is_running:
            return
        self._log.append_log("실행 중지 요청을 보냈습니다.")
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()

    def cleanup(self) -> None:
        self._cleanup_runtime_config()
        self._cleanup_post_parse_runtime()

    # ── Parse phase ──────────────────────────────────────────────

    def _on_parse_started(self) -> None:
        self._log.append_log("프로세스 시작 완료")
        self.status_changed.emit("문서 파서 실행 중...")
        self.started.emit()

    def _on_parse_finished(
        self, exit_code: int, _exit_status: QProcess.ExitStatus
    ) -> None:
        self._flush_decoder()
        self._process = None

        if exit_code == 0:
            self._log.append_log("파싱 완료 (exit code=0)")
            self._cleanup_runtime_config()
            if self._post_parse_enabled and self._post_parse_config_path:
                self._run_post_parse()
                return
            self.status_changed.emit("실행 완료")
        else:
            self._log.append_log(f"파싱 실패 (exit code={exit_code})")
            self._cleanup_runtime_config()
            self.status_changed.emit("파싱 실패")

        self.finished.emit(exit_code)

    def _on_parse_error(self, error: QProcess.ProcessError) -> None:
        self._log.append_log(f"프로세스 오류: {error}")
        self._cleanup_runtime_config()
        self._process = None
        self._decoder = None
        self._log.flush_buffer()
        self.status_changed.emit("프로세스 실행 오류")
        self.error_occurred.emit(str(error))

    # ── Post-parse phase ─────────────────────────────────────────

    def _run_post_parse(self) -> None:
        self._log.append_log("─" * 48)
        self._log.append_log("Output 스키마 검증을 시작합니다.")
        self.status_changed.emit("Output 검증 실행 중...")

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.setProgram(sys.executable)
        process.setArguments(
            [
                "-u", "-m", "post_parse.cli",
                "--config", str(self._post_parse_config_path),
                "--output-root", self._output_root,
            ]
        )
        process.setWorkingDirectory(str(self._parse_root))
        process.setProcessEnvironment(self._make_env())

        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._log.reset_buffer()

        process.readyReadStandardOutput.connect(self._on_output)
        process.finished.connect(self._on_post_parse_finished)
        process.errorOccurred.connect(self._on_post_parse_error)

        self._process = process
        process.start()

    def _on_post_parse_finished(
        self, exit_code: int, _exit_status: QProcess.ExitStatus
    ) -> None:
        self._flush_decoder()
        self._cleanup_post_parse_runtime()
        self._process = None

        if exit_code == 0:
            self._log.append_log("Output 검증 완료 (오류 없음)")
            self.status_changed.emit("실행 완료")
        else:
            self._log.append_log("Output 검증 완료 (오류 있음 — 위 로그를 확인하세요)")
            self.status_changed.emit("실행 완료 (검증 오류)")

        self.finished.emit(exit_code)

    def _on_post_parse_error(self, error: QProcess.ProcessError) -> None:
        self._log.append_log(f"Output 검증 프로세스 오류: {error}")
        self._cleanup_post_parse_runtime()
        self._process = None
        self._decoder = None
        self._log.flush_buffer()
        self.status_changed.emit("Output 검증 실행 오류")
        self.error_occurred.emit(str(error))

    # ── Shared helpers ───────────────────────────────────────────

    def _on_output(self) -> None:
        if self._process is None:
            return
        payload = bytes(self._process.readAllStandardOutput())
        text = self._decode_chunk(payload)
        self._log.append_stream_text(text)

    def _decode_chunk(self, payload: bytes) -> str:
        if not payload:
            return ""
        if self._decoder is not None:
            return self._decoder.decode(payload, final=False)
        for encoding in ("utf-8", locale.getpreferredencoding(False), "cp949", "euc-kr"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="replace")

    def _flush_decoder(self) -> None:
        if self._decoder is not None:
            tail = self._decoder.decode(b"", final=True)
            self._log.append_stream_text(tail)
        self._decoder = None
        self._log.flush_buffer()

    def _cleanup_runtime_config(self) -> None:
        path = self._runtime_config_path
        self._runtime_config_path = None
        cleanup_runtime_config_file(path)

    def _cleanup_post_parse_runtime(self) -> None:
        path = self._post_parse_runtime_path
        self._post_parse_runtime_path = None
        cleanup_runtime_config_file(path)

    @staticmethod
    def _make_env() -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        return env
