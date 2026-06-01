from __future__ import annotations

import concurrent.futures
import copy
import os
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt5.QtCore import QThread, pyqtSignal

from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.loader import PluginLoader
from app.tabs.pre_parse.plugin_system.registry import CheckRegistry
from app.tabs.pre_parse.plugin_system.runner import CheckRunner

_PROCESS_RUNNER: CheckRunner | None = None
_PROCESS_PROJECT_ID = "demo"
_PROCESS_SELECTED_PLUGIN_IDS: List[str] = []
_PROCESS_SELECTED_OPTIONS: Dict[str, Any] = {}


def _init_check_process(
    plugin_dir: str,
    project_id: str,
    selected_plugin_ids: List[str],
    selected_options: Dict[str, Any],
) -> None:
    global _PROCESS_RUNNER, _PROCESS_PROJECT_ID, _PROCESS_SELECTED_PLUGIN_IDS, _PROCESS_SELECTED_OPTIONS

    registry = CheckRegistry()
    loader = PluginLoader(Path(plugin_dir))
    loader.load_into_registry(registry)
    _PROCESS_RUNNER = CheckRunner(registry)
    _PROCESS_PROJECT_ID = str(project_id or "demo")
    _PROCESS_SELECTED_PLUGIN_IDS = [str(plugin_id) for plugin_id in selected_plugin_ids]
    _PROCESS_SELECTED_OPTIONS = copy.deepcopy(selected_options or {})


def _run_page_check_task(task: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if _PROCESS_RUNNER is None:
        return {}, "process runner not initialized"

    page_key = str(task.get("page_key", "")).strip()
    book_id = str(task.get("book_id", "")).strip()
    page_token = str(task.get("page_token", "")).strip()
    page_no = int(task.get("page_no", 0) or 0)
    file_name = str(task.get("file_name", "")).strip()
    order_index = int(task.get("order_index", 0) or 0)
    payload = task.get("payload", {})
    if not isinstance(payload, dict):
        return {}, f"{book_id}:{page_token} (invalid snapshot payload)"

    try:
        page_context = PageContext(
            project_id=_PROCESS_PROJECT_ID,
            book_id=book_id,
            page_no=page_no,
            ocr_text="",
            json_data=payload,
            config=copy.deepcopy(_PROCESS_SELECTED_OPTIONS),
        )
        checks = _PROCESS_RUNNER.run_for_page(page_context, _PROCESS_SELECTED_PLUGIN_IDS)
        return (
            {
                "order_index": order_index,
                "page_key": page_key,
                "book_id": book_id,
                "page_token": page_token,
                "file_name": file_name,
                "payload": payload,
                "checks": checks,
            },
            "",
        )
    except Exception as exc:
        return {}, f"{book_id}:{page_token} ({exc})"


class PreParseCheckRunWorker(QThread):
    finished_ok = pyqtSignal(object, object)
    cancelled = pyqtSignal(object, object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)
    bundle_ready = pyqtSignal(object)

    def __init__(
        self,
        *,
        plugin_dir: str,
        project_id: str,
        selected_plugin_ids: List[str],
        selected_options: Dict[str, Any],
        page_tasks: List[Dict[str, Any]],
        max_workers: int | None = None,
    ) -> None:
        super().__init__()
        self.plugin_dir = str(plugin_dir)
        self.project_id = str(project_id or "demo")
        self.selected_plugin_ids = [str(plugin_id) for plugin_id in selected_plugin_ids]
        self.selected_options = copy.deepcopy(selected_options or {})
        self.page_tasks = [copy.deepcopy(task) for task in page_tasks]
        cpu_count = os.cpu_count() or 2
        self.max_workers = max(1, int(max_workers or max(1, cpu_count - 1)))
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
            results: List[Dict[str, Any]] = []
            failures: List[str] = []
            total = len(self.page_tasks)
            if total == 0:
                self.finished_ok.emit(results, failures)
                return

            worker_count = min(self.max_workers, total)
            completed = 0
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=worker_count,
                initializer=_init_check_process,
                initargs=(
                    self.plugin_dir,
                    self.project_id,
                    self.selected_plugin_ids,
                    self.selected_options,
                ),
            ) as executor:
                future_map = {
                    executor.submit(_run_page_check_task, dict(task)): dict(task)
                    for task in self.page_tasks
                }
                try:
                    for future in concurrent.futures.as_completed(future_map):
                        if self._is_stop_requested():
                            for pending in future_map:
                                if not pending.done():
                                    pending.cancel()
                            break

                        completed += 1
                        self.progress.emit("페이지별 플러그인 검사 실행", completed, total)
                        try:
                            bundle, failure = future.result()
                        except Exception as exc:
                            failures.append(str(exc))
                            continue

                        if failure:
                            failures.append(failure)
                            continue
                        if isinstance(bundle, dict):
                            results.append(bundle)
                            self.bundle_ready.emit(bundle)
                finally:
                    if self._is_stop_requested():
                        for pending in future_map:
                            if not pending.done():
                                pending.cancel()

            if self._is_stop_requested():
                self.cancelled.emit(results, failures)
                return
            self.finished_ok.emit(results, failures)
        except Exception as exc:
            self.failed.emit("".join(traceback.format_exception(exc)))
