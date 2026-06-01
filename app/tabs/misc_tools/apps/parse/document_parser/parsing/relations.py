from __future__ import annotations

from collections import defaultdict

from ..config import AppConfig
from ..models import NormalizedShape
from ..utils.boxes import area, contains, normalize_points, to_bbox


def build_shapes(raw_shapes: list[dict], config: AppConfig, work_id: str, page_number: str) -> list[NormalizedShape]:
    shapes: list[NormalizedShape] = []
    for index, raw_shape in enumerate(raw_shapes):
        rule = config.label_rule(raw_shape["label"])
        normalized_points = normalize_points(raw_shape["points"])
        shapes.append(
            NormalizedShape(
                index=index,
                label=rule.label,
                shape_type=rule.type,
                flags_text=raw_shape["flags"]["text"],
                points=normalized_points,
                bbox=to_bbox(normalized_points),
            )
        )

    _assign_direct_parents(shapes)
    _assign_ancestor_chains(shapes)
    _assign_tags(shapes, config, work_id, page_number)
    return shapes


def _assign_direct_parents(shapes: list[NormalizedShape]) -> None:
    for child in shapes:
        parent_candidates = [
            candidate
            for candidate in shapes
            if candidate.index != child.index
            and area(candidate.bbox) > area(child.bbox)
            and contains(candidate.bbox, child.bbox)
        ]
        if not parent_candidates:
            continue

        direct_parent = min(parent_candidates, key=lambda candidate: area(candidate.bbox))
        child.parent_index = direct_parent.index
        direct_parent.children.append(child.index)

    for shape in shapes:
        shape.children.sort()


def _assign_ancestor_chains(shapes: list[NormalizedShape]) -> None:
    for shape in shapes:
        ancestors: list[int] = []
        current_parent = shape.parent_index
        while current_parent is not None:
            ancestors.append(current_parent)
            current_parent = shapes[current_parent].parent_index
        shape.ancestor_indices = tuple(ancestors)


def _assign_tags(shapes: list[NormalizedShape], config: AppConfig, work_id: str, page_number: str) -> None:
    counters: defaultdict[str, int] = defaultdict(int)
    for shape in shapes:
        rule = config.label_rule(shape.label)
        if rule.use_in_contents != "tag":
            continue
        counters[rule.type] += 1
        shape.tag = f"{rule.type}_{work_id}_{page_number}_{counters[rule.type]:04d}"