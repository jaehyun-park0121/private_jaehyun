from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .base import normalize_match_values, render_match_summary


def compile_pattern(source_text: str, *, use_regex: bool, case_sensitive: bool) -> Optional[re.Pattern]:
    if not use_regex:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(source_text, flags)


def replace_text(
    text: str,
    source_text: str,
    replacement: str,
    *,
    use_regex: bool,
    case_sensitive: bool,
    regex: Optional[re.Pattern],
    replacement_uses_groups: bool = False,
) -> tuple[str, List[str], List[Dict[str, Any]]]:
    if use_regex:
        if regex is None:
            return text, [], []
        match_objects = [match for match in regex.finditer(text) if match.group(0)]
        if not match_objects:
            return text, [], []

        parts: List[str] = []
        segments: List[Dict[str, Any]] = []
        cursor = 0
        for match in match_objects:
            start, end = match.span()
            parts.append(text[cursor:start])
            replaced = match.expand(replacement) if replacement_uses_groups else replacement
            parts.append(replaced)
            segments.append({"start": start, "end": end, "replacement": replaced})
            cursor = end
        parts.append(text[cursor:])
        return "".join(parts), [match.group(0) for match in match_objects], segments

    if not source_text:
        return text, [], []
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(source_text), flags)
    match_objects = [match for match in pattern.finditer(text) if match.group(0)]
    if not match_objects:
        return text, [], []

    parts: List[str] = []
    segments: List[Dict[str, Any]] = []
    cursor = 0
    for match in match_objects:
        start, end = match.span()
        parts.append(text[cursor:start])
        parts.append(replacement)
        segments.append({"start": start, "end": end, "replacement": replacement})
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), [match.group(0) for match in match_objects], segments


def build_replace_detail(*, pattern: str, replacement: str, matches: List[str], use_regex: bool) -> str:
    normalized_matches = normalize_match_values(matches)
    total = len(normalized_matches)
    if use_regex:
        rendered = render_match_summary(normalized_matches)
        return f"치환 완료: {rendered} -> {replacement} | 총 {total}건 | 패턴: {pattern}"
    return f"치환 완료: {pattern} -> {replacement} | 총 {total}건"


def normalize_compare_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: normalize_compare_payload(value)
            for key, value in payload.items()
            if key not in {"is_problem", "problem_reason"}
        }
    if isinstance(payload, list):
        return [normalize_compare_payload(value) for value in payload]
    return payload


def format_replace_row_label(row: Dict[str, Any]) -> str:
    book_id = str(row.get("book_id", "")).strip()
    page_name = str(row.get("page_name", "")).strip()
    label_id = str(row.get("label_id", "")).strip()
    label = str(row.get("label", "")).strip()
    parts = [part for part in [book_id, page_name, f"#{label_id}" if label_id else "", label] if part]
    return " / ".join(parts) or str(row.get("row_key", "")).strip() or "(unknown)"
