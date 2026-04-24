"""
카테고리별 크롤링 (YAML categories 설정 기반)
"""
from core.stealth_crawler import test_with_stealth
from core.unlocker_crawler import test_with_unlocker


async def test_with_categories(url, config, browser_mode='stealth',
                               user_max_value=20, proxy_manager=None,
                               log_func=None):
    """
    카테고리별 페이지네이션 크롤링

    Args:
        url: 기본 URL
        config: YAML 설정 (categories 포함)
        browser_mode: 크롤링 모드
        user_max_value: 최대 클릭/페이지 수
        proxy_manager: ProxyManager 인스턴스
        log_func: 로그 함수

    Returns:
        dict: 카테고리별 결과
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    categories = config.get('categories', [])
    if not categories:
        log("⚠️ 카테고리 설정이 없습니다.", "warning")
        return {'success': False, 'error': 'No categories configured'}

    log(f"\n{'='*60}", "header")
    log(f"📂 카테고리별 크롤링 시작 ({len(categories)}개)", "header")
    log(f"{'='*60}", "header")

    category_results = []
    total_links = 0
    total_clicks = 0
    success_categories = 0
    failed_categories = 0

    for idx, category in enumerate(categories):
        cat_name = category.get('name', f'Category {idx+1}')
        cat_slug = category.get('slug', f'cat{idx+1}')
        cat_url = category.get('url', '')

        if not cat_url:
            # URL 패턴으로 생성
            url_pattern = category.get('url_pattern', '')
            if url_pattern:
                cat_url = url_pattern
            else:
                cat_url = f"{url.rstrip('/')}/{cat_slug}"

        log(f"\n📁 [{idx+1}/{len(categories)}] {cat_name}", "header")
        log(f"   URL: {cat_url}", "info")

        try:
            # 카테고리별 config 오버라이드
            cat_config = dict(config)
            if 'pagination' in category:
                cat_config['pagination'] = category['pagination']

            # 모드에 따라 크롤링 실행
            if browser_mode in ['unlocker'] and proxy_manager and proxy_manager.proxy_unlocker:
                cat_result = await test_with_unlocker(
                    url=cat_url,
                    config=cat_config,
                    proxy_url=proxy_manager.proxy_unlocker,
                    user_max_value=user_max_value,
                    phase1_only=True,
                    log_func=log_func
                )
            else:
                cat_result = await test_with_stealth(
                    url=cat_url,
                    config=cat_config,
                    user_max_value=user_max_value,
                    phase1_only=True,
                    category_slug=cat_slug,
                    log_func=log_func
                )

            if cat_result.get('success'):
                cat_links = cat_result.get('all_links', [])
                category_results.append({
                    'category_name': cat_name,
                    'category_slug': cat_slug,
                    'category_url': cat_url,
                    'clicks': cat_result.get('clicks', 0),
                    'all_links': cat_links,
                    'success': True
                })
                total_links += len(cat_links)
                total_clicks += cat_result.get('clicks', 0)
                success_categories += 1

                log(f"   ✅ {cat_name}: {len(cat_links)}개 링크 수집", "success")
            else:
                failed_categories += 1
                category_results.append({
                    'category_name': cat_name,
                    'category_slug': cat_slug,
                    'category_url': cat_url,
                    'success': False,
                    'error': cat_result.get('error', 'Unknown')
                })
                log(f"   ❌ {cat_name}: 실패", "error")

        except Exception as e:
            failed_categories += 1
            log(f"   ❌ {cat_name} 예외: {str(e)[:50]}", "error")

    # 전체 링크 통합
    all_links = []
    for cr in category_results:
        if cr.get('success'):
            all_links.extend(cr.get('all_links', []))

    return {
        'success': True,
        'clicks': total_clicks,
        'initial_count': 0,
        'final_count': total_links,
        'new_articles': total_links,
        'all_links': all_links,
        'category_results': category_results,
        'total_categories': len(categories),
        'success_categories': success_categories,
        'failed_categories': failed_categories,
        'method_used': f'categories_{browser_mode}'
    }
