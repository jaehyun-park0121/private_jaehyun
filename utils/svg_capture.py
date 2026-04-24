"""
SVG 요소 캡처 (vega-embed 차트)
"""
import os
from pathlib import Path
from datetime import datetime


async def capture_svg_elements(page, site_name, output_folder="screenshots",
                               log_func=None, prefix="OAI_EN", article_id=None):
    """
    페이지의 SVG 요소들을 캡처하여 저장 (vega-embed 차트만)

    Args:
        page: Playwright page object
        site_name: 사이트명 (하위 호환용)
        output_folder: 저장 폴더
        log_func: 로그 함수
        prefix: 파일명 접두사 (예: "OAI_EN", "OAI_KO")
        article_id: 게시글 ID (예: 1, 2, 3... → 000001, 000002, 000003...)
    Returns: dict with capture results
    """
    def log(msg, level="info"):
        if log_func:
            log_func(msg, level)
        elif os.getenv("DEBUG_OVERLAY") == "1":
            print(msg)

    # 오버레이 제거 헬퍼
    async def _remove_overlays():
        try:
            await page.evaluate("""() => {
                const styleId = "overlay-guard-style";
                if (!document.getElementById(styleId)) {
                    const style = document.createElement("style");
                    style.id = styleId;
                    style.textContent = `
                        [class*="chatgpt"], [id*="chatgpt"],
                        button[aria-label*="ChatGPT"], [aria-label*="ChatGPT"] {
                            display: none !important;
                            visibility: hidden !important;
                        }
                    `;
                    (document.head || document.documentElement).appendChild(style);
                }

                if (window._overlayGuardInstalled) return;
                window._overlayGuardInstalled = true;

                function nuke(root) {
                    let count = 0;
                    const xpath = "//*[contains(text(), 'ChatGPT') or contains(text(), 'Ask ChatGPT') or contains(text(), '묻기')]";
                    try {
                        const result = document.evaluate(xpath, root, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                        for (let i = 0; i < result.snapshotLength; i++) {
                            let el = result.snapshotItem(i);
                            if (el.textContent.length > 200) continue;
                            let current = el;
                            let removed = false;
                            const chatForm = el.closest('form');
                            if (chatForm) {
                                const hasChatInput = chatForm.querySelector('input[placeholder*="ChatGPT"], input[aria-label*="ChatGPT"]');
                                if (hasChatInput) {
                                    chatForm.remove();
                                    removed = true;
                                    count++;
                                }
                            }
                            for (let k = 0; k < 6; k++) {
                                if (!current || current === document.body) break;
                                const style = window.getComputedStyle(current);
                                if (style.position === 'fixed' || style.position === 'absolute' || style.position === 'sticky' ||
                                    current.tagName === 'BUTTON' || current.getAttribute('role') === 'dialog' || current.getAttribute('aria-modal') === 'true') {
                                    current.remove();
                                    removed = true;
                                    count++;
                                    break;
                                }
                                current = current.parentElement;
                            }
                            if (!removed) {
                                const container = el.closest('button, [role="button"], [aria-label*="ChatGPT"], [class*="chatgpt"], [id*="chatgpt"]');
                                if (container) {
                                    const style = window.getComputedStyle(container);
                                    if (style.position === 'fixed' || style.position === 'absolute' || style.position === 'sticky' ||
                                        container.getAttribute('role') === 'dialog' || container.getAttribute('aria-modal') === 'true') {
                                        container.remove();
                                        count++;
                                    }
                                }
                            }
                        }
                    } catch(e) {}

                    const selectors = [
                        '[class*="chatgpt"]', '[id*="chatgpt"]',
                        'button[aria-label*="ChatGPT"]'
                    ];
                    selectors.forEach(sel => {
                        try {
                            root.querySelectorAll(sel).forEach(el => {
                                const style = window.getComputedStyle(el);
                                if (style.position === 'fixed' || style.position === 'absolute' || style.position === 'sticky' ||
                                    el.tagName === 'BUTTON' || el.getAttribute('role') === 'dialog' || el.getAttribute('aria-modal') === 'true') {
                                    el.remove();
                                    count++;
                                }
                            });
                        } catch(e) {}
                    });
                    return count;
                }

                setInterval(() => {
                    nuke(document);
                    document.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) nuke(el.shadowRoot);
                    });
                }, 100);

                const observer = new MutationObserver(() => { nuke(document); });
                observer.observe(document.body, { childList: true, subtree: true });

                window.addEventListener('scroll', () => { nuke(document); }, { capture: true, passive: true });
            }""")
        except Exception as e:
            log(f"   ⚠️ 오버레이 방어막 설치 실패: {e}", "warning")

    log("\n🔍 SVG 요소 캡처 시작 (vega-embed 차트만)...", "info")

    output_path = Path(output_folder)
    output_path.mkdir(exist_ok=True)

    # vega-embed 차트가 렌더링될 때까지 대기
    log("   ⏳ Vega 차트 렌더링 대기 중...", "info")
    try:
        await page.wait_for_selector('div.vega-embed svg', timeout=10000, state='attached')
        log("   ✅ Vega 차트 렌더링 완료", "success")
    except Exception as e:
        log(f"   ⚠️ Vega 차트 렌더링 대기 시간 초과: {str(e)[:50]}", "warning")

    await page.wait_for_timeout(2000)
    await _remove_overlays()

    # 모든 SVG 찾기
    all_svgs = await page.query_selector_all('svg')
    log(f"   🔍 페이지 내 총 SVG 개수: {len(all_svgs)}개", "info")

    svg_elements = []

    if len(all_svgs) == 0:
        log("   ❌ 페이지에 SVG가 없습니다.", "error")
        return {'success': False, 'count': 0, 'files': []}

    for idx, svg in enumerate(all_svgs):
        try:
            await _remove_overlays()
            await page.wait_for_timeout(500)

            if not await svg.is_visible():
                continue

            box = await svg.bounding_box()
            if not box:
                continue

            if box['width'] < 10 or box['height'] < 10:
                continue

            is_target = False
            match_reason = ""

            if box['width'] > 200 and box['height'] > 100:
                is_target = True
                match_reason = f"Size ({box['width']}x{box['height']})"

            if not is_target:
                result = await svg.evaluate("""(el) => {
                    if (el.classList.contains('marks')) return "marks";
                    if (el.closest('div.vega-embed')) return "vega-embed";
                    if (el.closest('div[role="graphics-document"]')) return "role-graphics";
                    return null;
                }""")

                if result:
                    is_target = True
                    match_reason = f"Condition ({result})"

            if is_target:
                log(f"   ✅ SVG #{idx}: 캡처 대상 선정 ({match_reason})", "success")
                svg_elements.append(svg)

        except Exception as e:
            log(f"   ❌ SVG #{idx} 에러: {e}", "error")
            continue

    svg_count = len(svg_elements)
    log(f"   ✅ 캡처 대상 SVG 선정: {svg_count}개", "info")

    if svg_count == 0:
        log("   ❌ 캡처 조건에 맞는 SVG가 없습니다", "warning")
        return {'success': False, 'count': 0, 'files': []}

    captured_files = []
    captured_count = 0

    for idx, svg in enumerate(svg_elements):
        try:
            if not await svg.is_visible():
                continue

            box = await svg.bounding_box()
            if box and box['width'] > 10 and box['height'] > 10:
                if article_id is not None:
                    filename = output_path / f"{prefix}_{article_id:06d}_{captured_count}.png"
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    if isinstance(site_name, dict):
                        site_safe_name = site_name.get('name', 'unknown').replace(' ', '_').replace('/', '_')
                    else:
                        site_safe_name = str(site_name).replace(' ', '_').replace('/', '_')
                    filename = output_path / f"{site_safe_name}_svg_{timestamp}_{idx:03d}.png"

                await svg.screenshot(path=str(filename))

                # HTML에 캡처된 파일명 주입
                try:
                    await page.evaluate('''(svgElement, capturedFilename) => {
                        const container = svgElement.closest('div.vega-embed') || svgElement.parentElement;
                        if (container) {
                            container.setAttribute('data-captured-svg', capturedFilename);
                        }
                        svgElement.setAttribute('data-captured-svg', capturedFilename);
                    }''', svg, filename.name)
                except Exception:
                    pass

                log(f"   📸 Vega 차트 #{captured_count} 저장: {filename.name} ({box['width']:.0f}x{box['height']:.0f}px)", "success")
                captured_files.append(str(filename))
                captured_count += 1
        except Exception as e:
            log(f"   ⚠️ SVG #{idx} 캡처 실패: {str(e)[:50]}", "warning")
            continue

    log(f"\n✅ Vega 차트 캡처 완료: {captured_count}개 저장", "success")
    log(f"   📁 저장 위치: {output_path.absolute()}", "info")

    return {
        'success': True,
        'count': captured_count,
        'files': captured_files
    }
