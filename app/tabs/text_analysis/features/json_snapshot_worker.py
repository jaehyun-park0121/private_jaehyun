from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyQt5.QtCore import QThread, pyqtSignal

from app.common.io.encoding import decode_text, dump_json_file

from .s3_loader import S3Loader

_PROCESS_S3_LOADER: S3Loader | None = None


def _json_cache_key(json_row: Dict[str, Any]) -> str:
    s3_key = str(json_row.get("s3_key", "")).strip()
    etag = str(json_row.get("etag", "")).strip()
    if not s3_key:
        return ""
    return f"{s3_key}|{etag}" if etag else s3_key


def _local_json_cache_path(cache_dir: str, json_row: Dict[str, Any]) -> Path:
    s3_key = str(json_row.get("s3_key", "")).strip()
    etag = str(json_row.get("etag", "")).strip()
    hash_seed = f"{s3_key}|{etag}" if etag else s3_key
    safe_name = hashlib.md5(hash_seed.encode("utf-8")).hexdigest() + ".json"
    return Path(cache_dir) / safe_name


def _init_snapshot_process(aws_config: Dict[str, Any]) -> None:
    global _PROCESS_S3_LOADER
    _PROCESS_S3_LOADER = S3Loader(dict(aws_config or {}))


def _get_process_s3_loader(aws_config: Dict[str, Any]) -> S3Loader:
    global _PROCESS_S3_LOADER
    if _PROCESS_S3_LOADER is None:
        _PROCESS_S3_LOADER = S3Loader(dict(aws_config or {}))
    return _PROCESS_S3_LOADER


def _load_snapshot_task(
    aws_config: Dict[str, Any],
    cache_dir: str,
    json_row: Dict[str, Any],
) -> Tuple[str, str, str]:
    bucket = str(json_row.get("bucket", "")).strip()
    s3_key = str(json_row.get("s3_key", "")).strip()
    page_name = str(json_row.get("page_no", "")).strip()
    book_id = str(json_row.get("book_id", "")).strip()
    cache_key = _json_cache_key(json_row)
    if not bucket or not s3_key or not cache_key:
        return "", "", f"{book_id}:{page_name} (S3 path missing)"

    try:
        local_path = _local_json_cache_path(cache_dir, json_row)
        if local_path.exists():
            return cache_key, str(local_path), ""

        loader = _get_process_s3_loader(aws_config)
        response = loader.client.get_object(Bucket=bucket, Key=s3_key)
        body = response.get("Body")
        if body is None:
            return "", "", f"{book_id}:{page_name} (body missing)"

        payload = json.loads(decode_text(body.read()))
        if not isinstance(payload, dict):
            return "", "", f"{book_id}:{page_name} (invalid JSON payload)"

        local_path.parent.mkdir(parents=True, exist_ok=True)
        dump_json_file(local_path, payload, ensure_ascii=False, indent=2)
        return cache_key, str(local_path), ""
    except Exception as exc:
        return "", "", f"{book_id}:{page_name} ({exc})"


class TextAnalysisJsonSnapshotWorker(QThread):
    finished_ok = pyqtSignal(object, object)
    cancelled = pyqtSignal(object, object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)

    def __init__(
        self,
        *,
        aws_config: Dict[str, Any],
        json_rows: List[Dict[str, Any]],
        cache_dir: str,
        max_workers: int | None = None,
    ) -> None:
        super().__init__()
        self.aws_config = dict(aws_config or {})
        self.json_rows = [dict(row) for row in json_rows]
        self.cache_dir = str(cache_dir)
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
            cache_paths: Dict[str, str] = {}
            failures: List[str] = []
            total = len(self.json_rows)
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

            if total == 0:
                self.finished_ok.emit(cache_paths, failures)
                return

            worker_count = min(self.max_workers, total)
            completed = 0
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=worker_count,
                initializer=_init_snapshot_process,
                initargs=(self.aws_config,),
            ) as executor:
                future_map = {
                    executor.submit(
                        _load_snapshot_task,
                        self.aws_config,
                        self.cache_dir,
                        dict(json_row),
                    ): dict(json_row)
                    for json_row in self.json_rows
                }
                try:
                    for future in concurrent.futures.as_completed(future_map):
                        if self._is_stop_requested():
                            for pending in future_map:
                                if not pending.done():
                                    pending.cancel()
                            break

                        completed += 1
                        self.progress.emit("JSON 스냅샷 로딩", completed, total)
                        try:
                            cache_key, cache_path, failure = future.result()
                        except Exception as exc:
                            failures.append(str(exc))
                            continue

                        if failure:
                            failures.append(failure)
                            continue
                        if cache_key and cache_path:
                            cache_paths[cache_key] = cache_path
                finally:
                    if self._is_stop_requested():
                        for pending in future_map:
                            if not pending.done():
                                pending.cancel()

            if self._is_stop_requested():
                self.cancelled.emit(cache_paths, failures)
                return
            self.finished_ok.emit(cache_paths, failures)
        except Exception as exc:
            self.failed.emit("".join(traceback.format_exception(exc)))
