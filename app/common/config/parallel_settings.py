from __future__ import annotations

import os
from typing import Any, Dict


def cpu_core_count() -> int:
    return max(1, int(os.cpu_count() or 1))


def default_parallel_workers() -> int:
    return max(1, cpu_core_count() - 1)


def get_parallel_config(config: Dict[str, Any] | None) -> Dict[str, int]:
    parallel_config: Dict[str, Any] = {}
    if isinstance(config, dict):
        candidate = config.get("parallel", {})
        if isinstance(candidate, dict):
            parallel_config = candidate

    legacy_values = [
        parallel_config.get("max_workers"),
        parallel_config.get("bbox_snapshot_workers"),
        parallel_config.get("bbox_check_workers"),
    ]
    resolved = default_parallel_workers()
    for value in legacy_values:
        if value is None:
            continue
        resolved = _to_positive_int(value, default_parallel_workers())
        break

    return {"max_workers": resolved}


def resolve_parallel_workers(
    config: Dict[str, Any] | None,
    *,
    total_tasks: int | None = None,
) -> int:
    configured = get_parallel_config(config).get("max_workers", default_parallel_workers())
    worker_count = max(1, int(configured))
    if total_tasks is not None and total_tasks > 0:
        worker_count = min(worker_count, int(total_tasks))
    return max(1, worker_count)


def build_parallel_config(*, max_workers: int) -> Dict[str, Dict[str, int]]:
    return {
        "parallel": {
            "max_workers": _to_positive_int(max_workers, default_parallel_workers()),
        }
    }


def _to_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(1, parsed)
