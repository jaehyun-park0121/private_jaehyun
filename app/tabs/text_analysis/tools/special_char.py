from __future__ import annotations

import re
from typing import Any, Dict

from .base import empty_scan_result_patch, render_disallowed_char


def validate_config(config: Dict[str, Any]) -> str:
    pattern_text = str(config.get("pattern_text", "") or "")
    try:
        re.compile(pattern_text)
    except re.error as exc:
        return str(exc)
    return ""


def prepare_runtime(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "regex": re.compile(str(config.get("pattern_text", "") or "")),
        "target_labels": {
            str(value).strip().upper()
            for value in (config.get("target_labels", []) or [])
            if str(value).strip()
        },
    }


def build_special_char_detail(matches: list[str]) -> str:
    counts: Dict[str, int] = {}
    for char in matches:
        counts[char] = counts.get(char, 0) + 1
    rendered = ", ".join(
        f"{render_disallowed_char(char)}({count})"
        for char, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )
    return f"허용 외 문자: {rendered}"


def analyze_row(row: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    patch = empty_scan_result_patch()

    target_labels = set(runtime.get("target_labels", set()) or set())
    label_name = str(row.get("label", "")).strip().upper()
    if target_labels and label_name not in target_labels:
        return patch

    text = str(row.get("flags_text", "") or "")
    regex = runtime.get("regex")
    if not regex:
        return patch
    raw_matches = [(m.start(), m.end(), m.group(0)) for m in regex.finditer(text) if m.group(0)]
    if not raw_matches:
        return patch

    matches = [group for _start, _end, group in raw_matches]
    match_spans = [[start, end, group] for start, end, group in raw_matches]
    patch.update(
        {
            "tool_id": "special_char_analysis",
            "tool_error_type": "특수문자 분석",
            "tool_error_detail": build_special_char_detail(matches),
            "tool_error_matches": matches,
            "match_spans": match_spans,
            "highlight_text": "",
            "highlight_matches": matches,
            "detail_filter_tool_id": "special_char_analysis",
            "detail_filter_values": matches,
        }
    )
    return patch
