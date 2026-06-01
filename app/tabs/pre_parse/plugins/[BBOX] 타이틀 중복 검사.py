from typing import List

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin 
from app.tabs.pre_parse.plugin_system.context import PageContext 
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue 
from app.tabs.pre_parse.plugin_system.shape_utils import get_shape_label, iter_shape_dicts


class Plugin(BaseCheckPlugin):
    TAG = "필수" 
    DESCRIPTION = (
        "한 페이지 내부에 TITLE 라벨이 여러 개 있는 경우를 검사합니다.\n"
        "\n"
        "- TITLE 라벨이 2개 이상이면 중복으로 판단합니다."
    )

    def option_schema(self):
        return []  

    def run(self, page_context: PageContext) -> CheckResult:
        issues: List[Issue] = [] 
        shapes = page_context.json_data.get("shapes", []) 

        title_indices = [] 

        for idx, shape in iter_shape_dicts(page_context.json_data): 
            label = get_shape_label(shape)  # label 값을 대문자 기준으로 정리
            if label == "TITLE":  # TITLE 라벨인 경우만 수집
                title_indices.append(idx)  # 해당 shape index 저장

        if len(title_indices) >= 2:  # TITLE이 2개 이상이면 중복 오류로 판단
            title_count = len(title_indices)
            for shape_index in title_indices:  # 중복된 TITLE 각각에 대해 Issue 생성
                issues.append(
                    Issue(
                        shape_index=shape_index,  # 오류가 발생한 원본 shape index
                        error_type=f"페이지 내 TITLE {title_count}개",  # 오류 유형 필터용 분류명
                        error_message=f"페이지 내 TITLE {title_count}개 존재",
                        issue_code="DUPLICATE_TITLE_IN_PAGE",  
                    )
                )

        return CheckResult(
            check_id=self.PLUGIN_ID, 
            status="FAIL" if issues else "PASS", 
            issues=issues, 
        )
