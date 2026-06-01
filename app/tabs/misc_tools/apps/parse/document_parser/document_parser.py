from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .config import AppConfig, load_config
from .errors import ParserError
from .io.crops import export_crops
from .io.pages import export_page_image
from .metadata.excel_loader import MetadataLoader
from .parsing.relations import build_shapes
from .parsing.renderer import first_title_on_page, render_page
from .parsing.schema import validate_page_schema


LOGGER = logging.getLogger(__name__)


class DocumentParser:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.metadata_loader = MetadataLoader(config)
        self.page_pattern = re.compile(config.parser.page_number_pattern)

    @classmethod
    def from_config_path(cls, config_path: str | Path) -> "DocumentParser":
        return cls(load_config(config_path))

    def parse_all_documents(self) -> None:
        # Keep sequential/parallel orchestration outside the core document parser.
        from .execution.runner import run_all_documents

        run_all_documents(self)

    def list_document_directories(self) -> list[Path]:
        self.config.paths.output_root.mkdir(parents=True, exist_ok=True)
        return sorted(path for path in self.config.paths.input_root.iterdir() if path.is_dir())

    def prepare_for_parallel(self) -> None:
        self.config.paths.output_root.mkdir(parents=True, exist_ok=True)
        # Preload shared metadata before worker threads start.
        self.metadata_loader.ensure_loaded()

    def parse_document(self, document_dir: Path) -> Path:
        work_id = document_dir.name
        LOGGER.info("[DOC] 문서 처리 시작: %s", work_id)
        metadata = self.metadata_loader.get_document_metadata(work_id)
        page_paths = self._collect_page_paths(document_dir)
        output_document_dir = self.config.paths.output_root / work_id
        output_document_dir.mkdir(parents=True, exist_ok=True)

        contents = []
        previous_title = ""
        for page_path in page_paths:
            LOGGER.info("[PAGE] [%s] 페이지 처리 시작: %s", work_id, page_path.name)
            try:
                raw_page = json.loads(page_path.read_text(encoding="utf-8"))
                validate_page_schema(raw_page, page_path, self.config)

                page_number = self._extract_page_number(page_path)
                shapes = build_shapes(raw_page[self.config.schema.top_level_shapes_key], self.config, work_id, page_number)
                if not shapes:
                    LOGGER.info("[PAGE] [%s] 페이지 스킵(유효 shape 없음): %s", work_id, page_path.name)
                    continue
                page_title = first_title_on_page(shapes, self.config)
                chapter = page_title or previous_title

                page_result = render_page(
                    shapes=shapes,
                    config=self.config,
                    page_number=page_number,
                    chapter=chapter,
                )
                contents.append(
                    {
                        "page": page_result.page,
                        "chapter": page_result.chapter,
                        "page_contents": page_result.page_contents,
                        "add_info": page_result.add_info,
                    }
                )

                # Only pages that are included in contents are copied into pages/.
                export_page_image(
                    image_path=page_path.with_suffix(".png"),
                    output_document_dir=output_document_dir,
                    config=self.config,
                )
                export_crops(
                    image_path=page_path.with_suffix(".png"),
                    output_document_dir=output_document_dir,
                    shapes=shapes,
                    config=self.config,
                )
                if page_title:
                    previous_title = page_title
                LOGGER.info("[PAGE] [%s] 페이지 처리 완료: %s", work_id, page_path.name)
            except (ParserError, json.JSONDecodeError, OSError) as exc:
                LOGGER.warning("[PAGE] [%s] 페이지 '%s' 파싱 중 경고가 발생하여 건너뜁니다: %s", work_id, page_path.name, exc)
                continue

        payload = {
            **metadata,
            "contents": contents,
        }

        output_path = output_document_dir / f"{work_id}.json"
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=self.config.parser.output_indent),
            encoding="utf-8",
        )
        LOGGER.info("[DOC] 문서 저장 완료: %s (pages=%s)", work_id, len(contents))
        return output_path

    def _extract_page_number(self, page_path: Path) -> str:
        match = self.page_pattern.search(page_path.stem)
        if not match:
            raise ParserError(f"파일명 '{page_path.name}'에서 페이지 번호를 찾을 수 없습니다.")
        return match.group(1)

    def _collect_page_paths(self, document_dir: Path) -> list[Path]:
        sortable_paths: list[tuple[int, str, Path]] = []
        for page_path in document_dir.glob("*.json"):
            try:
                page_number = self._extract_page_number(page_path)
            except ParserError as exc:
                LOGGER.warning("[PAGE] 페이지 파일 스킵: %s", exc)
                continue
            sortable_paths.append((int(page_number), page_path.name, page_path))
        sortable_paths.sort()
        return [page_path for _, _, page_path in sortable_paths]
