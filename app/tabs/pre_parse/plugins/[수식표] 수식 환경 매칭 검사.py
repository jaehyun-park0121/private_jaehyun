import re
from typing import List

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    get_shape_flags_text,
    get_shape_label,
    iter_shape_dicts,
)


class Plugin(BaseCheckPlugin):
    TAG = "필수"
    DESCRIPTION = (
        "FORMULA 라벨 내부의 LaTeX 수식 환경 짝이 맞는지 검사합니다.\n"
        "[검사 대상]\n"
        "- flags.text 기준 검사\n"
        "\n"
        "[허용 환경]\n"
        "- equation\n"
        "- align\n"
        "- align*\n"
        "- multline\n"
        "- gather\n"
    )

    def option_schema(self):
        return []

    def run(self, page_context: PageContext) -> CheckResult:
        issues: List[Issue] = []
        shapes = page_context.json_data.get("shapes", [])

        if not isinstance(shapes, list) or not shapes:
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        equation_envs = {"equation", "align", "align*", "multline", "gather"}

        for idx, shape in iter_shape_dicts(page_context.json_data):
            shape_label = get_shape_label(shape)
            if shape_label != "FORMULA":
                continue

            flag_val = get_shape_flags_text(shape)
            if not flag_val:
                continue

            matches = list(re.finditer(r"(?<!\\)\\(begin|end)\{([^\}]+)\}", flag_val))

            invalid_envs = sorted({m.group(2) for m in matches if m.group(2) not in equation_envs})
            if invalid_envs:
                for env in invalid_envs:
                    issues.append(
                        Issue(
                            issue_code="LATEX_ENV_NOT_ALLOWED",
                            shape_index=idx,
                            error_type="허용되지 않은 수식 환경",
                            error_message=f"{env} 환경 허용 목록에 없음",
                        )
                    )
                continue

            env_stack: List[str] = []
            has_error = False

            for match in matches:
                token_type = match.group(1)
                env = match.group(2)

                if token_type == "begin":
                    env_stack.append(env)
                    continue

                if not env_stack:
                    issues.append(
                        Issue(
                            issue_code="LATEX_EQUATION_START_MISSING",
                            shape_index=idx,
                            error_type="수식 환경 시작 누락",
                            error_message=f"{env} 환경 시작 없이 종료",
                        )
                    )
                    has_error = True
                    break

                expected_env = env_stack[-1]
                if expected_env != env:
                    issues.append(
                        Issue(
                            issue_code="LATEX_EQUATION_END_MISMATCH",
                            shape_index=idx,
                            error_type="수식 환경 종료 불일치",
                            error_message=(
                                f"{expected_env} 대신 {env} 먼저 종료"
                            ),
                        )
                    )
                    has_error = True
                    break

                env_stack.pop()

            if has_error:
                continue

            if env_stack:
                for unmatched in reversed(env_stack):
                    issues.append(
                        Issue(
                            issue_code="LATEX_EQUATION_END_MISSING",
                            shape_index=idx,
                            error_type="수식 환경 종료 누락",
                            error_message=f"{unmatched} 환경 종료 누락",
                        )
                    )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
