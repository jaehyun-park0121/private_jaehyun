from __future__ import annotations

import math


def normalize_points(points: list[list[float]] | tuple[tuple[float, float], tuple[float, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    (x1, y1), (x2, y2) = points
    left = float(min(x1, x2))
    top = float(min(y1, y2))
    right = float(max(x1, x2))
    bottom = float(max(y1, y2))
    return (left, top), (right, bottom)


def to_bbox(points: tuple[tuple[float, float], tuple[float, float]]) -> tuple[float, float, float, float]:
    (left, top), (right, bottom) = points
    return left, top, right, bottom


def area(bbox: tuple[float, float, float, float]) -> float:
    left, top, right, bottom = bbox
    return max(0.0, right - left) * max(0.0, bottom - top)


def contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float], epsilon: float = 0.0) -> bool:
    o_left, o_top, o_right, o_bottom = outer
    i_left, i_top, i_right, i_bottom = inner
    return (
        o_left - epsilon <= i_left
        and o_top - epsilon <= i_top
        and o_right + epsilon >= i_right
        and o_bottom + epsilon >= i_bottom
    )


def crop_box(bbox: tuple[float, float, float, float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    left, top, right, bottom = bbox
    return (
        max(0, min(width, math.floor(left))),
        max(0, min(height, math.floor(top))),
        max(0, min(width, math.ceil(right))),
        max(0, min(height, math.ceil(bottom))),
    )
