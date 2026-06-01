"""정적 자산 (JS, CSS) 로더."""

from pathlib import Path
from functools import lru_cache

_ASSET_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load_text(name: str) -> str:
    """app/assets/<name> 파일을 UTF-8 텍스트로 로드."""
    return (_ASSET_DIR / name).read_text(encoding="utf-8")


def table_edit_js() -> str:
    return load_text("table_edit.js")


def assets_dir() -> Path:
    """assets 디렉토리 절대 경로. WebView setHtml의 baseUrl 구성에 사용."""
    return _ASSET_DIR
