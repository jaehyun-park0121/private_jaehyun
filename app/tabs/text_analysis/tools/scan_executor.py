from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .registry import analyze_scan_row, prepare_scan_runtime


def run_scan_chunk(task: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]], int, str]:
    chunk_index = int(task.get("chunk_index", 0) or 0)
    try:
        tool_id = str(task.get("tool_id", "")).strip()
        tool_config = dict(task.get("tool_config", {}) or {})
        rows = list(task.get("rows", []) or [])
        runtime = prepare_scan_runtime(tool_id, tool_config)

        patches: List[Dict[str, Any]] = []
        matched_count = 0
        for row in rows:
            row_data = dict(row or {})
            row_key = str(row_data.get("row_key", "")).strip()
            if not row_key:
                continue
            patch = analyze_scan_row(tool_id, row_data, runtime)
            if str(patch.get("tool_error_detail", "")).strip():
                matched_count += 1
            patches.append({"row_key": row_key, "patch": patch})

        return chunk_index, patches, matched_count, ""
    except Exception as exc:
        return chunk_index, [], 0, str(exc)
