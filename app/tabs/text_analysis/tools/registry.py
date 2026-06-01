from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from . import search, special_char


@dataclass(frozen=True)
class ScanToolSpec:
    tool_id: str
    display_name: str
    progress_desc: str
    completion_message: str


_SCAN_TOOL_SPECS = {
    "special_char_analysis": ScanToolSpec(
        tool_id="special_char_analysis",
        display_name="특수문자 분석",
        progress_desc="특수문자 분석",
        completion_message="실행 완료: 특수문자 분석 결과 {matched_count}건",
    ),
    "search_tool": ScanToolSpec(
        tool_id="search_tool",
        display_name="검색",
        progress_desc="검색 실행",
        completion_message="실행 완료: 검색 '{keyword}' 결과 {matched_count}건",
    ),
}

_SCAN_TOOL_MODULES = {
    "special_char_analysis": special_char,
    "search_tool": search,
}


def get_scan_tool_spec(tool_id: str) -> Optional[ScanToolSpec]:
    return _SCAN_TOOL_SPECS.get(str(tool_id or "").strip())


def validate_scan_tool_config(tool_id: str, config: Dict[str, Any]) -> str:
    module = _SCAN_TOOL_MODULES.get(str(tool_id or "").strip())
    if module is None:
        return "선택한 텍스트 분석 도구는 아직 개발 예정입니다."
    return str(module.validate_config(dict(config or {})) or "").strip()


def prepare_scan_runtime(tool_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    module = _SCAN_TOOL_MODULES[str(tool_id or "").strip()]
    return module.prepare_runtime(dict(config or {}))


def analyze_scan_row(tool_id: str, row: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    module = _SCAN_TOOL_MODULES[str(tool_id or "").strip()]
    return module.analyze_row(dict(row or {}), runtime)
