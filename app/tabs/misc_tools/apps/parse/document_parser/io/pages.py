from __future__ import annotations

import shutil
from pathlib import Path

from ..config import AppConfig


def export_page_image(
    image_path: Path,
    output_document_dir: Path,
    config: AppConfig,
) -> None:
    if not config.parser.export_pages:
        return
    if not image_path.exists():
        return

    pages_dir = output_document_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image_path, pages_dir / image_path.name)