from pathlib import Path
from typing import Optional

from app.tabs.misc_tools.base import BaseMiscToolApp


class App(BaseMiscToolApp):
    APP_ID = "template"
    APP_NAME = "앱 템플릿"
    CATEGORY = "가이드"
    SUMMARY = "신규 misc app을 만들 때 카드 항목과 실행 기능을 어디에 넣는지 보여주는 템플릿입니다."
    DESCRIPTION = (
        "카드 텍스트 입력 위치\n"
        "- APP_NAME: 카드 제목\n"
        "- SUMMARY: 카드 요약 (제목 아래)\n"
        "- STATUS_TEXT: 카드 우측 하단 상태 배지\n"
        "- MODULE_PATH: 앱 엔트리 파일 경로\n"
        "\n"
        "앱 기능 연결 위치\n"
        "- run_tool(self, repo_root): 카드 클릭 시 실행 동작 구현\n"
        "- build_workspace(self, parent): 탭 내부 위젯형 도구가 필요할 때 구현\n"
        "\n"
        "이 템플릿 카드는 기본 동작으로 안내 팝업만 표시합니다."
    )
    STATUS_TEXT = "TEMPLATE"
    STATUS_TONE = "neutral"
    ACCENT_START = "#dbeafe"
    ACCENT_END = "#bfdbfe"
    META_LINE = "template / starter / guide"
    TAGS = ["Template", "Starter", "Guide"]
    OWNER = "중앙화 코드"
    ENTRY_KIND = "internal"
    MODULE_PATH = "app/tabs/misc_tools/apps/template/__init__.py"
    DISPLAY_ORDER = 5

    def run_tool(self, repo_root: Path) -> Optional[str]:
        # Return None to use the default info popup in misc_tools/page.py.
        del repo_root
        return None

