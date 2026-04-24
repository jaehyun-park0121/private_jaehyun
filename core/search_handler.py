"""
사이트 내 검색 기능 (YAML search 설정 기반)
"""
from urllib.parse import quote_plus


def normalize_search_config(config):
    """YAML의 search 설정을 정규화"""
    search_cfg = config.get("search", {}) if isinstance(config, dict) else {}
    if not isinstance(search_cfg, dict):
        return {"enabled": False}

    enabled = bool(search_cfg.get("enabled", False))
    query = str(search_cfg.get("query", search_cfg.get("keyword", ""))).strip()
    mode = str(search_cfg.get("mode", "form")).strip().lower()
    url_template = str(search_cfg.get("url_template", "")).strip()
    post_url = str(search_cfg.get("post_url", "")).strip()
    post_payload = str(search_cfg.get("post_payload", "")).strip()
    callback_fn = str(search_cfg.get("callback_fn", "")).strip()
    post_headers = search_cfg.get("post_headers", {})
    if not isinstance(post_headers, dict):
        post_headers = {}

    input_selectors = search_cfg.get("input_selectors", [])
    if isinstance(input_selectors, str):
        input_selectors = [input_selectors]
    if not input_selectors:
        input_selectors = [
            "input[type='search']",
            "input[name='q']",
            "input[name='query']",
            "input[placeholder*='search' i]",
        ]

    submit_selectors = search_cfg.get("submit_selectors", [])
    if isinstance(submit_selectors, str):
        submit_selectors = [submit_selectors]

    wait_after_ms = int(search_cfg.get("wait_after_ms", 2500))

    return {
        "enabled": enabled,
        "query": query,
        "mode": mode,
        "url_template": url_template,
        "post_url": post_url,
        "post_payload": post_payload,
        "callback_fn": callback_fn,
        "post_headers": post_headers,
        "input_selectors": input_selectors,
        "submit_selectors": submit_selectors,
        "wait_after_ms": wait_after_ms,
    }


async def execute_custom_actions(page, actions, log_func=None):
    """YAML의 search_actions (커스텀 자동화 액션) 실행"""
    if not actions:
        return
    def log(msg, level="info"):
        if log_func: log_func(msg, level)

    log(f"🔎 사용자 정의 액션(search_actions) {len(actions)}개 실행 중...", "info")
    for action in actions:
        try:
            a_type = action.get("type")
            sel = action.get("selector")
            if a_type == "fill":
                await page.fill(sel, str(action.get("value", "")))
            elif a_type == "press":
                await page.press(sel, str(action.get("key", "Enter")))
            elif a_type == "click":
                await page.click(sel)
            elif a_type == "wait_for_selector":
                await page.wait_for_selector(sel, state="visible", timeout=30000)
            elif a_type == "wait_for_timeout":
                await page.wait_for_timeout(int(action.get("ms", 2000)))
        except Exception as e:
            log(f"⚠️ search_action {a_type} 실패 ({sel}): {e}", "warning")

async def apply_search_if_configured(page, config, base_url, log_func=None):
    """설정된 search가 있으면 Playwright로 검색을 먼저 실행"""
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)

    # 1. 커스텀 액션 우선 실행 (kipris 모델 등)
    crawling_cfg = config.get("crawling") or {}
    search_actions = crawling_cfg.get("search_actions", [])
    if search_actions:
        await execute_custom_actions(page, search_actions, log_func=log_func)

    # 2. 전통적인 Search 객체 체크
    cfg = normalize_search_config(config)
    if not cfg["enabled"]:
        return False

    if not cfg["query"]:
        log("⚠️ search.enabled=true 이지만 query가 비어있어 검색을 건너뜁니다.", "warning")
        return False

    query = cfg["query"]

    # POST 모드
    if cfg["mode"] == "post":
        if not cfg["post_url"] or not cfg["post_payload"]:
            log("⚠️ search.mode=post 이지만 post_url/post_payload가 없어 검색을 건너뜁니다.", "warning")
            return False
        try:
            payload = (
                cfg["post_payload"]
                .replace("{query}", quote_plus(query))
                .replace("{query_raw}", query)
                .replace("{url}", quote_plus(base_url))
                .replace("{url_raw}", base_url)
            )
            log(f"🔎 POST 검색 호출: {cfg['post_url']}", "info")
            result = await page.evaluate(
                """
                async ({postUrl, payload, headers, callbackFnName}) => {
                    const headerObj = Object.assign(
                        {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                        headers || {}
                    );
                    const response = await fetch(postUrl, {
                        method: "POST",
                        headers: headerObj,
                        body: payload,
                        credentials: "include",
                    });
                    const text = await response.text();
                    let parsed = null;
                    try { parsed = JSON.parse(text); } catch (e) {}
                    if (callbackFnName && typeof window[callbackFnName] === "function" && parsed) {
                        try { window[callbackFnName](parsed); } catch (e) {}
                    }
                    return {
                        ok: response.ok,
                        status: response.status,
                        hasJson: !!parsed,
                        textPreview: text.slice(0, 500),
                    };
                }
                """,
                {
                    "postUrl": cfg["post_url"],
                    "payload": payload,
                    "headers": cfg["post_headers"],
                    "callbackFnName": cfg["callback_fn"],
                },
            )
            log(
                f"   ✅ POST 응답: status={result.get('status')} json={result.get('hasJson')}",
                "success" if result.get("ok") else "warning",
            )
            await page.wait_for_timeout(cfg["wait_after_ms"])
            return bool(result.get("ok"))
        except Exception as e:
            log(f"⚠️ POST 검색 호출 실패: {e}", "warning")
            return False

    # URL 모드
    if cfg["mode"] == "url":
        if not cfg["url_template"]:
            log("⚠️ search.mode=url 이지만 url_template이 없어 검색을 건너뜁니다.", "warning")
            return False
        try:
            search_url = cfg["url_template"].format(
                query=quote_plus(query),
                query_raw=query,
                url=base_url,
            )
            log(f"🔎 검색 URL 이동: {search_url}", "info")
            await page.goto(search_url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(cfg["wait_after_ms"])
            return True
        except Exception as e:
            log(f"⚠️ 검색 URL 이동 실패: {e}", "warning")
            return False

    # Form 모드 (기본)
    input_handle = None
    input_selector_used = None
    for sel in cfg["input_selectors"]:
        try:
            h = await page.query_selector(sel)
            if h and await h.is_visible():
                input_handle = h
                input_selector_used = sel
                break
        except Exception:
            continue

    if not input_handle:
        log("⚠️ 검색 입력창을 찾지 못해 검색을 건너뜁니다.", "warning")
        return False

    try:
        log(f"🔎 검색어 입력: '{query}' (selector: {input_selector_used})", "info")
        await input_handle.click()
        await input_handle.fill("")
        await input_handle.fill(query)
    except Exception as e:
        log(f"⚠️ 검색어 입력 실패: {e}", "warning")
        return False

    submitted = False
    for sel in cfg["submit_selectors"]:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                submitted = True
                log(f"   ✅ 검색 버튼 클릭: {sel}", "success")
                break
        except Exception:
            continue

    if not submitted:
        try:
            await input_handle.press("Enter")
            submitted = True
            log("   ✅ Enter로 검색 제출", "success")
        except Exception as e:
            log(f"⚠️ 검색 제출 실패: {e}", "warning")
            return False

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    await page.wait_for_timeout(cfg["wait_after_ms"])
    return True
