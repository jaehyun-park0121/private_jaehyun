"""
Playwright 페이지에서 미디어 요소 추출 (이미지, 비디오, 오디오)
- _recrawl_stealth와 _recrawl_unlocker에서 중복되던 ~80줄을 통합
"""
from urllib.parse import urljoin


async def extract_media_from_page(page, article_url, max_imgs=50, log_func=None):
    """
    Playwright 페이지에서 모든 미디어 요소 추출 (통합)

    Args:
        page: Playwright page object
        article_url: 현재 페이지 URL (상대경로 resolve용)
        max_imgs: 최대 이미지 수
        log_func: 로그 함수

    Returns:
        tuple: (images, videos, audios, media_stats)
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    images = []
    videos = []
    audios = []
    media_stats = {
        'total_iframes': 0,
        'video_iframes': 0,
        'video_tags': 0,
        'audio_tags': 0,
        'yt_data_attrs': 0
    }

    # 1. 이미지 추출
    try:
        img_elems = await page.locator('img').all()
        seen_img_urls = set()
        for img in img_elems[:max_imgs]:
            try:
                src = await img.get_attribute('src') or await img.get_attribute('data-src')
                if src and src not in seen_img_urls and not src.startswith('data:'):
                    absolute_url = src if src.startswith('http') else urljoin(article_url, src)
                    seen_img_urls.add(absolute_url)
                    images.append({
                        'idx': len(images),
                        'image_url': absolute_url,
                        'alt': await img.get_attribute('alt') or ''
                    })
            except Exception:
                continue
    except Exception:
        pass

    # 2. iframe 비디오 추출
    video_platforms = ['youtube', 'vimeo', 'youtu.be', 'dailymotion', 'wistia', 'brightcove', 'player.']
    try:
        iframes = await page.locator('iframe').all()
        media_stats['total_iframes'] = len(iframes)
        for iframe in iframes[:30]:
            try:
                iframe_src = await iframe.get_attribute('src')
                if iframe_src:
                    absolute_iframe = iframe_src if iframe_src.startswith('http') else urljoin(article_url, iframe_src)
                    if any(vp in absolute_iframe.lower() for vp in video_platforms):
                        media_stats['video_iframes'] += 1
                        videos.append({
                            'idx': len(videos),
                            'video_url': absolute_iframe,
                            'type': 'iframe',
                            'title': await iframe.get_attribute('title') or ''
                        })
            except Exception:
                continue
    except Exception:
        pass

    # 3. video 태그 추출
    try:
        video_elems = await page.locator('video').all()
        for vid in video_elems[:20]:
            try:
                # currentSrc 확인 (JS 속성) - 동적 로딩된 비디오용
                vid_src = await vid.evaluate("node => node.currentSrc")

                # src 속성 확인 (HTML 속성) - fallback
                if not vid_src:
                    vid_src = await vid.get_attribute('src')

                # source 태그 확인
                if not vid_src:
                    try:
                        source_elem = vid.locator('source').first
                        vid_src = await source_elem.get_attribute('src')
                    except Exception:
                        pass

                if vid_src:
                    if vid_src.startswith('blob:'):
                        continue

                    absolute_vid = vid_src if vid_src.startswith('http') else urljoin(article_url, vid_src)
                    media_stats['video_tags'] += 1
                    videos.append({
                        'idx': len(videos),
                        'video_url': absolute_vid,
                        'type': 'video_tag',
                        'title': ''
                    })
            except Exception:
                continue
    except Exception:
        pass

    # 4. YouTube 데이터 속성 (data-glue-yt-video-vid)
    try:
        yt_data_elems = await page.locator('[data-glue-yt-video-vid]').all()
        media_stats['yt_data_attrs'] = len(yt_data_elems)
        for yt_elem in yt_data_elems:
            try:
                vid_id = await yt_elem.get_attribute('data-glue-yt-video-vid')
                if vid_id:
                    yt_url = f"https://www.youtube.com/embed/{vid_id}"
                    if not any(yt_url in v.get('video_url', '') for v in videos):
                        videos.append({
                            'idx': len(videos),
                            'video_url': yt_url,
                            'type': 'yt_data_attr',
                            'video_id': vid_id
                        })
            except Exception:
                continue
    except Exception:
        pass

    # 5. audio 태그 추출
    try:
        audio_elems = await page.locator('audio').all()
        for aud in audio_elems[:20]:
            try:
                aud_src = await aud.get_attribute('src')
                if not aud_src:
                    try:
                        source_elem = aud.locator('source').first
                        aud_src = await source_elem.get_attribute('src')
                    except Exception:
                        pass
                if aud_src:
                    absolute_aud = aud_src if aud_src.startswith('http') else urljoin(article_url, aud_src)
                    media_stats['audio_tags'] += 1
                    audios.append({
                        'idx': len(audios),
                        'audio_url': absolute_aud,
                        'title': ''
                    })
            except Exception:
                continue
    except Exception:
        pass

    log(
        f"      📊 미디어: 🖼️{len(images)} 📹{len(videos)} 🔊{len(audios)} "
        f"(iframe:{media_stats['total_iframes']}, YT_DATA:{media_stats['yt_data_attrs']})",
        "info"
    )

    if media_stats['yt_data_attrs'] > 0 and media_stats['video_iframes'] < media_stats['yt_data_attrs']:
        log(
            f"      ⚠️ YouTube iframe 누락 가능! "
            f"(YT_DATA:{media_stats['yt_data_attrs']} > iframe:{media_stats['video_iframes']})",
            "warning"
        )

    return images, videos, audios, media_stats
