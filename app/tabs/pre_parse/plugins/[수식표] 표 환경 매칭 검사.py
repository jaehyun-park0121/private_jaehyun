import re
from typing import List, Tuple

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import get_shape_flags_text, get_shape_label, iter_shape_dicts


class Plugin(BaseCheckPlugin):
    TAG = "필수"
    DESCRIPTION = (
        "TABLE 라벨 내부의 표 환경 짝이 맞는지 검사합니다.\n"
        "옵션에 따라 TABLE HTML 또는 TABLE LATEX 기준으로 검사합니다.\n"
        "[검사 대상]\n"
        "- TABLE 라벨 flags.text 검사\n"
    )

    def option_schema(self):
        return [
            {
                "key": "matching_check_type",
                "label": "검사 방식",
                "type": "select",
                "choices": ["TABLE HTML", "TABLE LATEX"],
                "default": "TABLE HTML",
                "placeholder": "검사 방식을 선택하세요.",
            }
        ]

    @staticmethod
    def _extract_html_tokens(html_text: str) -> List[Tuple[str, str]]:
        token_pattern = re.compile(r"<\s*(/)?\s*(table|tr|td|th|caption|tfoot)\b[^>]*>", re.IGNORECASE)
        tokens: List[Tuple[str, str]] = []

        for match in token_pattern.finditer(html_text):
            is_end = bool(match.group(1))
            tag = match.group(2).lower()
            tokens.append(("end" if is_end else "start", tag))

        return tokens

    def run(self, page_context: PageContext) -> CheckResult:
        issues: List[Issue] = []
        shapes = page_context.json_data.get("shapes", [])

        if not isinstance(shapes, list) or not shapes:
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        options = page_context.config.get(self.PLUGIN_ID, {}) if isinstance(page_context.config, dict) else {}
        matching_check_type = str(options.get("matching_check_type", "TABLE HTML")).strip().upper()
        if matching_check_type not in ("TABLE LATEX", "TABLE HTML"):
            matching_check_type = "TABLE HTML"

        check_table_latex = matching_check_type == "TABLE LATEX"
        check_table_html = matching_check_type == "TABLE HTML"

        for idx, shape in iter_shape_dicts(page_context.json_data):
            shape_label = get_shape_label(shape)
            if shape_label != "TABLE":
                continue

            flags_value = shape.get("flags")
            if not isinstance(flags_value, dict):
                continue

            if not flags_value:
                if check_table_latex:
                    issues.append(
                        Issue(
                            issue_code="TABLE_ENV_MISSING",
                            shape_index=idx,
                            error_type="TABLE 환경 누락",
                            error_message="tabular 환경 누락",
                        )
                    )
                if check_table_html:
                    issues.append(
                        Issue(
                            issue_code="TABLE_HTML_ENV_MISSING",
                            shape_index=idx,
                            error_type="HTML TABLE 환경 누락",
                            error_message="HTML table 태그 누락",
                        )
                    )
                continue

            flag_val = get_shape_flags_text(shape)

            lower_val = flag_val.lower()

            if check_table_latex:
                valid_begin_count = len(re.findall(r"(?<!\\)\\begin\{tabular\}", flag_val))
                valid_end_count = len(re.findall(r"(?<!\\)\\end\{tabular\}", flag_val))
                escaped_begin_count = len(re.findall(r"(?<!\\)\\\\begin\{tabular\}", flag_val))
                escaped_end_count = len(re.findall(r"(?<!\\)\\\\end\{tabular\}", flag_val))
                has_html_table = "<table" in lower_val or "</table>" in lower_val

                if escaped_begin_count > 0 or escaped_end_count > 0:
                    issues.append(
                        Issue(
                            issue_code="TABLE_ENV_ESCAPED",
                            shape_index=idx,
                            error_type="tabular 환경 이스케이프 오류",
                           error_message="tabular 환경 이스케이프 형태 포함",
                        )
                    )
                elif valid_begin_count == 0 and valid_end_count == 0 and not has_html_table:
                    issues.append(
                        Issue(
                            issue_code="TABLE_ENV_MISSING",
                            shape_index=idx,
                            error_type="TABLE 환경 누락",
                            error_message="tabular 환경 누락",
                        )
                    )
                else:
                    stripped_val = flag_val.strip()

                    if valid_begin_count > 0 and not stripped_val.startswith(r"\begin{tabular}"):
                        issues.append(
                            Issue(
                                issue_code="TABLE_ENV_START_INVALID",
                                shape_index=idx,
                                error_type="tabular 시작 환경 오류",
                                error_message="tabular 시작 위치 오류",
                            )
                        )
                    elif valid_end_count > 0 and not stripped_val.endswith(r"\end{tabular}"):
                        issues.append(
                            Issue(
                                issue_code="TABLE_ENV_END_INVALID",
                                shape_index=idx,
                                error_type="tabular 종료 환경 오류",
                                error_message="tabular 종료 환경 위치 오류",
                            )
                        )
                    else:
                        latex_tokens = list(re.finditer(r"(?<!\\)\\(begin|end)\{([^\}]+)\}", flag_val))
                        env_stack: List[str] = []
                        latex_error_recorded = False

                        for match in latex_tokens:
                            token_type = match.group(1)
                            env_name = match.group(2)

                            if token_type == "begin":
                                env_stack.append(env_name)
                                continue

                            if not env_stack:
                                issues.append(
                                    Issue(
                                        issue_code="TABLE_ENV_START_INVALID",
                                        shape_index=idx,
                                        error_type="tabular 시작 환경 오류",
                                        error_message=f"{env_name} 환경 시작 없이 종료",
                                    )
                                )
                                latex_error_recorded = True
                                break

                            expected_env = env_stack[-1]
                            if expected_env != env_name:
                                issues.append(
                                    Issue(
                                        issue_code="TABLE_ENV_SYNTAX_ERROR",
                                        shape_index=idx,
                                        error_type="tabular 환경 문법 오류",
                                        error_message=(
                                            f"{expected_env} 대신 {env_name} 먼저 종료"
                                        ),
                                    )
                                )
                                latex_error_recorded = True
                                break

                            env_stack.pop()

                        if not latex_error_recorded and env_stack:
                            issues.append(
                                Issue(
                                    issue_code="TABLE_ENV_END_INVALID",
                                    shape_index=idx,
                                    error_type="tabular 종료 환경 오류",
                                    error_message=f"{env_stack[-1]} 환경 종료 누락",
                                )
                            )

            if check_table_html:
                html_tokens = self._extract_html_tokens(flag_val)
                has_table_open = bool(re.search(r"<\s*table\b", lower_val))
                has_table_close = bool(re.search(r"<\s*/\s*table\s*>", lower_val))

                if not html_tokens and r"\begin{tabular}" not in flag_val and r"\end{tabular}" not in flag_val:
                    issues.append(
                        Issue(
                            issue_code="TABLE_HTML_ENV_MISSING",
                            shape_index=idx,
                            error_type="HTML TABLE 환경 누락",
                            error_message="HTML table 태그 누락",
                        )
                    )
                elif has_table_open and not lower_val.strip().startswith("<table"):
                    issues.append(
                        Issue(
                            issue_code="TABLE_HTML_START_INVALID",
                            shape_index=idx,
                            error_type="HTML table 시작 태그 오류",
                            error_message="HTML table 시작 위치 오류",
                        )
                    )
                elif has_table_close and not lower_val.strip().endswith("</table>"):
                    issues.append(
                        Issue(
                            issue_code="TABLE_HTML_END_INVALID",
                            shape_index=idx,
                            error_type="HTML table 종료 태그 오류",
                            error_message="HTML table 종료 위치 오류",
                        )
                    )
                else:
                    html_stack: List[str] = []
                    html_error_recorded = False

                    for token_type, tag_name in html_tokens:
                        if token_type == "start":
                            html_stack.append(tag_name)
                            continue

                        if not html_stack:
                            issues.append(
                                Issue(
                                    issue_code="TABLE_HTML_START_INVALID",
                                    shape_index=idx,
                                    error_type="HTML table 시작 태그 오류",
                                    error_message=f"{tag_name} 시작 태그 없음"
                                )
                            )
                            html_error_recorded = True
                            break

                        expected_tag = html_stack[-1]
                        if expected_tag != tag_name:
                            issues.append(
                                Issue(
                                    issue_code="TABLE_HTML_SYNTAX_ERROR",
                                    shape_index=idx,
                                    error_type="HTML 태그 문법 오류",
                                    error_message=(
                                        f"{expected_tag} 대신 {tag_name} 먼저 종료"
                                    ),
                                )
                            )
                            html_error_recorded = True
                            break

                        html_stack.pop()

                    if not html_error_recorded and html_stack:
                        issues.append(
                            Issue(
                                issue_code="TABLE_HTML_END_INVALID",
                                shape_index=idx,
                                error_type="HTML table 종료 태그 오류",
                                error_message=f"{html_stack[-1]} 종료 태그 누락",
                            )
                        )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
