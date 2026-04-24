"""
Bright Data Browser API (Scraping Browser) 크롤러
- fetch_via_sb: Scraping Browser CDP 연결 크롤링 (main.py에서 이식)
- test_with_scraping_browser: Phase 1 + Phase 2
"""
import random
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote_plus
from playwright.async_api import async_playwright

from utils.cookie_handler import remove_cookie_popup
from utils.svg_capture import capture_svg_elements
from core.media_extractor import extract_media_from_page
from shared.constants import USER_AGENTS


async def fetch_via_sb(url, sb_auth, timeout_ms=120000,
                       capture_svg=False, lang_prefix="OAI_EN",
                       article_id=None, is_openai_news=False,
                       log_func=None):
    """
    Bright Data Scraping Browser를 통한 크롤링 (main.py fetch_via_sb 이식)

    Args:
        url: 크롤링할 URL
        sb_auth: Scraping Browser WSS 인증 URL
        timeout_ms: 타임아웃
        capture_svg: SVG 캡처 여부
        lang_prefix: 언어 접두사
        article_id: 게시글 ID
        is_openai_news: OpenAI News 여부
        log_func: 로그 함수

    Returns:
        dict: 크롤링 결과
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    try:
        async with async_playwright() as p:
            log(f"   🌐 Scraping Browser 연결 중...", "info")

            browser = await p.chromium.connect_over_cdp(sb_auth)

            # 기존 컨텍스트 사용 또는 새로 생성
            contexts = browser.contexts
            if contexts:
                ctx = contexts[0]
            else:
                locale = 'ko-KR' if '/ko-KR/' in url or '/ko/' in url else 'en-US'
                timezone_id = 'Asia/Seoul' if locale == 'ko-KR' else 'America/New_York'
                ctx = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    accept_downloads=True,
                    locale=locale,
                    timezone_id=timezone_id
                )

            page = await ctx.new_page()

            # 네트워크 모니터링 (오디오 URL 수집)
            audio_urls = []

            def handle_response(response):
                try:
                    content_type = response.headers.get("content-type", "").lower()
                    resp_url = response.url
                    if any(ext in resp_url.lower() for ext in [".mp3", ".wav", ".m4a", ".ogg", ".aac"]) or \
                       "audio" in content_type or "mpeg" in content_type:
                        audio_urls.append(resp_url)
                except Exception:
                    pass

            page.on("response", handle_response)

            await page.goto(url, wait_until="load", timeout=timeout_ms)
            await page.wait_for_timeout(5000)

            # 스크롤
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(1000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
            except Exception:
                pass

            # SVG 캡처
            svg_files = []
            if capture_svg and is_openai_news:
                try:
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(1000)

                    await page.evaluate("""
                        async () => {
                            const scrollStep = window.innerHeight * 0.8;
                            const maxScroll = document.body.scrollHeight;
                            for (let y = 0; y < maxScroll; y += scrollStep) {
                                window.scrollTo(0, y);
                                await new Promise(resolve => setTimeout(resolve, 500));
                            }
                            window.scrollTo(0, 0);
                        }
                    """)
                    await page.wait_for_timeout(2000)

                    capture_result = await capture_svg_elements(
                        page, site_name="OpenAI",
                        output_folder="screenshots_browser_api",
                        log_func=log_func,
                        prefix=lang_prefix,
                        article_id=article_id
                    )
                    if capture_result['success']:
                        svg_files = capture_result['files']
                except Exception as e:
                    log(f"      ⚠️ SVG 캡처 실패: {str(e)[:50]}", "warning")

            # 콘텐츠 추출
            raw_html = await page.content()
            title = await page.title()
            final_url = page.url

            # 미디어 추출
            images, videos, audios, media_stats = await extract_media_from_page(
                page, url, log_func=log_func
            )

            # 네트워크에서 발견된 오디오 URL 추가
            for audio_url in audio_urls:
                if not any(a.get('audio_url') == audio_url for a in audios):
                    audios.append({
                        'idx': len(audios),
                        'audio_url': audio_url,
                        'title': 'Network captured'
                    })

            # article 추출
            soup = BeautifulSoup(raw_html, 'html.parser')
            article_elem = soup.find('article') or soup.find('main')
            texts = []
            if article_elem:
                texts.append(f"<{article_elem.name}>{str(article_elem)}</{article_elem.name}>")

            await ctx.close()
            await browser.close()

            return {
                'success': True,
                'status': 200,
                'final_url': final_url,
                'title': title,
                'texts': texts,
                'images': images,
                'videos': videos,
                'audios': audios,
                'raw_html': raw_html,
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                'media_stats': media_stats,
                'svg_files': svg_files
            }

    except Exception as e:
        log(f"      ❌ Scraping Browser 크롤링 실패: {str(e)[:100]}", "error")
        return {'success': False, 'error': str(e)}


async def recrawl_browser_api(url, sb_auth, is_openai=False, article_id=None,
                              capture_svg=False, log_func=None):
    """Scraping Browser를 이용한 단일 URL 재크롤링"""
    return await fetch_via_sb(
        url=url,
        sb_auth=sb_auth,
        capture_svg=capture_svg,
        is_openai_news=is_openai,
        article_id=article_id,
        lang_prefix="OAI_EN" if not ('/ko-KR/' in url or '/ko/' in url) else "OAI_KO",
        log_func=log_func
    )
