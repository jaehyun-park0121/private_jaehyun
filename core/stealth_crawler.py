"""
Stealth 모드 크롤러 (Phase 1 + Phase 2)
- 로컬 Playwright 사용 (프록시 없음)
- 봇 감지 우회 스크립트 내장
"""
import random
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

from utils.cookie_handler import remove_cookie_popup
from utils.cloudflare_handler import handle_cloudflare_challenge
from utils.svg_capture import capture_svg_elements
from core.search_handler import apply_search_if_configured
from core.pagination_handler import handle_pagination
import os

# ========== Stealth 초기화 스크립트 ==========
STEALTH_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
"""


async def recrawl_stealth(url, is_openai=False, article_id=None,
                          capture_svg=False, svg_output_folder="screenshots",
                          lang_prefix="OAI_EN", log_func=None):
    """
    Stealth 모드로 단일 URL 재크롤링

    Args:
        url: 크롤링할 URL
        is_openai: OpenAI 사이트 여부
        article_id: 게시글 ID
        capture_svg: SVG 캡처 여부
        svg_output_folder: SVG 저장 폴더
        lang_prefix: 언어 접두사
        log_func: 로그 함수

    Returns:
        dict: 크롤링 결과
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )

            ctx = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                locale='ko-KR',
                timezone_id='Asia/Seoul',
                extra_http_headers={'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'}
            )

            page = await ctx.new_page()
            await page.add_init_script(STEALTH_INIT_SCRIPT)

            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(5000)

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
        log(f"      ❌ Stealth 크롤링 실패: {str(e)[:100]}", "error")
        return {'success': False, 'error': str(e)}

async def execute_spa_inline_download(page, config, url, user_max_value, log_func=None):
    """KIPRIS처럼 페이지 이동 불가한 SPA(세션 유지) 사이트를 위한 인라인 다운로드 처리"""
    def log(msg, level="info"):
        if log_func: log_func(msg, level)
        
    crawling_config = config.get('crawling', {})
    list_selector = crawling_config.get('list_item_selector', 'article')
    detail_btn_selector = crawling_config.get('detail_link_selector', 'button')
    pdf_selector = crawling_config.get('pdf_download_selector', 'a.btn-download-pdf')
    
    downloaded_pdfs = []
    
    for page_num in range(1, user_max_value + 1):
        log(f"\n📄 [SPA 인라인 모드] {page_num}페이지 검색 결과 수집 중...", "info")
        await page.wait_for_timeout(2000)
        
        # 목록 가져오기
        items = await page.query_selector_all(list_selector)
        if not items:
            log("⚠️ 검색 결과가 더 이상 없습니다.", "warning")
            break
            
        log(f"   💡 현재 페이지에서 {len(items)}개의 문서를 발견했습니다.", "success")
        
        for idx, item in enumerate(items, 1):
            try:
                # 1. 상세 보기 버튼 클릭 (아코디언 형태라고 가정)
                detail_btn = await item.query_selector(detail_btn_selector)
                if not detail_btn:
                    # KIPRIS의 경우, global로 찾기
                    detail_btn = await page.query_selector_all(f"{list_selector}:nth-child({idx}) {detail_btn_selector}")
                    if detail_btn: detail_btn = detail_btn[0]
                    
                if detail_btn:
                    await detail_btn.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await detail_btn.click(force=True)
                    log(f"   [{idx}/{len(items)}] 📖 상세 내용 열기 성공", "info")
                    await page.wait_for_timeout(2000) # 로딩 대기
                    
                    # 2. PDF 전문 다운로드 버튼 클릭
                    pdf_btn = await page.query_selector(pdf_selector)
                    if pdf_btn and await pdf_btn.is_visible():
                        async with page.expect_download(timeout=30000) as download_info:
                            await pdf_btn.click()
                        download = await download_info.value
                        
                        os.makedirs("downloads", exist_ok=True)
                        import time
                        file_name = f"{int(time.time())}_{download.suggested_filename}"
                        save_path = os.path.join("downloads", file_name)
                        await download.save_as(save_path)
                        
                        # 3. PDF 필터링 연동
                        try:
                            from core.pdf_analyzer import process_and_filter_pdf
                            log(f"      🔍 PDF 심층 검증 중: {download.suggested_filename}", "info")
                            is_valid, reason = process_and_filter_pdf(save_path, require_license=False)
                            if is_valid:
                                downloaded_pdfs.append(save_path)
                                log(f"      ✅ [합격] PDF 최종 보관 됨", "success")
                            else:
                                os.remove(save_path)
                                log(f"      ⚠️ [탈락] 조건 미달 (삭제됨): {reason}", "warning")
                        except Exception as e:
                            log(f"      ⚠️ 분석기 에러 (그냥 보관함): {e}", "warning")
                            downloaded_pdfs.append(save_path)
                    else:
                        log(f"      ⚠️ 첨부된 PDF가 없습니다.", "warning")
                else:
                    log(f"   [{idx}/{len(items)}] ⚠️ 상세 열기 버튼을 못 찾았습니다.", "error")
            except Exception as e:
                log(f"   [{idx}/{len(items)}] ❌ 항목 처리 중 에러: {str(e)[:50]}", "error")
                
        # [TODO: KIPRIS 페이지네이션 '다음' 버튼 클릭 로직. 현재는 첫 페이지의 항목들만 순회]
        log(f"   (SPA 인라인 시연: {page_num}페이지 루프 종료)", "info")
        break # 시연용이므로 일단 1페이지 처리 후 멈춤
        
    return {
        'success': True,
        'method_used': 'spa_inline_download',
        'downloaded_pdfs': downloaded_pdfs,
        'crawled_articles': [{'title': 'SPA Crawled PDF', 'url': p} for p in downloaded_pdfs]
    }

async def test_with_stealth(url, config, user_max_value=20,
                            phase1_only=False, category_slug=None,
                            remove_duplicates=True, log_func=None):
    """
    Stealth 모드로 Phase 1 (링크 수집) + Phase 2 (콘텐츠 크롤링) 실행

    Args:
        url: 시작 URL
        config: YAML 사이트 설정
        user_max_value: 최대 클릭/페이지 수
        phase1_only: Phase 1만 실행
        category_slug: 카테고리 필터
        remove_duplicates: 중복 링크 제거
        log_func: 로그 함수

    Returns:
        dict: 테스트 결과
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    pagination = config.get('pagination', {})
    is_openai_news = "openai.com" in url and "/news" in url
    crawling_config = config.get('crawling', {})
    wait_until = crawling_config.get('wait_until', 'networkidle')

    async with async_playwright() as p:
        log("🌐 브라우저 시작 중...", "info")

        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )

        ctx = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Upgrade-Insecure-Requests': '1'
            }
        )

        page = await ctx.new_page()
        await page.add_init_script(STEALTH_INIT_SCRIPT)
        log("✅ Stealth 모드 활성화 (봇 감지 우회)", "success")

        log(f"📄 페이지 로딩: {url}", "info")
        log(f"⏳ 페이지 로딩 대기 조건: {wait_until}", "info")
        await page.goto(url, wait_until=wait_until, timeout=60000)

        # Cloudflare 검증 대기
        log("⏳ Cloudflare 검증 대기 중... (20초)", "info")
        await page.wait_for_timeout(20000)

        try:
            await page.wait_for_function(
                """!document.body.textContent.includes('Just a moment') &&
                   !document.body.textContent.includes('Please unblock challenges.cloudflare.com') &&
                   !document.body.textContent.includes('Checking your browser')""",
                timeout=30000
            )
            log("✅ Cloudflare challenge passed", "success")
        except Exception:
            log("⚠️ Cloudflare challenge 여전히 존재 - 추가 대기...", "warning")
            await page.wait_for_timeout(10000)

        # 스크롤
        if is_openai_news:
            log("📜 OpenAI News: 최소 스크롤만 수행", "info")
            try:
                await page.evaluate("window.scrollTo({top: window.innerHeight * 2, behavior: 'smooth'})")
                await page.wait_for_timeout(2000)
                await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                await page.wait_for_timeout(1000)
            except Exception:
                pass
        else:
            log("📜 페이지 스크롤 중...", "info")
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(2000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(1000)
            except Exception:
                pass

        log("✅ 페이지 로드 완료", "success")
        await apply_search_if_configured(page, config, url, log_func=log_func)

        if is_openai_news:
            log("\n🎯 OpenAI News 감지: 쿠키 팝업 제거", "info")
            await remove_cookie_popup(page, log_func=log_func)

        # ========== Phase 0: KIPRIS 등 세션 기반 SPA 모드 체크 ==========
        if crawling_config.get('download_method') == 'spa_inline_download':
            log("\n⚡ SPA 인라인 다운로드 엔진 가동 (Phase 1, 2 생략)", "header")
            result = await execute_spa_inline_download(page, config, url, user_max_value, log_func)
            await browser.close()
            return result

        # ========== Phase 1: 링크 수집 ==========
        log(f"\n📋 페이지네이션 시작 (통합 모듈 사용)", "info")
        
        result = await handle_pagination(
            page=page,
            url=url,
            config=config,
            user_max_value=user_max_value,
            log_func=log_func,
            execution_phase='phase1' if phase1_only else 'all',
            proxy_name='stealth'
        )

        if phase1_only:
            await browser.close()
            return result

        # ========== Phase 2: 게시글 콘텐링 (병렬) ==========
        # Phase 2는 parallel_crawler 모듈을 통해 실행
        # GUI에서 호출할 때 별도로 처리

        await browser.close()
        return result
