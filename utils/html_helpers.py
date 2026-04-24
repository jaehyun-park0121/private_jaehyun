"""
HTML 관련 헬퍼 함수
"""
from bs4 import BeautifulSoup


def get_title(html):
    """HTML에서 페이지 제목 추출"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:150]
    except Exception:
        pass
    return ""
