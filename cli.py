import argparse
import asyncio
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (패키지 import 지원)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

# 현재 디렉토리 및 상위(원본) .env 동시 지원
load_dotenv()
original_env = os.path.join(PROJECT_ROOT, '..', 'Crawling Code', '.env')
if os.path.exists(original_env):
    load_dotenv(original_env)

from shared.config import get_config_loader, ParallelCrawlConfig
from core.stealth_crawler import test_with_stealth
from core.parallel_crawler import crawl_articles_parallel
from core.result_saver import save_phase2_result
from datetime import datetime

async def run_pipeline(url, max_pages, max_concurrent, mode='stealth', phase1_only=False):
    config_loader = get_config_loader()
    config = config_loader.get_config_by_url(url)
    
    if not config:
        print(f"❌ '{url}' 에 대한 설정을 찾을 수 없습니다. (site_configs/*.yaml 확인)")
        return
        
    site_name = config.get('site', {}).get('name', url)
    print(f"🚀 크롤링 파이프라인 시작: {site_name}")
    print(f"   모드: {mode}, 최대 스크롤/수집 제한: {max_pages}, 병렬 워커: {max_concurrent}")
    
    def log_callback(msg, level="info"):
        prefix = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "header": "🏁"}.get(level, "💬")
        print(f"{prefix} {msg}")

    try:
        # Phase 1: 링크(게시글 URL) 수집
        log_callback("Phase 1: 게시글 링크 수집 시작", "header")
        result = await test_with_stealth(
            url=url, 
            config=config, 
            user_max_value=max_pages,
            phase1_only=True,
            log_func=log_callback
        )
        
        if not result or not result.get('success'):
            log_callback("Phase 1 구조화 및 수집 실패", "error")
            return
            
        links = result.get('all_links', [])
        log_callback(f"Phase 1 성공: {len(links)}개 링크 수집 완료", "success")
        
        if phase1_only or not links:
            log_callback("Phase 1 완료! (Phase 2 건너뜀)", "info")
            return
            
        # Phase 2: 병렬 본문 수집
        log_callback("Phase 2: 병렬 수집 시작", "header")
        parallel_config = ParallelCrawlConfig(
            enabled=True,
            max_concurrent=max_concurrent,
            batch_size=50
        )
        
        article_links = [{'url': l['url'], 'title': l['title'], 'article_id': i+1} for i, l in enumerate(links)]
        
        crawl_results = await crawl_articles_parallel(
            article_links=article_links,
            config=config,
            parallel_config=parallel_config,
            browser_mode=mode,
            log_func=log_callback
        )
        
        # 파일로 저장 (result_saver)
        crawled = crawl_results.get('crawled_articles', [])
        if crawled:
            log_callback(f"결과 저장 중... (총 {len(crawled)}건)", "info")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            save_phase2_result(
                crawled_articles=crawled, 
                failed_articles=crawl_results.get('failed_articles', []),
                timestamp=timestamp,
                site_name=site_name, 
                log_func=log_callback
            )
        
        log_callback("전체 파이프라인(CLI) 실행 완료!", "success")
        
    except Exception as e:
        print(f"\n❌ 파이프라인 하네스 에러: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="하네스 크롤링 파이프라인 CLI")
    parser.add_argument("--url", type=str, required=True, help="타겟 사이트 URL (필수)")
    parser.add_argument("--max-pages", type=int, default=3, help="페이지네이션/클릭 제한 횟수 (기본 3)")
    parser.add_argument("--concurrent", type=int, default=5, help="동시 수집 제한 수 (기본 5)")
    parser.add_argument("--mode", type=str, default='stealth', help="실행 모드 (예: stealth(무료), unlocker(브라이트데이터 유료) 등)")
    parser.add_argument("--phase1-only", action="store_true", help="게시글 url 수집만 하고 본문 크롤링은 스킵")
    
    args = parser.parse_args()
    
    asyncio.run(run_pipeline(
        url=args.url,
        max_pages=args.max_pages,
        max_concurrent=args.concurrent,
        mode=args.mode,
        phase1_only=args.phase1_only
    ))

if __name__ == "__main__":
    main()
