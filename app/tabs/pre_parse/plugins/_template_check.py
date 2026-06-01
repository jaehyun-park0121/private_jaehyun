from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue


class Plugin(BaseCheckPlugin):
    TAG = "optional"
    DESCRIPTION = "새 플러그인 작성 시 참고하는 템플릿 플러그인입니다."

    def option_schema(self):
        return [
            {"key": "enabled", "label": "검사 사용", "type": "bool", "default": True},
            {
                "key": "result_mode",
                "label": "결과 모드",
                "type": "select",
                "choices": ["PASS", "FAIL_DEMO"],
                "default": "PASS",
                "placeholder": "결과 모드를 선택하세요.",
            },
            {
                "key": "demo_text",
                "label": "예시 문구",
                "type": "text",
                "default": "",
                "placeholder": "표에 표시할 설명을 입력하세요.",
            },
            {
                "key": "target_labels",
                "label": "대상 라벨",
                "type": "multi_select_buttons",
                "choices": ["TEXT", "TITLE", "CAPTION", "IMAGE", "FORMULA", "TABLE", "CHART", "ITEM", "FOOTNOTE"],
                "default": ["TEXT", "TITLE", "CAPTION", "FOOTNOTE"],
                "columns": 3,
            },
        ]

    def run(self, page_context: PageContext) -> CheckResult:
        issues = []
        options = page_context.config.get(self.PLUGIN_ID, {}) if isinstance(page_context.config, dict) else {}
        if not bool(options.get("enabled", True)):
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        target_labels = options.get("target_labels", [])
        if not isinstance(target_labels, list):
            target_labels = []

        if str(options.get("result_mode", "PASS")).upper() == "FAIL_DEMO":
            detail = str(options.get("demo_text", "") or "").strip()
            if not detail:
                detail = "template_check 플러그인에서 생성한 예시 오류입니다."
            issues.append(
                Issue(
                    issue_code="TEMPLATE_DEMO_ISSUE",
                    shape_index=0,
                    error_type="[템플릿 예시 오류]",
                    error_message=(
                        f"{detail} "
                        f"(대상 라벨: {', '.join(target_labels) if target_labels else '-'})"
                    ),
                )
            )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
