from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from app.common.config.config_manager import ConfigManager


def resolve_path(base_dir: Path, value: str) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def absolute_text(config_dir: Path, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = config_dir / path
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def base_directory(configured_value: str, config_dir: Path, fallback: Path) -> str:
    resolved = resolve_path(config_dir, configured_value.strip())
    if resolved is not None and resolved.exists():
        return str(resolved)
    return str(fallback)


def load_config_file(config_path: Path) -> dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8-sig"))


def build_merged_config(
    raw_config: dict[str, Any], collected: dict[str, Any]
) -> dict[str, Any]:
    raw = copy.deepcopy(raw_config) if raw_config else {}
    raw.setdefault("paths", {}).update(collected["paths"])

    raw_excel = raw.setdefault("excel", {})
    raw_excel["workbook_path"] = collected["excel"]["workbook_path"]
    raw_excel["sheet_name"] = collected["excel"]["sheet_name"]
    raw_excel["header_row"] = collected["excel"]["header_row"]
    raw_excel["columns"] = collected["excel"]["columns"]

    raw_schema = raw.setdefault("schema", {})
    raw_schema["top_level_shapes_key"] = collected["schema"]["top_level_shapes_key"]
    raw_schema["required_shape_fields"] = collected["schema"]["required_shape_fields"]
    raw_schema["strict_required_fields"] = collected["schema"]["strict_required_fields"]
    raw_schema["stop_on_validation_error"] = collected["schema"]["stop_on_validation_error"]

    raw_parser = raw.setdefault("parser", {})
    raw_parser["export_pages"] = collected["parser"]["export_pages"]

    raw_execution = raw.setdefault("execution", {})
    raw_execution["parallel_enabled"] = collected["execution"]["parallel_enabled"]
    raw_execution["max_workers"] = collected["execution"]["max_workers"]
    raw["labels"] = collected["labels"]
    return raw


def write_runtime_config(parse_root: Path, raw: dict[str, Any]) -> Path:
    cache_dir = parse_root / ".cache" / "run_configs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix="parse_run_", suffix=".json", dir=str(cache_dir)
    )
    os.close(fd)
    path = Path(temp_path)
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def cleanup_runtime_config_file(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def load_program_default_workers(parse_root: Path) -> int:
    fallback = max(1, int(os.cpu_count() or 1))
    try:
        qc_root = parse_root.parents[4]
        config_path = qc_root / "config" / "default.yaml"
        data = ConfigManager(config_path).load() if config_path.exists() else {}
        parallel = data.get("parallel", {}) if isinstance(data, dict) else {}
        workers = int(parallel.get("max_workers", fallback) or fallback)
        return max(1, workers)
    except Exception:
        return fallback


def discover_schema_fields(
    input_root_value: str, shapes_key: str, config_dir: Path
) -> list[str]:
    discovered: set[str] = set()
    input_root = resolve_path(config_dir, input_root_value.strip())
    if input_root is None or not input_root.exists():
        return []

    scanned = 0
    try:
        for page_path in input_root.rglob("*.json"):
            if scanned >= 3:
                break
            scanned += 1
            try:
                raw = json.loads(page_path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            shapes = raw.get(shapes_key)
            if not isinstance(shapes, list):
                continue
            for shape in shapes[:50]:
                if not isinstance(shape, dict):
                    continue
                for key, value in shape.items():
                    if str(key) == "description":
                        continue
                    discovered.add(str(key))
                    if key == "flags" and isinstance(value, dict):
                        for sub_key in value.keys():
                            discovered.add(f"flags.{sub_key}")
    except Exception:
        return []
    return sorted(discovered)
