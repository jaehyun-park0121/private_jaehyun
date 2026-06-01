from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ...plugin_system.result_model import CheckResult


@dataclass
class AggregatedStats:
    total_books: int = 0
    total_pages: int = 0
    error_pages: int = 0
    total_issues: int = 0
    pass_rate: float = 0.0


class ResultAggregator:
    def aggregate(
        self, page_results: Dict[str, Dict[str, CheckResult]], total_books: int = 0
    ) -> AggregatedStats:
        stats = AggregatedStats(total_books=total_books, total_pages=len(page_results))
        for _, checks in page_results.items():
            page_issue_count = sum(result.issue_count for result in checks.values())
            page_failed = page_issue_count > 0 or any(
                str(result.status).upper() == "FAIL" for result in checks.values()
            )
            if page_failed:
                stats.error_pages += 1
            stats.total_issues += page_issue_count
        if stats.total_pages > 0:
            pass_pages = stats.total_pages - stats.error_pages
            stats.pass_rate = (pass_pages / stats.total_pages) * 100.0
        return stats
