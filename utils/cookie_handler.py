"""
쿠키 팝업 자동 제거
"""


async def remove_cookie_popup(page, log_func=None):
    """
    쿠키 팝업 자동 제거
    Returns: True if removed, False if not found
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    log("🍪 쿠키 팝업 제거 시도 중...", "info")

    cookie_selectors = [
        # Facebook 특화 (우선 처리)
        '[data-cookiebanner="accept_button"]',
        'button:has-text("Allow all cookies")',
        '[data-testid="cookie-policy-manage-dialog-accept-button"]',

        # 일반적인 쿠키 팝업
        'button:has-text("Accept")',
        'button:has-text("Accept all")',
        'button:has-text("동의")',
        'button:has-text("모두 동의")',
        'button:has-text("확인")',
        'button:has-text("OK")',
        'button:has-text("Dismiss")',
        'button:has-text("Done")',
        'button:has-text("Allow")',
        'button:has-text("허용")',
        '[id*="cookie"] button',
        '[class*="cookie"] button',
        '[class*="consent"] button',
        'button[aria-label*="cookie"]',
        'button[aria-label*="Accept"]',

        # OpenAI 특화
        'button[class*="consent"]',
        'div[class*="cookie"] button',
    ]

    for selector in cookie_selectors:
        try:
            button = await page.query_selector(selector)
            if button:
                is_visible = await button.is_visible()
                if is_visible:
                    await button.click()
                    log(f"   ✅ 쿠키 팝업 제거 성공: {selector}", "success")
                    await page.wait_for_timeout(1000)
                    return True
        except Exception:
            continue

    log("   ℹ️ 쿠키 팝업을 찾지 못했거나 이미 제거됨", "info")
    return False
