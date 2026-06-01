from __future__ import annotations

import logging
from pathlib import Path

from ..config import AppConfig
from ..errors import SchemaValidationError


LOGGER = logging.getLogger(__name__)


def validate_page_schema(raw_page: dict, page_path: Path, config: AppConfig) -> None:
    shapes_key = config.schema.top_level_shapes_key
    if not isinstance(raw_page, dict):
        raise SchemaValidationError(f"[{page_path.name}] JSON 최상위는 객체여야 합니다.")
    if shapes_key not in raw_page:
        raise SchemaValidationError(f"[{page_path.name}] '{shapes_key}'가 없습니다.")

    shapes = raw_page[shapes_key]
    if not isinstance(shapes, list):
        raise SchemaValidationError(f"[{page_path.name}] '{shapes_key}'는 list여야 합니다.")

    for index, shape in enumerate(shapes):
        _validate_shape(shape, page_path, index)


def _validate_shape(shape: object, page_path: Path, index: int) -> None:
    prefix = f"[{page_path.name}] shape[{index}]"
    if not isinstance(shape, dict):
        raise SchemaValidationError(f"{prefix}는 객체여야 합니다.")

    label = shape.get("label")
    if not isinstance(label, str):
        raise SchemaValidationError(f"{prefix}.label은 문자열이어야 합니다.")

    points = shape.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise SchemaValidationError(f"{prefix}.points는 길이 2의 list여야 합니다.")
    for point_index, point in enumerate(points):
        if not isinstance(point, list) or len(point) != 2:
            raise SchemaValidationError(f"{prefix}.points[{point_index}]는 길이 2의 list여야 합니다.")
        if not all(isinstance(value, (int, float)) for value in point):
            raise SchemaValidationError(f"{prefix}.points[{point_index}]는 숫자여야 합니다.")

    flags = shape.get("flags")
    if not isinstance(flags, dict):
        raise SchemaValidationError(f"{prefix}.flags는 객체여야 합니다.")

    if "text" not in flags:
        flags["text"] = ""
        LOGGER.warning("%s.flags.text가 없어 빈 문자열로 처리합니다.", prefix)
        return

    flags_text = flags["text"]
    if not isinstance(flags_text, str):
        raise SchemaValidationError(f"{prefix}.flags.text는 문자열이어야 합니다.")
    flags["text"] = flags_text.strip()
