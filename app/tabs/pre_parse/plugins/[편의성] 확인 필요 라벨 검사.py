from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import iter_shape_dicts


class Plugin(BaseCheckPlugin):
    TAG = "선택"
    DESCRIPTION = "is_problem 값이 true인 라벨만 검사하고, problem_reason 값을 오류 유형과 세부 내용으로 표시합니다."

    def option_schema(self):
        return []

    def _to_bool(self, value) -> bool:
        # bool이면 그대로 반환
        if isinstance(value, bool):
            return value

        # None이면 False
        if value is None:
            return False

        # 문자열이면 true 계열만 True 처리
        if isinstance(value, str):
            return value.strip().lower() in {"true"}

        # 숫자면 0이 아닐 때 True
        if isinstance(value, (int, float)):
            return value != 0

        # 그 외는 기본 bool 처리
        return bool(value)

    def run(self, page_context: PageContext) -> CheckResult:
        issues = []

        # 현재 페이지의 shapes 목록을 가져옴
        shapes = page_context.json_data.get("shapes", [])

        # shapes가 리스트가 아니면 PASS 반환
        if not isinstance(shapes, list):
            return CheckResult(
                check_id=self.PLUGIN_ID,
                status="PASS",
                issues=[],
            )

        # 모든 shape를 순회
        for idx, shape in iter_shape_dicts(page_context.json_data):
            # is_problem 값을 안전하게 bool로 변환
            is_problem = self._to_bool(shape.get("is_problem", False))

            # is_problem이 true가 아니면 건너뜀
            if not is_problem:
                continue

            # problem_reason 원본 값 가져오기
            raw_problem_reason = shape.get("problem_reason", "")

            # problem_reason이 None이면 빈 문자열 처리
            if raw_problem_reason is None:
                problem_reason = ""
            else:
                # 원본 문자열 그대로 사용
                problem_reason = str(raw_problem_reason)

            # problem_reason이 비어 있으면 
            # 비어 있는 문자 값으로 사용
            if problem_reason == "":
                error_message = "\u200b"
            else:
                error_message = problem_reason

            # is_problem == true면 무조건 Issue 추가
            issues.append(
                Issue(
                    shape_index=idx,
                    error_type=error_message,
                    error_message=error_message,
                    issue_code="IS_PROBLEM_LABEL",
                )
            )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
