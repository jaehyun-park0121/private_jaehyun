from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

import yaml


class ConfigManager:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.data: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            example = self.config_path.with_name("default.yaml.example")
            if example.exists():
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(example, self.config_path)
            else:
                self.data = {}
                return self.data
        with self.config_path.open("r", encoding="utf-8") as file:
            self.data = yaml.safe_load(file) or {}
        return self.data

    def save(self, data: Dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
        self.data = data
