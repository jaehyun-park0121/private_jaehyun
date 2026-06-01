from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PyQt5.QtWidgets import QWidget


@dataclass(frozen=True)
class MiscToolAppMeta:
    app_id: str
    app_name: str
    category: str
    summary: str
    description: str
    status_text: str
    status_tone: str
    accent_start: str
    accent_end: str
    meta_line: str
    tags: List[str] = field(default_factory=list)
    primary_action: str = "패널 열기"
    secondary_action: str = "상세 보기"
    owner: str = "미지정"
    entry_kind: str = "internal"
    module_path: str = ""
    display_order: int = 100


class BaseMiscToolApp(ABC):
    APP_ID = "base_misc_tool"
    APP_NAME = "Base Misc Tool"
    CATEGORY = "기타"
    SUMMARY = ""
    DESCRIPTION = ""
    STATUS_TEXT = "준비 중"
    STATUS_TONE = "neutral"
    ACCENT_START = "#cbd5f5"
    ACCENT_END = "#e2e8f0"
    META_LINE = ""
    TAGS: List[str] = []
    PRIMARY_ACTION = "패널 열기"
    SECONDARY_ACTION = "상세 보기"
    OWNER = "미지정"
    ENTRY_KIND = "internal"
    MODULE_PATH = ""
    DISPLAY_ORDER = 100

    def metadata(self) -> MiscToolAppMeta:
        return MiscToolAppMeta(
            app_id=self.APP_ID,
            app_name=self.APP_NAME,
            category=self.CATEGORY,
            summary=self.SUMMARY,
            description=self.DESCRIPTION,
            status_text=self.STATUS_TEXT,
            status_tone=self.STATUS_TONE,
            accent_start=self.ACCENT_START,
            accent_end=self.ACCENT_END,
            meta_line=self.META_LINE,
            tags=list(self.TAGS),
            primary_action=self.PRIMARY_ACTION,
            secondary_action=self.SECONDARY_ACTION,
            owner=self.OWNER,
            entry_kind=self.ENTRY_KIND,
            module_path=self.MODULE_PATH,
            display_order=self.DISPLAY_ORDER,
        )

    def build_workspace(self, parent: Optional[QWidget] = None) -> Optional[QWidget]:
        return None

    def run_tool(self, repo_root: Path) -> Optional[str]:
        del repo_root
        return None
