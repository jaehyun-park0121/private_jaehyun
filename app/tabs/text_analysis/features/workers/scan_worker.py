from __future__ import annotations

import concurrent.futures
import os
import threading
import traceback
from typing import Any, Dict, List

from PyQt5.QtCore import QThread, pyqtSignal

from ...tools.scan_executor import run_scan_chunk


class TextAnalysisScanWorker(QThread):
    finished_ok = pyqtSignal(object, object, int)
    cancelled = pyqtSignal(object, object, int)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)

    def __init__(
        self,
        *,
        tool_id: str,
        tool_config: Dict[str, Any],
        row_inputs: List[Dict[str, Any]],
        progress_desc: str,
        max_workers: int | None = None,
        chunk_size: int = 200,
    ) -> None:
        super().__init__()
        self.tool_id = str(tool_id or "").strip()
        self.tool_config = dict(tool_config or {})
        self.row_inputs = [dict(row) for row in row_inputs]
        self.progress_desc = str(progress_desc or "텍스트 분석 실행")
        cpu_count = os.cpu_count() or 2
        self.max_workers = max(1, int(max_workers or max(1, cpu_count - 1)))
        self.chunk_size = max(1, int(chunk_size or 200))
        self._stop_requested = False
        self._stop_lock = threading.Lock()

    def request_stop(self) -> None:
        with self._stop_lock:
            self._stop_requested = True

    def _is_stop_requested(self) -> bool:
        with self._stop_lock:
            return self._stop_requested

    def _build_tasks(self) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        for chunk_index, start in enumerate(range(0, len(self.row_inputs), self.chunk_size)):
            tasks.append(
                {
                    "chunk_index": chunk_index,
                    "tool_id": self.tool_id,
                    "tool_config": dict(self.tool_config),
                    "rows": [dict(row) for row in self.row_inputs[start : start + self.chunk_size]],
                }
            )
        return tasks

    def run(self) -> None:
        try:
            patches: List[Dict[str, Any]] = []
            failures: List[str] = []
            matched_count = 0
            tasks = self._build_tasks()
            total = len(tasks)
            if total == 0:
                self.finished_ok.emit(patches, failures, matched_count)
                return

            worker_count = min(self.max_workers, total)
            completed = 0
            with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_map = {executor.submit(run_scan_chunk, dict(task)): dict(task) for task in tasks}
                try:
                    for future in concurrent.futures.as_completed(future_map):
                        if self._is_stop_requested():
                            for pending in future_map:
                                if not pending.done():
                                    pending.cancel()
                            break

                        completed += 1
                        self.progress.emit(self.progress_desc, completed, total)
                        try:
                            _chunk_index, chunk_patches, chunk_matches, failure = future.result()
                        except Exception as exc:
                            failures.append(str(exc))
                            continue

                        if failure:
                            failures.append(failure)
                            continue

                        patches.extend(list(chunk_patches or []))
                        matched_count += int(chunk_matches or 0)
                finally:
                    if self._is_stop_requested():
                        for pending in future_map:
                            if not pending.done():
                                pending.cancel()

            if self._is_stop_requested():
                self.cancelled.emit(patches, failures, matched_count)
                return
            self.finished_ok.emit(patches, failures, matched_count)
        except Exception as exc:
            self.failed.emit("".join(traceback.format_exception(exc)))
