from __future__ import annotations

from typing import Dict, Iterable, List

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.registry import CheckRegistry

from .context import PageContext
from .result_model import CheckResult, Issue


class CheckRunner:
    def __init__(self, registry: CheckRegistry) -> None:
        self.registry = registry

    def run_for_page(
        self, page_context: PageContext, selected_plugin_ids: Iterable[str]
    ) -> Dict[str, CheckResult]:
        results: Dict[str, CheckResult] = {}
        for plugin_id in selected_plugin_ids:
            plugin = self.registry.get(plugin_id)
            if not isinstance(plugin, BaseCheckPlugin):
                continue
            try:
                result = plugin.run(page_context)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                result = CheckResult(
                    check_id=plugin_id,
                    status="FAIL",
                    issues=[
                        Issue(
                            shape_index=-1,
                            issue_code="PLUGIN_RUNTIME_ERROR",
                            error_type="[플러그인 실행 오류]",
                            error_message=message,
                        )
                    ],
                    debug_message=message,
                )
            results[plugin_id] = result
        return results

    def run_for_pages(
        self, page_contexts: List[PageContext], selected_plugin_ids: Iterable[str]
    ) -> Dict[str, Dict[str, CheckResult]]:
        page_results: Dict[str, Dict[str, CheckResult]] = {}
        for ctx in page_contexts:
            page_key = f"{ctx.book_id}:{ctx.page_no}"
            page_results[page_key] = self.run_for_page(ctx, selected_plugin_ids)
        return page_results
