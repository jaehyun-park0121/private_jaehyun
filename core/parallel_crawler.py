"""
병렬 크롤링 오케스트레이터 (Phase 2)
- 수집된 링크들의 게시글 콘텐츠를 병렬로 크롤링
"""
import asyncio
import random
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

from shared.config import ParallelCrawlConfig
from shared.constants import USER_AGENTS
from utils.cookie_handler import remove_cookie_popup
from utils.cloudflare_handler import handle_cloudflare_challenge
from core.media_extractor import extract_media_from_page
import os


async def crawl_single_article(url, browser_context=None, config=None,
                               article_id=None, lang="EN",
                               proxy_manager=None, browser_mode='stealth',
                               log_func=None):
    """
    단일 게시글 크롤링

    Args:
        url: 게시글 URL
        browser_context: Playwright browser context (None이면 새로 생성)
        config: 사이트 설정
        article_id: 게시글 번호
        lang: 언어 코드
        proxy_manager: ProxyManager 인스턴스
        browser_mode: 크롤링 모드
        log_func: 로그 함수

    Returns:
        dict: 크롤링 결과
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    config = config or {}
    is_openai = "openai.com" in url.lower()

    try:
        own_context = browser_context is None
        ctx = browser_context
        browser = None

        if own_context:
            from playwright.async_api import async_playwright
            p = await async_playwright().start()

            browser_args = {
                'headless': False,
                'args': ['--disable-blink-features=AutomationControlled', '--no-sandbox']
            }

            # 프록시 설정
            if browser_mode in ['unlocker'] and proxy_manager:
                proxy_config = proxy_manager.get_phase2_proxy_config('auto')
                proxy_url = proxy_config.get('proxy_url')
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
                user_agent=random.choice(USER_AGENTS)
            )

        page = await ctx.new_page()

        # 페이지 로딩
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        # Cloudflare + 쿠키
        await handle_cloudflare_challenge(page, log_func=log_func)
        if is_openai:
            await remove_cookie_popup(page, log_func=log_func)

        # 제목 추출
        title = await page.title()

        # HTML 추출
        raw_html = await page.content()

        # article 본문 추출
        soup = BeautifulSoup(raw_html, 'html.parser')
        article_elem = soup.find('article') or soup.find('main')
        texts = []
        if article_elem:
            texts.append(f"<{article_elem.name}>{str(article_elem)}</{article_elem.name}>")

        # 미디어 추출
        images, videos, audios, media_stats = await extract_media_from_page(
            page, url, log_func=log_func
        )
        
        # PDF 다운로드 로직 (YAML 설정 기반)
        downloaded_pdfs = []
        crawling_config = config.get('crawling', {})
        pdf_selector = crawling_config.get('pdf_download_selector')
        
        if pdf_selector:
            try:
                log(f"   ⬇️ PDF 다운로드 시도 (selector: {pdf_selector})", "info")
                os.makedirs("downloads", exist_ok=True)
                
                # 버튼이 있는지 확인
                btn = await page.query_selector(pdf_selector)
                if btn and await btn.is_visible():
                    async with page.expect_download(timeout=30000) as download_info:
                        await btn.click()
                    download = await download_info.value
                    
                    # 게시글 번호나 시간 기준으로 이름이 겹치지 않게 조치 (KIPRIS 방지)
                    base_name = download.suggested_filename
                    safe_id = str(article_id if article_id else datetime.now().strftime("%H%M%S"))
                    file_name = f"{safe_id}_{base_name}"
                    
                    save_path = os.path.join("downloads", file_name)
                    await download.save_as(save_path)
                    
                    # --- [신규 기능] PDF 심층 분석 및 필터링 ---
                    try:
                        from core.pdf_analyzer import process_and_filter_pdf
                        log(f"   🔍 PDF 심층 파일 검증 중... (Digital Born, Multimodal): {file_name}", "info")
                        # 현재 라이선스 검증은 HTML에서 하므로 여기서는 False 기본
                        is_valid, reason = process_and_filter_pdf(save_path, require_license=False)
                        
                        if is_valid:
                            downloaded_pdfs.append(save_path)
                            log(f"   ✅ [합격] PDF 검증 완료 및 최종 보관: {file_name}", "success")
                        else:
                            # 조건에 맞지 않으면 즉시 삭제하여 디스크 용량 낭비 방지
                            try:
                                os.remove(save_path)
                            except Exception:
                                pass
                            log(f"   ⚠️ [탈락] PDF 조건 미달 (삭제됨): {reason} - {file_name}", "warning")
                            
                    except ImportError:
                        # pdf_analyzer가 없거나 PyMuPDF가 안 깔려있으면 그냥 보관
                        downloaded_pdfs.append(save_path)
                        log(f"   ✅ PDF 다운로드 완료 (필터 모듈 없음): {file_name}", "success")
                else:
                    log(f"   ⚠️ PDF 다운로드 버튼을 찾을 수 없음 ({pdf_selector})", "warning")
            except Exception as e:
                log(f"   ❌ PDF 다운로드 대기 중 실패 (또는 새 탭으로 열림): {e}", "warning")

        await page.close()
        if own_context and browser:
            await browser.close()

        return {
            'success': True,
            'url': url,
            'final_url': url,
            'title': title,
            'texts': texts,
            'images': images,
            'videos': videos,
            'audios': audios,
            'downloaded_pdfs': downloaded_pdfs,
            'raw_html': raw_html,
            'status': 200,
            'article_id': article_id,
            'lang': lang,
            'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
            'media_stats': media_stats
        }

    except Exception as e:
        log(f"   ❌ 게시글 크롤링 실패 ({url[:50]}...): {str(e)[:80]}", "error")
        return {
            'success': False,
            'url': url,
            'error': str(e),
            'article_id': article_id,
            'lang': lang
        }


async def crawl_articles_parallel(article_links, config=None,
                                  parallel_config=None,
                                  proxy_manager=None,
                                  browser_mode='stealth',
                                  site_name="",
                                  stop_event=None,
                                  log_func=None):
    """
    게시글 콘텐츠 병렬 크롤링 (Phase 2)

    Args:
        article_links: [{'url': str, 'title': str, 'article_id': int, 'lang': str}, ...]
        config: 사이트 설정
        parallel_config: ParallelCrawlConfig 인스턴스
        proxy_manager: ProxyManager 인스턴스
        browser_mode: 'stealth', 'unlocker', 'scraping_browser'
        site_name: 사이트명
        stop_event: 중지 이벤트 (threading.Event)
        log_func: 로그 함수

    Returns:
        dict: {'crawled_articles': [...], 'failed_articles': [...]}
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    if parallel_config is None:
        parallel_config = ParallelCrawlConfig()

    config = config or {}
    total = len(article_links)
    crawled_articles = []
    failed_articles = []

    log(f"\n{'='*60}", "header")
    log(f"⚡ Phase 2: 게시글 크롤링 시작 ({total}개)", "header")
    log(f"{'='*60}", "header")
    log(f"   모드: {browser_mode}", "info")
    log(f"   동시 요청: {parallel_config.max_concurrent}개", "info")
    log(f"   배치 크기: {parallel_config.batch_size}개", "info")

    # 세마포어로 동시 요청 제한
    semaphore = asyncio.Semaphore(parallel_config.max_concurrent)

    async def _crawl_with_limit(link_info, index):
        """세마포어로 동시 요청 제한"""
        if stop_event and stop_event.is_set():
            return None

        async with semaphore:
            # 딜레이
            delay = random.uniform(parallel_config.delay_min, parallel_config.delay_max)
            await asyncio.sleep(delay)

            log(f"   [{index+1}/{total}] 🔄 {link_info['url'][:60]}...", "info")

            result = await crawl_single_article(
                url=link_info['url'],
                config=config,
                article_id=link_info.get('article_id', index + 1),
                lang=link_info.get('lang', 'EN'),
                proxy_manager=proxy_manager,
                browser_mode=browser_mode,
                log_func=log_func
            )

            if result and result.get('success'):
                log(f"   [{index+1}/{total}] ✅ 성공: {result.get('title', '')[:40]}", "success")
            else:
                error = result.get('error', 'Unknown') if result else 'No result'
                log(f"   [{index+1}/{total}] ❌ 실패: {error[:50]}", "error")

            return result

    # 배치 처리
    batch_size = parallel_config.batch_size
    for batch_start in range(0, total, batch_size):
        if stop_event and stop_event.is_set():
            log("⚠️ 중지 요청 감지 - 크롤링 중단", "warning")
            break

        batch_end = min(batch_start + batch_size, total)
        batch = article_links[batch_start:batch_end]

        log(f"\n📦 배치 {batch_start//batch_size + 1}: {batch_start+1}~{batch_end} / {total}", "info")

        tasks = [
            _crawl_with_limit(link_info, batch_start + i)
            for i, link_info in enumerate(batch)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_articles.append({
                    'url': batch[i]['url'],
                    'error': str(result)
                })
            elif result is None:
                pass  # 중지됨
            elif result.get('success'):
                crawled_articles.append(result)
            else:
                failed_articles.append({
                    'url': batch[i]['url'],
                    'error': result.get('error', 'Unknown')
                })

        log(f"   📊 배치 결과: 성공 {len(crawled_articles)}개, 실패 {len(failed_articles)}개", "info")

    log(f"\n{'='*60}", "header")
    log(f"✅ Phase 2 완료: 성공 {len(crawled_articles)}개 / 실패 {len(failed_articles)}개 / 총 {total}개", "success")
    log(f"{'='*60}", "header")

    return {
        'crawled_articles': crawled_articles,
        'failed_articles': failed_articles,
        'total': total
    }
