"""
Cloudflare 챌린지 처리 및 차단 감지
"""
import random


async def handle_cloudflare_challenge(page, log_func=None):
    """
    Cloudflare "Verify you are human" 체크박스 처리

    Returns: True if challenge was handled, False if not detected
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    try:
        title = await page.title()

        is_cloudflare = False
        if any(x in title for x in ["Just a moment", "Attention Required", "Cloudflare", "Human Verification"]):
            is_cloudflare = True

        if not is_cloudflare:
            try:
                if await page.query_selector(".challenge-form") or await page.query_selector("#challenge-stage"):
                    is_cloudflare = True
            except Exception:
                pass

        if not is_cloudflare:
            return False

        log("🛡️ Cloudflare 챌린지 감지! 체크박스 확인 중...", "warning")

        selectors = [
            "div.cb-c input[type='checkbox']",
            "label.cb-lb input[type='checkbox']",
            "div.cb-c",
            "label.cb-lb",
            "div#NNbwm6",
            "#turnstile-wrapper",
            ".challenge-form input[type='checkbox']",
            "label:has-text('Verify you are human')",
            "span:has-text('Verify you are human')",
            "#challenge-stage input[type='checkbox']",
            "iframe[src*='challenges']"
        ]

        clicked = False
        await page.wait_for_timeout(2000)

        for selector in selectors:
            try:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000, state='visible')
                except Exception:
                    element = None

                if element:
                    log(f"   🎯 Cloudflare 요소 발견: {selector}", "success")
                    await page.wait_for_timeout(random.randint(500, 1500))

                    box = await element.bounding_box()
                    if box:
                        await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    else:
                        await element.click()

                    log("   👆 요소 클릭 완료! 리다이렉트 대기...", "info")
                    clicked = True

                    await page.wait_for_timeout(7000)

                    new_title = await page.title()
                    if new_title != title:
                        log("   ✅ Cloudflare 우회 성공 (페이지 전환됨)", "success")
                        return True
                    break
            except Exception:
                continue

        if clicked:
            return True

        # iframe 내부 확인 (Turnstile - Shadow DOM 대응)
        log("   🧩 iframe / Shadow DOM 탐색 중...", "info")

        for frame in page.frames:
            try:
                verify_btn = await frame.query_selector("input[type='checkbox']")
                if not verify_btn:
                    verify_btn = await frame.query_selector("label.cb-lb")
                if not verify_btn:
                    verify_btn = await frame.query_selector(".ctp-checkbox-label")

                if verify_btn:
                    log(f"   🎯 프레임({frame.url[:30]}...) 내 체크박스 발견!", "success")
                    await page.wait_for_timeout(random.randint(1000, 2000))
                    await verify_btn.click()
                    log("   👆 프레임 내 요소 클릭 완료!", "info")
                    await page.wait_for_timeout(5000)
                    return True
            except Exception:
                continue

        log("   ⚠️ 체크박스를 찾을 수 없습니다.", "warning")
        return False

    except Exception as e:
        log(f"   ⚠️ Cloudflare 처리 중 오류: {str(e)[:50]}", "warning")
        return False


async def detect_slider_or_captcha(page):
    """슬라이더/캡차 감지"""
    try:
        indicators = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            ".g-recaptcha",
            "#captcha",
            "[class*='captcha']",
            "[class*='slider']",
            ".challenge-form",
            "#challenge-stage",
        ]
        for selector in indicators:
            try:
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def is_blocked_or_failed(html_or_result):
    """페이지가 차단되었거나 실패했는지 확인"""
    if isinstance(html_or_result, dict):
        if html_or_result.get('blocked'):
            return True
        if html_or_result.get('error'):
            return True
        html = html_or_result.get('html', '') or html_or_result.get('raw_html', '')
    else:
        html = str(html_or_result) if html_or_result else ''

    if not html or len(html) < 200:
        return True

    block_indicators = [
        "Access Denied",
        "403 Forbidden",
        "Just a moment...",
        "Attention Required",
        "Enable JavaScript and cookies",
        "Please verify you are a human",
        "Rate limit exceeded",
    ]

    html_lower = html[:5000].lower() if html else ''
    for indicator in block_indicators:
        if indicator.lower() in html_lower:
            return True

    return False
