"""
Web Unlocker 크롤러 (Phase 1 + Phase 2)
- Bright Data Web Unlocker 프록시를 통한 크롤링
"""
import random
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

from utils.cookie_handler import remove_cookie_popup
from utils.cloudflare_handler import handle_cloudflare_challenge
from utils.svg_capture import capture_svg_elements
from core.media_extractor import extract_media_from_page
from core.search_handler import apply_search_if_configured
from shared.constants import USER_AGENTS
from core.pagination_handler import handle_pagination


async def recrawl_unlocker(url, proxy_url, is_openai=False, article_id=None,
                           capture_svg=False, svg_output_folder="screenshots",
                           lang_prefix="OAI_EN", log_func=None):
    """
    Web Unlocker 프록시를 이용한 단일 URL 재크롤링

    Args:
        url: 크롤링할 URL
        proxy_url: Unlocker 프록시 URL
        is_openai: OpenAI 여부
        article_id: 게시글 ID
        capture_svg: SVG 캡처 여부
        svg_output_folder: SVG 저장 폴더
        lang_prefix: 언어 접두사
        log_func: 로그 함수
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    try:
        async with async_playwright() as p:
            browser_args = {
                'headless': False,
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            }

            if proxy_url:
                # 프록시 URL 파싱
                from urllib.parse import urlparse as parse_url
                parsed = parse_url(proxy_url)
                browser_args['proxy'] = {
                    'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                    'username': parsed.username,
                    'password': parsed.password
                }

            browser = await p.chromium.launch(**browser_args)

            ctx = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=random.choice(USER_AGENTS),
                locale='ko-KR',
                timezone_id='Asia/Seoul',
                extra_http_headers={'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'}
            )

            page = await ctx.new_page()
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(5000)

            # Cloudflare 처리
            await handle_cloudflare_challenge(page, log_func=log_func)

            if is_openai:
                await remove_cookie_popup(page, log_func=log_func)

            if capture_svg and is_openai:
                await capture_svg_elements(
                    page, "recrawl", output_folder=svg_output_folder,
                    log_func=log_func, prefix=lang_prefix, article_id=article_id
                )

            title = await page.title()
            raw_html = await page.content()

            soup = BeautifulSoup(raw_html, 'html.parser')
            article_elem = soup.find('article') or soup.find('main')
            texts = []
            if article_elem:
                texts.append(f"<{article_elem.name}>{str(article_elem)}</{article_elem.name}>")

            images, videos, audios, media_stats = await extract_media_from_page(
                page, url, log_func=log_func
            )

            await ctx.close()
            await browser.close()

            return {
                'success': True,
                'final_url': url,
                'title': title,
                'texts': texts,
                'images': images,
                'videos': videos,
                'audios': audios,
                'raw_html': raw_html,
                'status': 200,
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                'media_stats': media_stats
            }

    except Exception as e:
        log(f"      ❌ Unlocker 크롤링 실패: {str(e)[:100]}", "error")
        return {'success': False, 'error': str(e)}


async def test_with_unlocker(url, config, proxy_url, user_max_value=20,
                             phase1_only=False, remove_duplicates=True,
                             log_func=None):
    """
    Web Unlocker 모드로 Phase 1 (링크 수집)

    Returns:
        dict: 테스트 결과
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    pagination = config.get('pagination', {})
    crawling_config = config.get('crawling', {})
    wait_until = crawling_config.get('wait_until', 'networkidle')

    async with async_playwright() as p:
        log("🌐 Web Unlocker 브라우저 시작 중...", "info")

        browser_args = {
            'headless': False,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        }

        if proxy_url:
            from urllib.parse import urlparse as parse_url
            parsed = parse_url(proxy_url)
            browser_args['proxy'] = {
                'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                'username': parsed.username,
                'password': parsed.password
            }

        browser = await p.chromium.launch(**browser_args)

        ctx = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=random.choice(USER_AGENTS),
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9'
            }
        )

        page = await ctx.new_page()

        log(f"📄 페이지 로딩: {url}", "info")
        await page.goto(url, wait_until=wait_until, timeout=60000)
        await page.wait_for_timeout(5000)

        # Cloudflare
        await handle_cloudflare_challenge(page, log_func=log_func)
        await remove_cookie_popup(page, log_func=log_func)

        await apply_search_if_configured(page, config, url, log_func=log_func)

        # Phase 1: 링크 수집
        log(f"\n📋 페이지네이션 시작 (통합 모듈 사용)", "info")
        
        result = await handle_pagination(
            page=page,
            url=url,
            config=config,
            user_max_value=user_max_value,
            log_func=log_func,
            execution_phase='phase1' if phase1_only else 'all',
            proxy_name='unlocker'
        )

        await browser.close()
        
        # Override method_used proxy_used for consistency if needed, but pagination_handler sets them.
        result['method_used'] = 'unlocker'
        result['proxy_used'] = 'Web Unlocker'

        return result
