"""
언어 관련 유틸리티
"""


def get_language_settings(is_openai, url):
    """OpenAI 사이트의 언어 설정 반환"""
    if is_openai:
        if '/ko-KR/' in url or '/ko/' in url:
            return {'locale': 'ko-KR', 'timezone_id': 'Asia/Seoul', 'lang': 'KO'}
        else:
            return {'locale': 'en-US', 'timezone_id': 'America/New_York', 'lang': 'EN'}
    else:
        return {'locale': 'ko-KR', 'timezone_id': 'Asia/Seoul', 'lang': 'KO'}


def get_lang_prefix(url):
    """URL에서 언어 접두사 추출 (SVG 캡처용)"""
    if '/ko-KR/' in url or '/ko/' in url:
        return "OAI_KO"
    else:
        return "OAI_EN"


def get_other_language_url(url):
    """URL에서 다른 언어 URL 생성"""
    if '/ko-KR/' in url:
        return url.replace('/ko-KR/', '/')
    elif '/ko/' in url:
        return url.replace('/ko/', '/')
    else:
        # 영어 → 한국어
        if 'openai.com/index/' in url:
            return url.replace('/index/', '/ko-KR/index/')
        return None
