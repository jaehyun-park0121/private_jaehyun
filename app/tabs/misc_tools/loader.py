from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any, List, Optional

from app.tabs.misc_tools.base import BaseMiscToolApp, MiscToolAppMeta


_META_KEYS = {
    "APP_ID",
    "APP_NAME",
    "CATEGORY",
    "SUMMARY",
    "DESCRIPTION",
    "STATUS_TEXT",
    "STATUS_TONE",
    "ACCENT_START",
    "ACCENT_END",
    "META_LINE",
    "TAGS",
    "PRIMARY_ACTION",
    "SECONDARY_ACTION",
    "OWNER",
    "ENTRY_KIND",
    "MODULE_PATH",
    "DISPLAY_ORDER",
}


class LazyMiscToolApp(BaseMiscToolApp):
    """Proxy app that defers module import/instantiation until first execution."""

    def __init__(self, module_name: str, source_file: Path, meta: MiscToolAppMeta) -> None:
        self._module_name = module_name
        self._source_file = source_file
        self._meta = meta
        self._loaded_app: Optional[BaseMiscToolApp] = None

    def metadata(self) -> MiscToolAppMeta:
        return self._meta

    def _ensure_loaded(self) -> BaseMiscToolApp:
        if self._loaded_app is not None:
            return self._loaded_app

        module = importlib.import_module(self._module_name)
        app_cls = getattr(module, "App", None)
        if app_cls is None:
            raise TypeError(f"{self._module_name}.App not found")

        app = app_cls()
        if not isinstance(app, BaseMiscToolApp):
            raise TypeError(f"{self._module_name}.App must inherit BaseMiscToolApp")

        setattr(app, "source_file", self._source_file)
        self._loaded_app = app
        return app

    def build_workspace(self, parent=None):
        app = self._ensure_loaded()
        return app.build_workspace(parent)

    def run_tool(self, repo_root: Path) -> Optional[str]:
        app = self._ensure_loaded()
        return app.run_tool(repo_root)


class MiscToolAppLoader:
    def __init__(self, app_dir: Path, package_prefix: str = "app.tabs.misc_tools.apps") -> None:
        self.app_dir = app_dir
        self.package_prefix = package_prefix
        self.last_errors: List[str] = []

    def load_apps(self) -> List[BaseMiscToolApp]:
        importlib.invalidate_caches()
        self.last_errors = []
        loaded: List[BaseMiscToolApp] = []
        for dir_path in sorted(self.app_dir.iterdir()):
            if not dir_path.is_dir() or dir_path.name.startswith("_"):
                continue
            init_file = dir_path / "__init__.py"
            if not init_file.exists():
                self.last_errors.append(f"{dir_path.name}: Missing __init__.py: {init_file}")
                continue

            module_name = f"{self.package_prefix}.{dir_path.name}"
            try:
                meta = self._read_app_meta(init_file=init_file, fallback_app_id=dir_path.name)
                app = LazyMiscToolApp(module_name=module_name, source_file=init_file, meta=meta)
            except Exception as exc:
                self.last_errors.append(f"{dir_path.name}: {exc}")
                continue
            setattr(app, "source_file", init_file)
            loaded.append(app)
        loaded.sort(key=lambda item: (item.metadata().display_order, item.metadata().app_name))
        return loaded

    def _read_app_meta(self, *, init_file: Path, fallback_app_id: str) -> MiscToolAppMeta:
        source = init_file.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(init_file))
        app_class = self._find_app_class(tree)
        if app_class is None:
            raise TypeError(f"App class not found: {init_file}")

        values: dict[str, Any] = {}
        for stmt in app_class.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            key = stmt.targets[0].id
            if key not in _META_KEYS:
                continue
            value = self._safe_literal(stmt.value)
            if value is None:
                continue
            values[key] = value

        tags_value = values.get("TAGS", [])
        tags: List[str] = []
        if isinstance(tags_value, (list, tuple)):
            tags = [str(item) for item in tags_value if str(item).strip()]

        return MiscToolAppMeta(
            app_id=self._as_str(values.get("APP_ID"), fallback_app_id),
            app_name=self._as_str(values.get("APP_NAME"), fallback_app_id),
            category=self._as_str(values.get("CATEGORY"), BaseMiscToolApp.CATEGORY),
            summary=self._as_str(values.get("SUMMARY"), BaseMiscToolApp.SUMMARY),
            description=self._as_str(values.get("DESCRIPTION"), BaseMiscToolApp.DESCRIPTION),
            status_text=self._as_str(values.get("STATUS_TEXT"), BaseMiscToolApp.STATUS_TEXT),
            status_tone=self._as_str(values.get("STATUS_TONE"), BaseMiscToolApp.STATUS_TONE),
            accent_start=self._as_str(values.get("ACCENT_START"), BaseMiscToolApp.ACCENT_START),
            accent_end=self._as_str(values.get("ACCENT_END"), BaseMiscToolApp.ACCENT_END),
            meta_line=self._as_str(values.get("META_LINE"), BaseMiscToolApp.META_LINE),
            tags=tags,
            primary_action=self._as_str(values.get("PRIMARY_ACTION"), BaseMiscToolApp.PRIMARY_ACTION),
            secondary_action=self._as_str(values.get("SECONDARY_ACTION"), BaseMiscToolApp.SECONDARY_ACTION),
            owner=self._as_str(values.get("OWNER"), BaseMiscToolApp.OWNER),
            entry_kind=self._as_str(values.get("ENTRY_KIND"), BaseMiscToolApp.ENTRY_KIND),
            module_path=self._as_str(values.get("MODULE_PATH"), str(init_file)),
            display_order=self._as_int(values.get("DISPLAY_ORDER"), BaseMiscToolApp.DISPLAY_ORDER),
        )

    def _find_app_class(self, tree: ast.Module) -> Optional[ast.ClassDef]:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "App":
                return node
        return None

    def _safe_literal(self, node: ast.AST) -> Any:
        try:
            return ast.literal_eval(node)
        except Exception:
            return None

    def _as_str(self, value: Any, default: str) -> str:
        text = str(value if value is not None else "").strip()
        return text if text else default

    def _as_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)
