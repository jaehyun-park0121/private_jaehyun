"""
URL 관련 유틸리티 함수
- decode_redirect_url: Facebook/LinkedIn 등의 리다이렉트 URL에서 실제 URL 추출
- get_source_info_from_url: URL에서 수집처 코드 추출
"""
import re
from urllib.parse import urlparse, parse_qs, unquote, quote

from shared.constants import URL_TO_SOURCE_INFO


def decode_redirect_url(url):
    """
    Facebook/LinkedIn 등의 리다이렉트 URL에서 실제 URL 추출

    예시:
    - l.facebook.com/l.php?u=https%3A%2F%2Fabout.fb.com%2F...
      → https://about.fb.com/...
    """
    if not url:
        return url

    # Facebook Lynx 리다이렉트 처리
    if 'l.facebook.com/l.php' in url:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'u' in params:
                return unquote(params['u'][0])
        except Exception:
            pass

    # open.go.kr javascript detail link -> real URL
    if isinstance(url, str) and url.lower().startswith("javascript:"):
        try:
            match = re.search(
                r"goDetail\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'[^']*')?\s*\)",
                url,
                re.IGNORECASE,
            )
            if match:
                return (
                    "/othicInfo/infoList/infoListDetl.do?"
                    f"prdnNstRgstNo={quote(match.group(1), safe='')}&"
                    f"prdnDt={quote(match.group(2), safe='')}&"
                    f"nstSeCd={quote(match.group(3), safe='')}&"
                    "title=%EC%9B%90%EB%AC%B8%EC%A0%95%EB%B3%B4"
                )
        except Exception:
            pass

    return url


def get_source_info_from_url(url):
    """
    URL에서 수집처 코드와 URL 구분자를 추출

    Returns:
        tuple: (수집처코드, URL구분자) 예: ('OAI', 'news')
    """
    if not url:
        return ('UNKNOWN', 'unknown')

    url_lower = url.lower()

    # 긴 패턴부터 매칭 (더 구체적인 패턴 우선)
    sorted_patterns = sorted(URL_TO_SOURCE_INFO.items(), key=lambda x: len(x[0]), reverse=True)

    for domain_pattern, (code, identifier) in sorted_patterns:
        if domain_pattern in url_lower:
            return (code, identifier)

    return ('UNKNOWN', 'unknown')
