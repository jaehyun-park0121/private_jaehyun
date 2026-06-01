from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import List, Optional

from app.tabs.pre_parse.plugin_system.base import BasePlugin
from app.tabs.pre_parse.plugin_system.registry import CheckRegistry


class PluginLoader:
    def __init__(self, plugin_dir: Path) -> None:
        self.plugin_dir = plugin_dir

    def load_into_registry(self, registry: CheckRegistry) -> List[BasePlugin]:
        loaded: List[BasePlugin] = []
        for file_path in sorted(self.plugin_dir.glob("*.py")):
            if file_path.name.startswith("_"):
                continue
            module = self._load_module(file_path)
            plugin = self._create_plugin(module)
            if plugin is None:
                continue
            # 플러그인 인스턴스에 소스 파일 경로를 저장해두면
            # UI에서 파일명을 그대로 사용할 수 있다.
            setattr(plugin, "source_file", file_path)
            # 파일명 기반 ID를 인스턴스에 주입한다.
            setattr(plugin, "PLUGIN_ID", file_path.stem)
            registry.register(plugin)
            loaded.append(plugin)
        return loaded

    def _load_module(self, file_path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(file_path.stem, str(file_path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot create spec: {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _create_plugin(self, module: ModuleType) -> Optional[BasePlugin]:
        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls is None:
            return None
        plugin = plugin_cls()
        if not isinstance(plugin, BasePlugin):
            raise TypeError(f"{module.__name__}.Plugin must inherit BasePlugin")
        return plugin
