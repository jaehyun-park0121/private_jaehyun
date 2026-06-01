from pathlib import Path
from typing import Optional, TYPE_CHECKING

from app.tabs.misc_tools.base import BaseMiscToolApp

if TYPE_CHECKING:
    from .launcher_dialog import ParseLauncherDialog


class App(BaseMiscToolApp):
    APP_ID = "parse"
    APP_NAME = "문서 파서"
    CATEGORY = "파싱"
    SUMMARY = "페이지 단위 JSON/PNG를 문서 단위 JSON과 산출물로 변환합니다."
    DESCRIPTION = "document_parser CLI를 실행해 문서 파싱을 수행합니다."
    STATUS_TEXT = "실행 가능"
    STATUS_TONE = "active"
    ACCENT_START = "#ffffff"
    ACCENT_END = "#f8fafc"
    META_LINE = "page json/png -> document json"
    TAGS = ["Parse", "JSON", "PNG"]
    PRIMARY_ACTION = "도구 실행"
    SECONDARY_ACTION = "상세 보기"
    OWNER = "파싱 운영"
    ENTRY_KIND = "internal"
    MODULE_PATH = "app/tabs/misc_tools/apps/parse/launcher_dialog/"
    DISPLAY_ORDER = 10

    def __init__(self) -> None:
        self._dialog: Optional["ParseLauncherDialog"] = None

    def run_tool(self, repo_root: Path) -> str:
        from .launcher_dialog import ParseLauncherDialog

        app_root = repo_root / "app" / "tabs" / "misc_tools" / "apps" / "parse"
        if not app_root.exists():
            return ""
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.raise_()
            self._dialog.activateWindow()
            return "문서 파서 설정 창이 이미 열려 있습니다."

        self._dialog = ParseLauncherDialog(app_root)
        self._dialog.destroyed.connect(self._on_dialog_destroyed)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        return "문서 파서 설정 창을 열었습니다."

    def _on_dialog_destroyed(self, _obj=None) -> None:
        self._dialog = None

