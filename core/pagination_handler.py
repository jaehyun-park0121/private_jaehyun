import random
import re
from urllib.parse import urljoin

def decode_redirect_url(url):
    return url

async def handle_pagination(
    page, url, config, user_max_value=20, log_func=None, execution_phase='all', proxy_name='none'
):
    """
    다양한 타입의 페이지네이션 로직을 통합 관리하는 핸들러.
    
    Args:
        page: Playwright Page 객체
        url: 초기 진입 URL
        config: 사이트의 YAML 설정
        user_max_value: GUI에서 입력한 최대 수집 또는 스크롤/클릭 횟수
        log_func: 로그를 출력할 함수 콜백
        execution_phase: 'phase1' 인지 'all' 인지 구분하여 조기 종료 판단 (반복 최적화용)
        proxy_name: 로깅 용도 (stealth, unlocker 등)
        
    Returns:
        dict: {
            'success': bool,
            'clicks': int,
            'initial_count': int,
            'final_count': int,
            'new_articles': int,
            'all_links': list[dict],
            'proxy_used': str,
            'method_used': str
        }
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)
            
    pagination = config.get('pagination', {})
    ptype = pagination.get('type', 'button')
    clicks = 0
    all_links = []
    
    # 게시글 셀렉터
    article_links_config = config.get('content', {}).get('article_links', {})
    article_selectors = article_links_config.get('selectors', ['a'])
    article_selector = article_selectors[0] if article_selectors else 'a'
    
    # URL 필터
    url_filter = article_links_config.get('url_filter', {})
    include_patterns = url_filter.get('include_patterns', [])
    exclude_patterns = url_filter.get('exclude_patterns', [])
    
    def passes_url_filter(test_url):
        for pattern in exclude_patterns:
            try:
                if re.search(pattern, test_url): return False
            except: pass
        if include_patterns:
            for pattern in include_patterns:
                try:
                    if re.search(pattern, test_url): return True
                except: pass
            return False
        return True

    try:
        initial_articles = await page.locator(article_selector).all()
        seen_urls = set()
        for elem in initial_articles:
            try:
                href = await elem.get_attribute('href')
                if href:
                    href = decode_redirect_url(href)
                    full_url = href if href.startswith('http') else urljoin(url, href)
                    if passes_url_filter(full_url) and full_url not in seen_urls:
                        title = await elem.inner_text()
                        all_links.append({'url': full_url, 'title': title.strip()[:200]})
                        seen_urls.add(full_url)
            except:
                pass
        
        initial_count = len(all_links)
        log(f"📊 초기 링크 수: {initial_count}개", "info")
    except Exception as e:
        log(f"⚠️ 초기 링크 수집 실패: {e}", "warning")
        initial_count = 0
        seen_urls = set()
        
    remove_duplicates = pagination.get('remove_duplicates', True)

    # 1. 페이지네이션 없음
    if not pagination.get('enabled', True) or ptype == 'none':
        log("ℹ️ 페이지네이션 없음 - 현재 페이지 게시글만 수집", "info")
        
    # 2. 버튼 (Button)
    elif ptype == 'button':
        button_config = pagination.get('button', {})
        selectors = button_config.get('selectors', [])
        wait_time = button_config.get('wait_after_click', 3000)
        
        log(f"🔘 버튼 클릭 페이지네이션 시작 (최대 {user_max_value}회)", "info")
        
        for click_num in range(user_max_value):
            button_found = False
            target_button = None
            
            for selector in selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.count() > 0 and await btn.is_visible():
                        target_button = btn
                        button_found = True
                        break
                except: continue
                
            if not button_found:
                # 스크롤해서 찾기 시도
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                for selector in selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.count() > 0 and await btn.is_visible():
                            target_button = btn
                            button_found = True
                            break
                    except: continue

            if not button_found:
                log(f"⏹️ 더 이상 버튼을 찾을 수 없음 (클릭 {clicks}회)", "info")
                break
                
            try:
                await target_button.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                await target_button.click(force=True)
                clicks += 1
                await page.wait_for_timeout(wait_time)
                
                # 네트워크 대기
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except: pass
                
                # 새 링크 수집
                new_articles = await page.locator(article_selector).all()
                added = 0
                for elem in new_articles:
                    try:
                        href = await elem.get_attribute('href')
                        if href:
                            href = decode_redirect_url(href)
                            full_url = href if href.startswith('http') else urljoin(url, href)
                            if passes_url_filter(full_url) and (not remove_duplicates or full_url not in seen_urls):
                                title = await elem.inner_text()
                                all_links.append({'url': full_url, 'title': title.strip()[:200]})
                                if remove_duplicates:
                                    seen_urls.add(full_url)
                                added += 1
                    except: pass
                    
                log(f"✅ 클릭 {clicks}회 완료: 새 링크 +{added}개 (총 {len(all_links)}개)", "success")
                if added == 0:
                    # 빈 페이지 대기 로직 재시도 등
                    log("📌 더 이상 새 게시글이 나타나지 않음", "info")
                    break
                    
            except Exception as e:
                log(f"⚠️ 클릭 실패: {str(e)[:50]}", "warning")
                break
                
    # 3. 자바스크립트 API (JavaScript)
    elif ptype == 'javascript':
        js_config = pagination.get('javascript', {})
        mode = js_config.get('mode', 'api_fetch')
        
        log(f"🔧 JavaScript 페이지네이션 시작 (모드: {mode})", "info")
        
        if mode == 'batchexecute' and "cloud.google.com/blog" in url:
            batch_config = js_config.get('batchexecute', {})
            rpc_id = batch_config.get('rpc_id', 'SQC9mf')
            articles_per_page = batch_config.get('articles_per_page', 10)
            blog_type = batch_config.get('blog_type', 'cloudblog')
            language = batch_config.get('language', 'en')
            content_type = batch_config.get('content_type', 'article')

            log("\n🔧 Google Cloud Blog: batchexecute API 사용", "info")
            try:
                google_result = await page.evaluate(rf"""
                async () => {{
                    const allLinks = new Set();
                    const articlesPerPage = {articles_per_page};
                    let loadedIds = [];
                    for (let pageNum = 1; pageNum <= 100; pageNum++) {{
                        const rpcData = JSON.stringify(["{blog_type}","{language}",null,null,articlesPerPage,String(pageNum),"{content_type}",[""],loadedIds.slice(-3)]);
                        const body = `f.req=${{encodeURIComponent(JSON.stringify([[["{rpc_id}", rpcData, null, "generic"]]]))}}` + '&';
                        const res = await fetch(`https://cloud.google.com/blog/_/TransformBlogUi/data/batchexecute?rpcids={rpc_id}`, {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                            body: body
                        }});
                        if (!res.ok) break;
                        const text = await res.text();
                        const matches = text.match(/https:\/\/cloud\.google\.com\/blog\/(topics|products)\/[^"\\\\]+/g) || [];
                        if (matches.length === 0) break;
                        matches.forEach(m => allLinks.add(m));
                    }}
                    return Object.fromEntries(Array.from(allLinks).map(a => [a, a.split('/').pop()]));
                }}
                """)
                all_links = [{'url': k, 'title': v} for k, v in google_result.items()]
                log(f"✅ Google API 완료: {len(all_links)}개 수집", "success")
            except Exception as e:
                log(f"⚠️ Google API 실패: {e}", "error")

        elif mode == 'api_fetch' and "alibabacloud.com/blog" in url:
            log("\n🔧 Alibaba Cloud: API Fetch 로직 실행", "info")
            try:
                alibaba_result = await page.evaluate(rf"""
                async () => {{
                    const allLinks = new Set();
                    for (let pageNum = 1; pageNum <= {user_max_value}; pageNum++) {{
                        const res = await fetch(`https://www.alibabacloud.com/blog/latest/${{pageNum}}`);
                        if(!res.ok) break;
                        const text = await res.text();
                        const doc = new DOMParser().parseFromString(text, "text/html");
                        const links = doc.querySelectorAll('a[href*="/blog/"]');
                        if(!links.length) break;
                        links.forEach(l => allLinks.add(l.href));
                    }}
                    return Array.from(allLinks);
                }}
                """)
                for a_url in alibaba_result:
                    if passes_url_filter(a_url):
                        all_links.append({'url': a_url, 'title': a_url.split('/')[-1]})
                log(f"✅ Alibaba API 롼료: {len(all_links)}개 수집", "success")
            except Exception as e:
                log(f"⚠️ Alibaba API 실패: {e}", "error")

        elif mode == 'url_param' and "openai.com" in url:
            log("\n🔧 OpenAI News: url parameters API Fetch 실행", "info")
            try:
                openai_result = await page.evaluate(rf"""
                async () => {{
                    const allLinks = new Set();
                    for (let pageNum = 1; pageNum <= {user_max_value}; pageNum++) {{
                        const res = await fetch(`https://openai.com/ko-KR/news/?display=list&page=${{pageNum}}`);
                        if(!res.ok) break;
                        const text = await res.text();
                        const doc = new DOMParser().parseFromString(text, "text/html");
                        const links = doc.querySelectorAll("a[href^='/index/'], a[href*='/index/']");
                        if(!links.length) break;
                        links.forEach(l => {{
                            const href = l.getAttribute('href');
                            const full = href.startsWith('http') ? href : `https://openai.com${{href}}`;
                            allLinks.add(full);
                        }});
                    }}
                    return Array.from(allLinks);
                }}
                """)
                for a_url in openai_result:
                    if passes_url_filter(a_url):
                        all_links.append({'url': a_url, 'title': a_url.split('/')[-2]})
                log(f"✅ OpenAI API 완료: {len(all_links)}개 수집", "success")
            except Exception as e:
                log(f"⚠️ OpenAI API 실패: {e}", "error")

        
    # 4. 스크롤 (Scroll)
    elif ptype == 'scroll':
        scroll_config = pagination.get('scroll', {})
        wait_time = scroll_config.get('wait_after_scroll', 2000)
        
        log(f"📜 무한 스크롤 시작 (최대 {user_max_value}회)", "info")
        for scroll_iter in range(user_max_value):
            height_before = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(wait_time)
            
            height_after = await page.evaluate("document.body.scrollHeight")
            new_articles = await page.locator(article_selector).all()
            added = 0
            for elem in new_articles:
                try:
                    href = await elem.get_attribute('href')
                    if href:
                        href = decode_redirect_url(href)
                        full_url = href if href.startswith('http') else urljoin(url, href)
                        if passes_url_filter(full_url) and full_url not in seen_urls:
                            title = await elem.inner_text()
                            all_links.append({'url': full_url, 'title': title.strip()[:200]})
                            if remove_duplicates:
                                seen_urls.add(full_url)
                            added += 1
                except: pass
                
            log(f"📜 스크롤 {scroll_iter+1}회: +{added}개 (총 {len(all_links)}개)", "info")
            if height_after == height_before and added == 0:
                log("⏹️ 더 이상 추가 콘텐츠 없음", "info")
                break
                
    # 5. 하이브리드 (Scroll + Button)
    elif ptype == 'scroll_button':
        sb_config = pagination.get('scroll_button', {})
        wait_after_scroll = sb_config.get('wait_after_scroll', 2000)
        button_selectors = sb_config.get('button_selectors', [])
        if not button_selectors:
            button_selectors = [sb_config.get('button_selector', "button:has-text('Load More')")]
            
        log(f"🔄 하이브리드 페이지네이션 시작", "info")
        for scroll_num in range(1, user_max_value * 10 + 1):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(wait_after_scroll)
            
            # 버튼 탐색 및 클릭
            clicked = False
            for selector in button_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)
                        await btn.click(force=True)
                        clicks += 1
                        clicked = True
                        break
                except: pass
                
            await page.wait_for_timeout(2000)
            
            new_articles = await page.locator(article_selector).all()
            added = 0
            for elem in new_articles:
                try:
                    href = await elem.get_attribute('href')
                    if href:
                        href = decode_redirect_url(href)
                        full_url = href if href.startswith('http') else urljoin(url, href)
                        if passes_url_filter(full_url) and full_url not in seen_urls:
                            title = await elem.inner_text()
                            all_links.append({'url': full_url, 'title': title.strip()[:200]})
                            if remove_duplicates:
                                seen_urls.add(full_url)
                            added += 1
                except: pass
                
            log(f"📜 하이브리드 {scroll_num}회: +{added}개 (총 {len(all_links)}개, 클릭 {clicks}회)", "info")
            if not clicked and added == 0:
                break
        
    # 6. 링크 (Link)
    elif ptype == 'link':
        link_config = pagination.get('link', {})
        url_template = link_config.get('url_template', None)
        use_template = link_config.get('use_template', False)
        start_page = link_config.get('start_page', 1)
        wait_time = link_config.get('wait_after_click', 3000)
        
        log(f"🔗 페이지 이동 페이지네이션 시작 ({user_max_value}회 제한)", "info")
        if use_template and url_template:
            for page_num in range(start_page + 1, start_page + user_max_value):
                try:
                    if "{url}" in url_template:
                        next_url = url_template.format(url=url, page=page_num)
                    else:
                        next_url = url_template.format(page=page_num)
                        
                    await page.goto(next_url, wait_until='networkidle', timeout=60000)
                    clicks += 1
                    await page.wait_for_timeout(wait_time)
                    
                    new_articles = await page.locator(article_selector).all()
                    added = 0
                    for elem in new_articles:
                        try:
                            href = await elem.get_attribute('href')
                            if href:
                                href = decode_redirect_url(href)
                                full_url = href if href.startswith('http') else urljoin(url, href)
                                if passes_url_filter(full_url) and full_url not in seen_urls:
                                    title = await elem.inner_text()
                                    all_links.append({'url': full_url, 'title': title.strip()[:200]})
                                    if remove_duplicates:
                                        seen_urls.add(full_url)
                                    added += 1
                        except: pass
                    
                    log(f"🔗 템플릿 이동 P.{page_num}: +{added}개 (총 {len(all_links)}개)", "info")
                    if added == 0: break
                except Exception as e:
                    log(f"⚠️ 템플릿 로딩 실패: {e}", "warning")
                    break

    return {
        'success': True,
        'clicks': clicks,
        'initial_count': initial_count,
        'final_count': len(all_links),
        'new_articles': len(all_links) - initial_count,
        'all_links': all_links,
        'proxy_used': proxy_name,
        'method_used': ptype
    }
