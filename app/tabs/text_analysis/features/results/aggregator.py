from __future__ import annotations

from typing import Callable, Dict, List


class TextAnalysisResultAggregator:
    def build_dashboard_payload(
        self,
        *,
        active_tool_id: str,
        label_rows: List[dict],
        row_has_issue: Callable[[dict], bool],
        issue_builder: Callable[[dict], List[dict]],
    ) -> tuple[dict, List[dict], List[dict]]:
        page_map: Dict[str, dict] = {}
        issues: List[dict] = []

        for row in label_rows:
            page_key = str(row.get("page_no", "")).strip()
            page_entry = page_map.setdefault(
                page_key,
                {
                    "page_no": page_key,
                    "book_id": str(row.get("book_id", "")).strip(),
                    "page_name": str(row.get("page_name", "")).strip(),
                    "issue_count": 0,
                },
            )
            if row_has_issue(row):
                page_entry["issue_count"] += 1
                issues.extend(issue_builder(row))

        page_rows = list(page_map.values())
        stats = {
            "active_tool": str(active_tool_id or "").strip() or "special_char_analysis",
            "total_books": len(
                {
                    str(row.get("book_id", "")).strip()
                    for row in page_rows
                    if str(row.get("book_id", "")).strip()
                }
            ),
            "matched_pages": sum(1 for row in page_rows if int(row.get("issue_count", 0)) > 0),
            "total_labels": len(label_rows),
            "matched_labels": sum(1 for row in label_rows if row_has_issue(row)),
        }
        return stats, page_rows, issues
