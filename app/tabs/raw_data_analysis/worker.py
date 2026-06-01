from __future__ import annotations

import threading
import traceback

from PyQt5.QtCore import QThread, pyqtSignal

from .analysis_core import AnalysisConfig, S3Config, run_analysis


class AnalysisWorker(QThread):
    finished_ok = pyqtSignal(list, str, list, bool)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)

    def __init__(
        self,
        *,
        s3_uri: str,
        s3_config: S3Config,
        analysis_config: AnalysisConfig,
    ) -> None:
        super().__init__()
        self.s3_uri = s3_uri
        self.s3_config = s3_config
        self.analysis_config = analysis_config
        self._stop_requested = False
        self._stop_lock = threading.Lock()

    def request_stop(self) -> None:
        with self._stop_lock:
            self._stop_requested = True

    def _is_stop_requested(self) -> bool:
        with self._stop_lock:
            return self._stop_requested

    def run(self) -> None:
        try:
            def callback(desc: str, current: int, total: int) -> None:
                self.progress.emit(desc, current, total)

            rows, output_path, page_rows, cancelled = run_analysis(
                s3_uri=self.s3_uri,
                s3_config=self.s3_config,
                analysis_config=self.analysis_config,
                progress_callback=callback,
                stop_requested=self._is_stop_requested,
            )
            output_path_text = str(output_path) if output_path else ""
            self.finished_ok.emit(rows, output_path_text, page_rows, bool(cancelled))
        except Exception as exc:
            self.failed.emit("".join(traceback.format_exception(exc)))
