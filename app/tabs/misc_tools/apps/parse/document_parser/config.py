from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError


@dataclass(frozen=True)
class LabelRule:
    label: str
    type: str
    use_in_contents: str
    marker: str
    crop: bool
    description_mode: str
    chapter_source: bool


@dataclass(frozen=True)
class ExcelConfig:
    workbook_path: Path | None
    sheet_name: str
    header_row: int
    columns: dict[str, str]


@dataclass(frozen=True)
class PathConfig:
    input_root: Path
    output_root: Path


@dataclass(frozen=True)
class SchemaConfig:
    top_level_shapes_key: str
    required_shape_fields: tuple[str, ...]
    strict_required_fields: bool
    stop_on_validation_error: bool


@dataclass(frozen=True)
class ParserSettings:
    page_number_pattern: str
    crop_dir_template: str
    output_indent: int
    export_pages: bool


@dataclass(frozen=True)
class ExecutionConfig:
    parallel_enabled: bool
    max_workers: int

@dataclass(frozen=True)
class AppConfig:
    paths: PathConfig
    excel: ExcelConfig
    schema: SchemaConfig
    parser: ParserSettings
    execution: ExecutionConfig
    labels: dict[str, LabelRule]

    def label_rule(self, label: str) -> LabelRule:
        try:
            return self.labels[label.upper()]
        except KeyError as exc:
            raise ConfigError(f"설정에 없는 라벨 '{label}'입니다. config.labels에 먼저 추가해 주세요.") from exc


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    base_dir = path.parent

    try:
        labels = {
            label.upper(): LabelRule(label=label.upper(), **payload)
            for label, payload in raw["labels"].items()
        }
        execution = raw.get("execution", {})
        parser = raw["parser"]
        return AppConfig(
            paths=PathConfig(
                input_root=_resolve_path(base_dir, raw["paths"]["input_root"]),
                output_root=_resolve_path(base_dir, raw["paths"]["output_root"]),
            ),
            excel=ExcelConfig(
                workbook_path=_resolve_optional_path(base_dir, raw["excel"]["workbook_path"]),
                sheet_name=raw["excel"]["sheet_name"],
                header_row=int(raw["excel"]["header_row"]),
                columns=dict(raw["excel"]["columns"]),
            ),
            schema=SchemaConfig(
                top_level_shapes_key=raw["schema"]["top_level_shapes_key"],
                required_shape_fields=tuple(raw["schema"]["required_shape_fields"]),
                strict_required_fields=bool(raw["schema"]["strict_required_fields"]),
                stop_on_validation_error=bool(raw["schema"]["stop_on_validation_error"]),
            ),
            parser=ParserSettings(
                page_number_pattern=parser["page_number_pattern"],
                crop_dir_template=parser["crop_dir_template"],
                output_indent=int(parser["output_indent"]),
                export_pages=bool(parser.get("export_pages", False)),
            ),
            execution=ExecutionConfig(
                parallel_enabled=bool(execution.get("parallel_enabled", False)),
                max_workers=max(1, int(execution.get("max_workers", 1))),
            ),
            labels=labels,
        )
    except KeyError as exc:
        raise ConfigError(f"필수 설정 키가 없습니다: {exc}") from exc


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _resolve_optional_path(base_dir: Path, value: str) -> Path | None:
    if not value:
        return None
    return _resolve_path(base_dir, value)
