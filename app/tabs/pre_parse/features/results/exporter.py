from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from app.common.io.encoding import CSV_ENCODING, dump_json_file
from .aggregator import AggregatedStats
from ...plugin_system.result_model import CheckResult


class ResultExporter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        page_results: Dict[str, Dict[str, CheckResult]],
        page_rows: List[dict],
        issues: List[dict],
        stats: AggregatedStats,
    ) -> None:
        self._write_summary(stats)
        self._write_page_results(page_rows)
        self._write_issues(issues)
        # TODO: stats.xlsx / error_previews/ 생성 로직 확장

    def _write_summary(self, stats: AggregatedStats) -> None:
        payload = {
            "total_books": stats.total_books,
            "total_pages": stats.total_pages,
            "error_pages": stats.error_pages,
            "total_issues": stats.total_issues,
            "pass_rate": stats.pass_rate,
        }
        dump_json_file(self.output_dir / "summary.json", payload, ensure_ascii=False, indent=2)

    def _write_page_results(self, rows: List[dict]) -> None:
        path = self.output_dir / "page_results.csv"
        with path.open("w", encoding=CSV_ENCODING, newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["page_no", "status", "issue_count", "failed_checks"])
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "page_no": row.get("page_no", ""),
                        "status": row.get("status", ""),
                        "issue_count": row.get("issue_count", 0),
                        "failed_checks": ",".join(row.get("failed_checks", [])),
                    }
                )

    def _write_issues(self, issues: List[dict]) -> None:
        path = self.output_dir / "issues.csv"
        with path.open("w", encoding=CSV_ENCODING, newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["check_id", "label", "shape_index", "bbox", "error_type", "error_message"],
            )
            writer.writeheader()
            for issue in issues:
                writer.writerow(
                    {
                        "check_id": issue.get("check_id", ""),
                        "label": issue.get("label", ""),
                        "shape_index": issue.get("shape_index", ""),
                        "bbox": issue.get("bbox", []),
                        "error_type": issue.get("error_type", ""),
                        "error_message": issue.get("error_message", issue.get("message", "")),
                    }
                )
