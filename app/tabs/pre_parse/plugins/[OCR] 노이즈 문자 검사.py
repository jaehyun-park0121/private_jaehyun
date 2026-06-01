import re
from typing import Dict, List, Pattern

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
        "TEXT, FOOTNOTE, TITLE, CAPTION 라벨의 텍스트에서 노이즈 문자를 그룹별로 검사합니다.\n"
        "\n"
        "[검사 대상]\n"
        "- flags.text 검사\n"
        "\n"
        "[기본 검사]\n"
        "- 제어 및 비가시\n"
        "- 품질 이상\n"
        "\n"
        "[확장 검사]\n"
        "- 체크 시 공백 및 줄바꿈, 사적 영역, 구두점 및 인용 부호, 전각, 단위 및 기호, 한글 자모, 괄호 및 원문자, 스타일 문자를 추가 검사합니다.\n"
        "\n"
        "오류 메시지는 매칭 문맥과 권장 처리 방식 기준으로 표시됩니다."
    )

    TARGET_LABELS = {"TEXT", "FOOTNOTE", "TITLE", "CAPTION"}

    NOISE_RULES = [
        {
            "error_type": "공백 및 줄바꿈",
            "issue_code": "NOISE_WHITESPACE_LINEBREAK",
            "action": "치환",
            "extended_only": True,
            "subrules": [
                {
                    "name": "공백",
                    "pattern_text": r"[\u0009\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]",
                    "pattern": re.compile(r"[\u0009\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]"),
                },
                {
                    "name": "줄바꿈",
                    "pattern_text": r"[\u000B-\u000D\u001C-\u001E\u0085\u2028\u2029]",
                    "pattern": re.compile(r"[\u000B-\u000D\u001C-\u001E\u0085\u2028\u2029]"),
                },
            ],
        },
        {
            "error_type": "제어 및 비가시",
            "issue_code": "NOISE_CONTROL_INVISIBLE",
            "action": "삭제",
            "extended_only": False,
            "subrules": [
                {
                    "name": "제어 및 비가시",
                    "pattern_text": (
                        r"[\u0000-\u0008\u000E-\u001B\u001F\u007F\u0080-\u0084\u0086-\u009F"
                        r"\u00AD\u034F\u061C\u115F-\u1160\u180B-\u180F\u200B-\u200F"
                        r"\u202A-\u202E\u2060-\u206F\u3164\uFEFF]"
                    ),
                    "pattern": re.compile(
                        r"[\u0000-\u0008\u000E-\u001B\u001F\u007F\u0080-\u0084\u0086-\u009F"
                        r"\u00AD\u034F\u061C\u115F-\u1160\u180B-\u180F\u200B-\u200F"
                        r"\u202A-\u202E\u2060-\u206F\u3164\uFEFF]"
                    ),
                }
            ],
        },
        {
            "error_type": "품질 이상",
            "issue_code": "NOISE_REPLACEMENT_CHARACTER",
            "action": "삭제",
            "extended_only": False,
            "subrules": [
                {
                    "name": "품질 이상",
                    "pattern_text": r"\uFFFD",
                    "pattern": re.compile(r"\uFFFD"),
                }
            ],
        },
        {
            "error_type": "사적 영역",
            "issue_code": "NOISE_PRIVATE_USE_AREA",
            "action": "검색 후 수기 검수 진행",
            "extended_only": True,
            "subrules": [
                {
                    "name": "사적 영역",
                    "pattern_text": r"[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]",
                    "pattern": re.compile(r"[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]"),
                }
            ],
        },
        {
            "error_type": "구두점 및 인용 부호",
            "issue_code": "NOISE_PUNCTUATION_QUOTES",
            "action": "치환",
            "extended_only": True,
            "subrules": [
                {
                    "name": "“",
                    "pattern_text": r"[\u201C-\u201F]",
                    "pattern": re.compile(r"[\u201C-\u201F]"),
                },
                {
                    "name": "’",
                    "pattern_text": r"[\u2018-\u201B]",
                    "pattern": re.compile(r"[\u2018-\u201B]"),
                },
                {
                    "name": "-",
                    "pattern_text": r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]",
                    "pattern": re.compile(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]"),
                },
                {
                    "name": "·",
                    "pattern_text": r"[\u00B7\u2022\u2027\u2219\u22C5]",
                    "pattern": re.compile(r"[\u00B7\u2022\u2027\u2219\u22C5]"),
                },
                {
                    "name": "~",
                    "pattern_text": r"[\u007E\u02DC\u2053\u223C\u301C\uFF5E]",
                    "pattern": re.compile(r"[\u007E\u02DC\u2053\u223C\u301C\uFF5E]"),
                },
            ],
        },
        {
            "error_type": "전각",
            "issue_code": "NOISE_FULLWIDTH",
            "action": "정규화(NFKC)",
            "extended_only": True,
            "subrules": [
                {
                    "name": "전각",
                    "pattern_text": r"[\uFF01-\uFF5E]",
                    "pattern": re.compile(r"[\uFF01-\uFF5E]"),
                }
            ],
        },
        {
            "error_type": "단위 및 기호",
            "issue_code": "NOISE_UNITS_SYMBOLS",
            "action": "정규화(NFKC)",
            "extended_only": True,
            "subrules": [
                {
                    "name": "단위 및 기호",
                    "pattern_text": r"[\u2100-\u214F\u3300-\u33FF]",
                    "pattern": re.compile(r"[\u2100-\u214F\u3300-\u33FF]"),
                }
            ],
        },
        {
            "error_type": "한글 자모",
            "issue_code": "NOISE_HANGUL_JAMO",
            "action": "정규화(NFKC)",
            "extended_only": True,
            "subrules": [
                {
                    "name": "한글 자모",
                    "pattern_text": r"[\u1100-\u11FF]",
                    "pattern": re.compile(r"[\u1100-\u11FF]"),
                }
            ],
        },
        {
            "error_type": "괄호 및 원문자",
            "issue_code": "NOISE_ENCLOSED_ALPHANUMERICS",
            "action": "괄호문자, 점문자: 정규화(NFKC) / 원문자: 검색 후 수기 검수 진행",
            "extended_only": True,
            "subrules": [
                {
                    "name": "괄호 문자",
                    "pattern_text": r"[\u2474-\u2487\u3200-\u321B]",
                    "pattern": re.compile(r"[\u2474-\u2487\u3200-\u321B]"),
                },
                {
                    "name": "원 문자",
                    "pattern_text": r"[\u2460-\u2473\u24B6-\u24CF\u24D0-\u24E9\u3260-\u326D]",
                    "pattern": re.compile(r"[\u2460-\u2473\u24B6-\u24CF\u24D0-\u24E9\u3260-\u326D]"),
                },
                {
                    "name": "점 문자",
                    "pattern_text": r"[\u2488-\u249B]",
                    "pattern": re.compile(r"[\u2488-\u249B]"),
                },
            ],
        },
        {
            "error_type": "스타일 문자",
            "issue_code": "NOISE_STYLED_TEXT",
            "action": "정규화(NFKC)",
            "extended_only": True,
            "subrules": [
                {
                    "name": "스타일 문자",
                    "pattern_text": r"[\U0001D400-\U0001D7FF]",
                    "pattern": re.compile(r"[\U0001D400-\U0001D7FF]"),
                }
            ],
        },
    ]

    def option_schema(self):
        return [
            {
                "key": "enable_extended_groups",
                "label": "확장 검사",
                "type": "bool",
                "default": False,
            }
        ]

    def run(self, page_context: PageContext) -> CheckResult:
        issues: List[Issue] = []
        json_data = page_context.json_data if isinstance(page_context.json_data, dict) else {}
        shapes = json_data.get("shapes", [])

        if not isinstance(shapes, list):
            return CheckResult(
                check_id=self.PLUGIN_ID,
                status="PASS",
                issues=[],
            )

        options = page_context.config.get(self.PLUGIN_ID, {}) if isinstance(page_context.config, dict) else {}
        enable_extended_groups = self._to_bool(options.get("enable_extended_groups", False))
        active_rules = self._get_active_rules(enable_extended_groups)

        for idx, shape in iter_shape_dicts(json_data):
            label = get_shape_label(shape)
            if label not in self.TARGET_LABELS:
                continue

            text_value = get_shape_flags_text(shape)
            if not text_value:
                continue

            for rule in active_rules:
                matched_infos: List[Dict[str, str]] = []

                for subrule in rule["subrules"]:
                    found_infos = self._extract_match_infos(
                        text=text_value,
                        pattern=subrule["pattern"],
                    )
                    if not found_infos:
                        continue

                    matched_infos.extend(found_infos)

                matched_infos = self._deduplicate_match_infos(matched_infos)
                if not matched_infos:
                    continue

                issues.append(
                    Issue(
                        shape_index=idx,
                        error_type=str(rule["error_type"]),
                        error_message=self._build_error_message(
                            action=str(rule["action"]),
                            matched_infos=matched_infos,
                        ),
                        issue_code=str(rule["issue_code"]),
                    )
                )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )

    def _get_active_rules(self, enable_extended_groups: bool) -> List[Dict[str, object]]:
        if enable_extended_groups:
            return list(self.NOISE_RULES)
        return [rule for rule in self.NOISE_RULES if not bool(rule.get("extended_only", False))]

    def _to_bool(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on"}

    def _extract_match_infos(self, text: str, pattern: Pattern) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []

        for match in pattern.finditer(text):
            start, end = match.span()
            matched_text = match.group()
            context = self._make_context_snippet(text, start, end)

            results.append(
                {
                    "char": matched_text,
                    "start": str(start),
                    "end": str(end),
                    "context": context,
                }
            )

        return results

    def _deduplicate_match_infos(self, match_infos: List[Dict[str, str]]) -> List[Dict[str, str]]:
        unique: List[Dict[str, str]] = []
        seen = set()

        for info in match_infos:
            key = (info["char"], info["start"], info["end"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(info)

        return unique

    def _make_context_snippet(self, text: str, start: int, end: int, window: int = 15) -> str:
        left = max(0, start - window)
        right = min(len(text), end + window)

        before = text[left:start]
        target = text[start:end]
        after = text[end:right]

        before = self._escape_for_message(before)
        target = self._escape_for_message(target)
        after = self._escape_for_message(after)

        prefix = "..." if left > 0 else ""
        suffix = "..." if right < len(text) else ""

        return f"{prefix}{before}{target}{after}{suffix}"

    def _build_error_message(
        self,
        *,
        action: str,
        matched_infos: List[Dict[str, str]],
    ) -> str:
        preview_items: List[str] = []

        for info in matched_infos[:5]:
            preview_items.append(
                f"매칭 패턴: {info['context']}"
            )

        if len(matched_infos) > 5:
            preview_items.append(f"외 {len(matched_infos) - 5}건")

        return f"{' | '.join(preview_items)} ({action} 필요)"

    def _format_char(self, char: str) -> str:
        codepoint = ord(char)
        code_text = f"U+{codepoint:04X}" if codepoint <= 0xFFFF else f"U+{codepoint:06X}"

        if char == " ":
            display = "[SPACE]"
        elif char == "\t":
            display = "[TAB]"
        elif char == "\n":
            display = "[LF]"
        elif char == "\r":
            display = "[CR]"
        else:
            display = self._escape_for_message(char)

        return f"{display}({code_text})"

    def _escape_for_message(self, text: str) -> str:
        return (
            text.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
        )
