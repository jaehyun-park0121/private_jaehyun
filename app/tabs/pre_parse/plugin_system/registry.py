from typing import Dict, Iterable, List

from app.tabs.pre_parse.plugin_system.base import BasePlugin


class CheckRegistry:
    def __init__(self) -> None:
        self._plugins: Dict[str, BasePlugin] = {}

    def register(self, plugin: BasePlugin) -> None:
        plugin_id = plugin.plugin_id()
        if plugin_id in self._plugins:
            raise ValueError(f"Duplicated plugin id: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def get(self, plugin_id: str) -> BasePlugin:
        return self._plugins[plugin_id]

    def all(self) -> List[BasePlugin]:
        return list(self._plugins.values())

    def ids(self) -> Iterable[str]:
        return self._plugins.keys()
