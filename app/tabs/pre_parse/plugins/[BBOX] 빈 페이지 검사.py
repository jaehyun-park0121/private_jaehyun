from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext 
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue


class Plugin(BaseCheckPlugin):
    TAG = "선택"
    DESCRIPTION = "페이지의 shapes 값이 비어 있는지 검사합니다. shapes가 []이면 빈 페이지로 판단합니다."

    def run(self, page_context: PageContext) -> CheckResult:
        issues = [] 
        json_data = page_context.json_data if isinstance(page_context.json_data, dict) else {}  # json_data가 dict인지 안전하게 확인
        shapes = json_data.get("shapes", None)  # shapes 값 조회

        if shapes == []: 
            issues.append(
                Issue(
                    # 페이지 단위 오류이므로 특정 shape index 대신 -1 사용 -> 페이지 전체 대상 오류=
                    shape_index=-1,
                    error_type="빈 페이지",
                    error_message="페이지의 shapes 비어 있음",
                    issue_code="PAGESHAPE_EMPTY",
                )
            )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )