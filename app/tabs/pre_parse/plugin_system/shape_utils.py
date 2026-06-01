from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple


ShapeDict = Dict[str, Any]
Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]


def get_shape_list(json_data: Any) -> List[Any]:
    if not isinstance(json_data, dict):
        return []

    shapes = json_data.get("shapes", [])
    if not isinstance(shapes, list):
        return []

    return shapes


def iter_shape_dicts(json_data: Any) -> Iterator[Tuple[int, ShapeDict]]:
    for idx, shape in enumerate(get_shape_list(json_data)):
        if isinstance(shape, dict):
            yield idx, shape


def get_shape_label(shape: ShapeDict) -> str:
    return str(shape.get("label", "") or "").strip().upper()


def get_shape_flags(shape: ShapeDict) -> Dict[str, Any]:
    flags = shape.get("flags", {})
    if isinstance(flags, dict):
        return flags
    return {}


def get_shape_flags_text(shape: ShapeDict) -> str:
    value = get_shape_flags(shape).get("text", "")
    if value is None:
        return ""
    return str(value)


def normalize_points(points: Any) -> List[Point]:
    normalized_points: List[Point] = []

    if not isinstance(points, (list, tuple)):
        return normalized_points

    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue

        try:
            normalized_points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            continue

    return normalized_points


def get_bbox_from_points(points: Any) -> Optional[BBox]:
    normalized_points = normalize_points(points)
    if len(normalized_points) < 2:
        return None

    x_values = [point[0] for point in normalized_points]
    y_values = [point[1] for point in normalized_points]

    x1 = min(x_values)
    y1 = min(y_values)
    x2 = max(x_values)
    y2 = max(y_values)

    if x2 <= x1 or y2 <= y1:
        return None

    return (x1, y1, x2, y2)


def get_shape_bbox(shape: ShapeDict) -> Optional[BBox]:
    return get_bbox_from_points(shape.get("points", []))


def bbox_area(bbox: BBox) -> float:
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def bbox_intersection_area(bbox1: BBox, bbox2: BBox) -> float:
    ax1, ay1, ax2, ay2 = bbox1
    bx1, by1, bx2, by2 = bbox2

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


def is_bbox_inside(outer: BBox, inner: BBox, eps: float = 1e-6) -> bool:
    return (
        outer[0] <= inner[0] + eps
        and outer[1] <= inner[1] + eps
        and outer[2] >= inner[2] - eps
        and outer[3] >= inner[3] - eps
    )
