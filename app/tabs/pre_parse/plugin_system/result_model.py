from typing import List, Optional


class Issue:
    """Single fail item returned by a plugin."""

    def __init__(
        self,
        *,
        shape_index: int,
        error_type: str = "",
        error_message: str = "",
        issue_code: str = "",
        **legacy,
    ) -> None:
        self.shape_index = int(shape_index)
        self.issue_code = str(issue_code or legacy.get("issue_code", "") or "")
        self.error_type = str(error_type or legacy.get("error_type", "") or "")
        self.error_message = str(error_message or legacy.get("message", "") or "")

    @property
    def message(self) -> str:
        return self.error_message


class CheckResult:
    """Page-level result for a single plugin."""

    def __init__(
        self,
        *,
        check_id: str,
        status: str,
        issues: Optional[List[Issue]] = None,
        debug_message: Optional[str] = None,
        **legacy,
    ) -> None:
        self.check_id = str(check_id)
        self.status = str(status)
        self.issues = list(issues or [])
        self.debug_message = str(
            debug_message
            or legacy.get("debug_message", "")
            or legacy.get("error_message", "")
            or ""
        )

    @property
    def issue_count(self) -> int:
        return len(self.issues)
