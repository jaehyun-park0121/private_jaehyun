from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NormalizedShape:
    index: int
    label: str
    shape_type: str
    flags_text: str
    bbox: tuple[float, float, float, float]
    points: tuple[tuple[float, float], tuple[float, float]]
    parent_index: int | None = None
    ancestor_indices: tuple[int, ...] = ()
    children: list[int] = field(default_factory=list)
    tag: str = ""


@dataclass
class PageParseResult:
    page: str
    chapter: str
    page_contents: str
    add_info: list[dict]