from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..config import AppConfig
from ..models import NormalizedShape
from ..utils.boxes import crop_box


def export_crops(
    image_path: Path,
    output_document_dir: Path,
    shapes: list[NormalizedShape],
    config: AppConfig,
) -> None:
    crop_shapes = [
        shape
        for shape in shapes
        if config.label_rule(shape.label).crop
    ]
    if not crop_shapes:
        return
    if not image_path.exists():
        return

    directories: dict[str, Path] = {}
    for shape in crop_shapes:
        if shape.label in directories:
            continue
        directory = output_document_dir / "crop" / shape.label
        directory.mkdir(parents=True, exist_ok=True)
        directories[shape.label] = directory

    with Image.open(image_path) as image:
        for shape in crop_shapes:
            box = crop_box(shape.bbox, image.size)
            if box[0] >= box[2] or box[1] >= box[3]:
                continue

            cropped = image.crop(box)
            cropped.save(directories[shape.label] / f"{shape.tag}.png")