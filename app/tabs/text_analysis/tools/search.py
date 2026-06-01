from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .base import empty_scan_result_patch, normalize_match_values, render_match_summary


def validate_config(config: Dict[str, Any]) -> str:
    keyword = str(config.get("keyword", "") or "").strip()
    if not keyword:
        return "검색할 텍스트를 입력한 뒤 실행해 주세요."

    if bool(config.get("use_regex", False)):
        try:
            flags = 0 if bool(config.get("case_sensitive", False)) else re.IGNORECASE
            re.compile(keyword, flags)
        except re.error as exc:
            return str(exc)
    return ""


def prepare_runtime(config: Dict[str, Any]) -> Dict[str, Any]:
    keyword = str(config.get("keyword", "") or "").strip()
    use_regex = bool(config.get("use_regex", False))
    case_sensitive = bool(config.get("case_sensitive", False))
    regex = None
    if use_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(keyword, flags)
    return {
        "keyword": keyword,
        "use_regex": use_regex,
        "case_sensitive": case_sensitive,
        "regex": regex,
    }


def search_matches(
    text: str,
    keyword: str,
    *,
    use_regex: bool,
    case_sensitive: bool,
    regex: Optional[re.Pattern],
) -> List[str]:
    if use_regex:
        if regex is None:
            return []
        return [match.group(0) for match in regex.finditer(text) if match.group(0)]

    if not keyword:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    return [match.group(0) for match in re.finditer(re.escape(keyword), text, flags) if match.group(0)]


def search_match_spans(
    text: str,
    keyword: str,
    *,
    use_regex: bool,
    case_sensitive: bool,
    regex: Optional[re.Pattern],
) -> List[Tuple[int, int, str]]:
    if use_regex:
        if regex is None:
            return []
        return [(m.start(), m.end(), m.group(0)) for m in regex.finditer(text) if m.group(0)]

    if not keyword:
        return []
    flags = 0 if case_sensitive else re.IGNORECASE
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(re.escape(keyword), text, flags) if m.group(0)]


def build_match_detail(*, prefix: str, pattern: str, matches: List[str], use_regex: bool) -> str:
    normalized_matches = normalize_match_values(matches)
    rendered = render_match_summary(normalized_matches)
    total = len(normalized_matches)
    if use_regex:
        return f"{prefix}: {rendered} | 총 {total}건 | 패턴: {pattern}"
    return f"{prefix}: {rendered} | 총 {total}건"


def analyze_row(row: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    patch = empty_scan_result_patch()

    keyword = str(runtime.get("keyword", "") or "")
    use_regex = bool(runtime.get("use_regex", False))
    case_sensitive = bool(runtime.get("case_sensitive", False))
    regex = runtime.get("regex")
    text = str(row.get("flags_text", "") or "")
    spans = search_match_spans(
        text,
        keyword,
        use_regex=use_regex,
        case_sensitive=case_sensitive,
        regex=regex,
    )
    if not spans:
        return patch

    matches = [group for _start, _end, group in spans]
    match_spans = [[start, end, group] for start, end, group in spans]
    patch.update(
        {
            "tool_id": "search_tool",
            "tool_error_type": keyword,
            "tool_error_detail": build_match_detail(
                prefix="검색 결과",
                pattern=keyword,
                matches=matches,
                use_regex=use_regex,
            ),
            "tool_error_matches": matches,
            "match_spans": match_spans,
            "highlight_text": "",
            "highlight_matches": matches,
            "detail_filter_tool_id": "search_tool",
            "detail_filter_values": matches,
        }
    )
    return patch
