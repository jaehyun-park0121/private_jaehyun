from __future__ import annotations

from typing import Any, Dict, List


def normalize_match_values(matches: Any) -> List[str]:
    if matches is None:
        return []
    if isinstance(matches, str):
        value = matches.strip()
        return [value] if value else []
    if isinstance(matches, (list, tuple, set)):
        normalized: List[str] = []
        for value in matches:
            text = str(value).strip()
            if text:
                normalized.append(text)
        return normalized
    text = str(matches).strip()
    return [text] if text else []


def render_disallowed_char(char: str) -> str:
    if char == "\n":
        return r"\n"
    if char == "\r":
        return r"\r"
    if char == "\t":
        return r"\t"
    if char == " ":
        return "<space>"
    return char


def render_match_summary(matches: Any) -> str:
    normalized_matches = normalize_match_values(matches)
    if not normalized_matches:
        return "-"

    counts: Dict[str, int] = {}
    for value in normalized_matches:
        counts[value] = counts.get(value, 0) + 1

    return ", ".join(
        f"{render_disallowed_char(value)}({count})"
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def empty_scan_result_patch() -> Dict[str, Any]:
    return {
        "tool_id": "",
        "tool_error_type": "",
        "tool_error_detail": "",
        "tool_error_matches": [],
        "match_spans": [],
        "highlight_text": "",
        "highlight_matches": [],
        "detail_filter_tool_id": "",
        "detail_filter_values": [],
    }
