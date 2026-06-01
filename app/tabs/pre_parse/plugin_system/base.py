from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from .context import PageContext
from .result_model import CheckResult


class BasePlugin(ABC):
    PLUGIN_ID = "base_plugin"
    TAG = "general"
    DESCRIPTION = ""

    def plugin_id(self) -> str:
        plugin_id = str(getattr(self, "PLUGIN_ID", "")).strip()
        if plugin_id and plugin_id != "base_plugin":
            return plugin_id
        source_file = getattr(self, "source_file", None)
        if isinstance(source_file, Path):
            return source_file.stem
        return self.__class__.__name__.lower()

    def plugin_tag(self) -> str:
        return str(getattr(self, "TAG", "")).strip()

    def metadata(self) -> Dict[str, str]:
        return {
            "plugin_id": self.plugin_id(),
            "tag": self.plugin_tag(),
            "description": self.DESCRIPTION,
        }

    def option_schema(self) -> List[Dict[str, Any]]:
        """검수 목록 UI에서 사용할 옵션 스키마(선택)"""
        return []


class BaseCheckPlugin(BasePlugin, ABC):
    @abstractmethod
    def run(self, page_context: PageContext) -> CheckResult:
        raise NotImplementedError
