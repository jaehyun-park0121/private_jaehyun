"""
JSONL/JSON 파일에서 URL을 읽어 재크롤링
"""
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from shared.config import ParallelCrawlConfig
from utils.language import get_lang_prefix, get_other_language_url


def parse_recrawl_file(file_path):
    """
    JSON/JSONL 파일에서 URL 목록 추출

    Returns:
        tuple: (urls, file_type, site_info)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    urls = []
    file_type = ""
    site_info = {}

    if content.startswith('{'):
        # JSON 파일 (크롤링 결과)
        data = json.loads(content)
        articles = data.get('crawled_articles', data.get('articles', []))
        for article in articles:
            url = article.get('url', article.get('source_url', ''))
            if url and url not in urls:
                urls.append(url)
        file_type = "JSON (크롤링 결과)"
        site_info = data.get('site', {})
    else:
        # JSONL 파일
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                url = item.get('source_url', item.get('url', ''))
                if url and url not in urls:
                    urls.append(url)
            except Exception:
                if line.startswith('http'):
                    urls.append(line)
        file_type = "JSONL"

    return urls, file_type, site_info


def build_article_links(urls, max_articles=0, dual_lang=False):
    """
    URL 목록을 article_links 형식으로 변환

    Args:
        urls: URL 목록
        max_articles: 최대 기사 수 (0=전체)
        dual_lang: 영어+한국어 동시 크롤링

    Returns:
        list: [{'url': str, 'title': str, 'article_id': int, 'lang': str}, ...]
    """
    target_urls = urls[:max_articles] if max_articles > 0 else urls
    article_links = []
    seen_urls = set()
    article_id = 0

    first_url = target_urls[0] if target_urls else ""
    is_openai = "openai.com" in first_url.lower()

    for url in target_urls:
        if url in seen_urls:
            continue

        article_id += 1
        current_lang = get_lang_prefix(url)

        article_links.append({
            'url': url,
            'title': f'Article {article_id}',
            'article_id': article_id,
            'lang': current_lang
        })
        seen_urls.add(url)

        # 영어+한국어 동시 크롤링
        if dual_lang and is_openai:
            other_url = get_other_language_url(url)
            if other_url and other_url not in seen_urls:
                other_lang = "OAI_KO" if "OAI_EN" in current_lang else "OAI_EN"
                article_links.append({
                    'url': other_url,
                    'title': f'Article {article_id}',
                    'article_id': article_id,
                    'lang': other_lang
                })
                seen_urls.add(other_url)

    return article_links


def get_site_name_from_url(url):
    """URL에서 사이트명 추출"""
    if "openai.com" in url:
        return "OpenAI_News"
    elif "research.google" in url:
        return "GOOGLE_Research"
    else:
        parsed = urlparse(url)
        return parsed.netloc.replace('.', '_').replace('www_', '')


def save_recrawl_result(all_articles, failed_articles, urls, site_name,
                        browser_mode='stealth', source_file='',
                        save_folder=None, log_func=None):
    """재크롤링 결과 저장"""
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    if not all_articles:
        return None

    base_dir = Path(save_folder) if save_folder else Path(".")
    content_output_folder = base_dir / "pagination_test_content" / site_name
    content_output_folder.mkdir(parents=True, exist_ok=True)

    formatted_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file = content_output_folder / f"{site_name.lower().replace('_', '-')}-{formatted_timestamp}.json"

    first_url = urls[0] if urls else ""

    content_data = {
        'site': {
            'name': site_name.replace('_', ' '),
            'url': first_url
        },
        'test_info': {
            'timestamp': formatted_timestamp,
            'test_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'method_used': f'recrawl_{browser_mode}',
            'source_file': source_file,
            'total_articles_crawled': len(all_articles),
            'total_articles_failed': len(failed_articles)
        },
        'crawled_articles': all_articles
    }

    if failed_articles:
        failed_urls = [url for url in urls if not any(a.get('url') == url for a in all_articles)]
        content_data['failed_urls'] = failed_urls

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(content_data, f, ensure_ascii=False, indent=2)

    log(f"\n{'='*60}", "success")
    log(f"✅ 재크롤링 JSON 저장 완료", "success")
    log(f"   📁 파일: {output_file}", "success")
    log(f"   📊 총 {len(all_articles)}개 게시글 포함", "success")
    if failed_articles:
        log(f"   ⚠️ 실패: {len(failed_articles)}개", "warning")
    log(f"{'='*60}\n", "success")

    return str(output_file)
