from collections import Counter
from typing import Dict, List, Tuple

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    bbox_area,
    get_shape_bbox,
    get_shape_flags_text,
    get_shape_label,
    is_bbox_inside,
    iter_shape_dicts,
)


class Plugin(BaseCheckPlugin):
    TAG = "필수"
    DESCRIPTION = (
        "박스 내부 direct 자식 박스 수와 태그 수의 일치 여부를 검사합니다.\n"
        "[검사 대상]\n"
        "- ITEM 제외 bbox 기반 부모 박스\n"
        "- 자식 박스는 direct 포함 관계 기준\n"
        "- flags.text 내부 태그 수 비교\n"
        "\n"
        "[비교 태그]\n"
        "- FORMULA: {fr}\n"
        "- IMAGE: {im}\n"
        "- TABLE: {tb}\n"
        "- CHART: {ch}\n"
        "- ITEM: {em}\n"
    )

    TAG_BY_LABEL: Dict[str, str] = {
        "FORMULA": "{fr}",
        "IMAGE": "{im}",
        "TABLE": "{tb}",
        "CHART": "{ch}",
        "ITEM": "{em}",
    }

    LABEL_DISPLAY_NAME: Dict[str, str] = {
        "FORMULA": "수식",
        "IMAGE": "이미지",
        "TABLE": "표",
        "CHART": "차트",
        "ITEM": "아이템",
    }

    def run(self, page_context: PageContext) -> CheckResult:
        issues: List[Issue] = []
        shapes = page_context.json_data.get("shapes", [])

        if not isinstance(shapes, list) or not shapes:
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        # 1. bbox가 있는 shape만 정리하고 부모-자식 포함관계를 계산
        parsed: List[Tuple[int, str, Tuple[float, float, float, float], Dict]] = []
        parsed_by_idx: Dict[int, Tuple[int, str, Tuple[float, float, float, float], Dict]] = {}

        for idx, shape in iter_shape_dicts(page_context.json_data):
            bbox = get_shape_bbox(shape)
            if bbox is None:
                continue
            label = get_shape_label(shape)
            item = (idx, label, bbox, shape)
            parsed.append(item)
            parsed_by_idx[idx] = item

        direct_parent: Dict[int, int] = {}
        for child_idx, _, child_bbox, _ in parsed:
            candidate_parents: List[Tuple[float, int]] = []

            for parent_idx, _, parent_bbox, _ in parsed:
                if parent_idx == child_idx:
                    continue

                if is_bbox_inside(parent_bbox, child_bbox):
                    candidate_parents.append((bbox_area(parent_bbox), parent_idx))

            if candidate_parents:
                _, nearest_parent_idx = min(candidate_parents, key=lambda item: (item[0], item[1]))
                direct_parent[child_idx] = nearest_parent_idx

        children_map: Dict[int, List[int]] = {idx: [] for idx, _, _, _ in parsed}
        for child_idx, parent_idx in direct_parent.items():
            children_map[parent_idx].append(child_idx)

        # 2. 각 부모 박스를 기준으로 자식 수와 태그 수를 비교
        for parent_idx, parent_label, _, parent_shape in parsed:
            if parent_label == "ITEM":
                continue

            child_indices = children_map.get(parent_idx, [])
            actual_child_labels = [
                parsed_by_idx[child_idx][1]
                for child_idx in child_indices
                if child_idx in parsed_by_idx
            ]

            actual_child_counter = Counter(lbl for lbl in actual_child_labels if lbl in self.TAG_BY_LABEL)
            parent_text_lower = get_shape_flags_text(parent_shape).lower()
            actual_tag_counter = {
                child_label: parent_text_lower.count(tag_text)
                for child_label, tag_text in self.TAG_BY_LABEL.items()
            }

            has_tracked_child = any(actual_child_counter.get(label, 0) > 0 for label in self.TAG_BY_LABEL)
            has_tracked_tag = any(actual_tag_counter.get(label, 0) > 0 for label in self.TAG_BY_LABEL)
            if not has_tracked_child and not has_tracked_tag:
                continue

            for child_label, tag_text in self.TAG_BY_LABEL.items():
                child_count = actual_child_counter.get(child_label, 0)
                tag_count = int(actual_tag_counter.get(child_label, 0))
                if child_count != tag_count:
                    child_display_name = self.LABEL_DISPLAY_NAME.get(child_label, child_label)
                    issues.append(
                        Issue(
                            issue_code="INLINE_BOX_TAG_COUNT_MISMATCH",
                            shape_index=parent_idx,
                            error_type=child_label,
                            error_message=f"자식 {child_display_name} 박스: {child_count}개, {tag_text} 태그: {tag_count}개",
                        )
                    )

        # 3. 오류가 하나라도 있으면 FAIL, 없으면 PASS 반환
        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
