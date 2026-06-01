from typing import Dict, List, Tuple

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    bbox_area,
    get_shape_bbox,
    get_shape_label,
    is_bbox_inside,
    iter_shape_dicts,
)


class Plugin(BaseCheckPlugin):
    TAG = "필수"
    DESCRIPTION = (
        "박스 간 직접 포함 관계를 검사합니다.\n"
        "- 허용 관계: 정상 통과\n"
        "- 허용(의심) 관계: 오류 의심 포함관계로 검출\n"
        "- 그 외 관계: 허용되지 않은 포함관계로 검출\n"
        "\n"
        "[정상 허용 관계]\n"
        "- TEXT : IMAGE, FORMULA, TABLE, CHART\n"
        "- TITLE : IMAGE, FORMULA, TABLE, CHART\n"
        "- CAPTION : IMAGE, FORMULA\n"
        "- IMAGE : CAPTION\n"
        "- FORMULA : 없음\n"
        "- TABLE : CAPTION, IMAGE, CHART, ITEM\n"
        "- CHART : CAPTION\n"
        "- ITEM : TEXT, CAPTION, IMAGE, FORMULA, TABLE, CHART\n"
        "- FOOTNOTE : IMAGE, FORMULA, TABLE, CHART, ITEM\n"
        "\n"
        "[오류 의심 포함관계]\n"
        "- TEXT : ITEM\n"
        "- TITLE : ITEM\n"
        "- CAPTION : TABLE, CHART, ITEM\n"
    )

    # 정상 허용 관계
    ALLOWED_CHILDREN: Dict[str, set] = {
        "TEXT": {"IMAGE", "FORMULA", "TABLE", "CHART"},
        "TITLE": {"IMAGE", "FORMULA", "TABLE", "CHART"},
        "CAPTION": {"IMAGE", "FORMULA"},
        "IMAGE": {"CAPTION"},
        "FORMULA": set(),
        "TABLE": {"CAPTION", "IMAGE", "CHART", "ITEM"},
        "CHART": {"CAPTION"},
        "ITEM": {"TEXT", "CAPTION", "IMAGE", "FORMULA", "TABLE", "CHART"},
        "FOOTNOTE": {"IMAGE", "FORMULA", "TABLE", "CHART", "ITEM"},
    }

    # 허용(의심) 관계 → 별도 오류 유형으로 검출
    SUSPECT_CHILDREN: Dict[str, set] = {
        "TEXT": {"ITEM"},
        "TITLE": {"ITEM"},
        "CAPTION": {"TABLE", "CHART", "ITEM"},
    }

    def run(self, page_context: PageContext) -> CheckResult:
        # 검출된 이슈를 저장할 리스트
        issues: List[Issue] = []

        # JSON 내 shapes 목록 가져오기
        shapes = page_context.json_data.get("shapes", [])

        # shapes가 비어 있으면 검사 종료
        if not isinstance(shapes, list) or not shapes:
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        # 유효한 shape만 bbox와 함께 파싱
        parsed: List[Tuple[int, str, Tuple[float, float, float, float]]] = []
        for idx, shape in iter_shape_dicts(page_context.json_data):
            bbox = get_shape_bbox(shape)
            if bbox is None:
                continue
            label = get_shape_label(shape)
            parsed.append((idx, label, bbox))

        # 각 자식 박스의 "직접 부모"를 저장
        direct_parent: Dict[int, int] = {}

        for child_idx, _, child_bbox in parsed:
            candidate_parents = []

            for parent_idx, _, parent_bbox in parsed:
                # 자기 자신은 부모 후보에서 제외
                if parent_idx == child_idx:
                    continue

                # parent가 child를 포함하면 후보 부모로 저장
                if is_bbox_inside(parent_bbox, child_bbox):
                    parent_area = bbox_area(parent_bbox)
                    candidate_parents.append((parent_area, parent_idx))

            # 가장 작은 면적의 부모 = 가장 가까운 직접 부모
            if candidate_parents:
                _, nearest_parent_idx = min(candidate_parents, key=lambda x: (x[0], x[1]))
                direct_parent[child_idx] = nearest_parent_idx

        # 부모별 자식 목록 생성
        children_map: Dict[int, List[int]] = {idx: [] for idx, _, _ in parsed}
        for child_idx, parent_idx in direct_parent.items():
            children_map[parent_idx].append(child_idx)

        # index 기준으로 label/bbox를 빠르게 찾기 위한 dict
        parsed_dict: Dict[int, Tuple[str, Tuple[float, float, float, float]]] = {
            idx: (label, bbox) for idx, label, bbox in parsed
        }

        # 직접 포함 관계 검사
        for parent_idx, child_indices in children_map.items():
            parent_label, _ = parsed_dict[parent_idx]

            # 정상 허용 자식 목록
            allowed_children = self.ALLOWED_CHILDREN.get(parent_label, set())

            # 허용(의심) 자식 목록
            suspect_children = self.SUSPECT_CHILDREN.get(parent_label, set())

            for child_idx in child_indices:
                child_label, _ = parsed_dict[child_idx]

                # 1. 정상 허용 관계면 통과
                if child_label in allowed_children:
                    continue

                # 2. 허용(의심) 관계면 "오류 의심 포함관계"로 검출
                if child_label in suspect_children:
                    issues.append(
                        Issue(
                            issue_code=f"SUSPECT_INCLUDED_RELATION_{parent_label}",
                            shape_index=parent_idx,
                            error_type="오류 의심 포함관계",
                            error_message=(
                                f"{parent_label} 박스 안에 {child_label} 라벨이 포함 "
                                f"(오류 의심 포함관계이므로 확인 필요)"
                            ),
                        )
                    )
                    continue

                # 3. 그 외는 허용되지 않은 포함관계
                issues.append(
                    Issue(
                        issue_code=f"UNDEFINED_INCLUDED_RELATION_{parent_label}",
                        shape_index=parent_idx,
                        error_type=f"허용되지 않은 포함관계 부모 라벨: {parent_label}",
                        error_message=f"{parent_label} 내부 {child_label} 포함 불가",
                    )
                )

        # 이슈가 하나라도 있으면 FAIL, 없으면 PASS
        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
