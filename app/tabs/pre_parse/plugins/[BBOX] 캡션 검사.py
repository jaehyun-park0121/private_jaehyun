from typing import Dict, List, Tuple

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    get_shape_bbox,
    get_shape_label,
    is_bbox_inside,
    iter_shape_dicts,
)

class Plugin(BaseCheckPlugin):
    TAG = "필수"
    DESCRIPTION = (
        "CAPTION 박스의 부모 존재 여부와 부모 박스 내 CAPTION 개수를 검사합니다."

    )
    CHECK_CAPTION_PARENT_MISSING = True  # CAPTION의 부모 박스 누락 여부 검사
    CHECK_MULTIPLE_CAPTIONS_IN_PARENT = True  # 부모 박스 내부 CAPTION 2개 이상 여부 검사
    MAX_CAPTION_PER_PARENT = 1  # 부모 박스당 허용 가능한 CAPTION 최대 개수

    def run(self, page_context: PageContext) -> CheckResult:
        issues: List[Issue] = []
        json_data = page_context.json_data if isinstance(page_context.json_data, dict) else {}
        shapes = json_data.get("shapes", [])

        if not isinstance(shapes, list) or not shapes:
            return CheckResult(
                check_id=self.PLUGIN_ID,
                status="PASS",
                issues=[],
            )
        parent_boxes: List[Tuple[int, str, Tuple[float, float, float, float]]] = []  # CAPTION ??? ??? ???
        caption_boxes: List[Tuple[int, Tuple[float, float, float, float]]] = []  # CAPTION 박스

        for idx, shape in iter_shape_dicts(json_data):
            label = get_shape_label(shape)
            bbox = get_shape_bbox(shape)
            if bbox is None:
                continue

            if label == "CAPTION":
                caption_boxes.append((idx, bbox))
            else:
                parent_boxes.append((idx, label, bbox))

        parent_to_caption_indices: Dict[int, List[int]] = {
            parent_idx: [] for parent_idx, _, _ in parent_boxes
        }

        for caption_idx, caption_bbox in caption_boxes:
            has_any_parent = False

            for _, _, parent_bbox in parent_boxes:
                if is_bbox_inside(parent_bbox, caption_bbox):
                    has_any_parent = True
                    break

            if self.CHECK_CAPTION_PARENT_MISSING and not has_any_parent:
                issues.append(
                    Issue(
                        shape_index=caption_idx,
                        error_type="CAPTION 부모 박스 누락",
                        error_message="CAPTION을 포함하는 부모 박스 누락",
                        issue_code="CAPTION_PARENT_MISSING",
                    )
                )

            for parent_idx, _parent_label, parent_bbox in parent_boxes:
                if is_bbox_inside(parent_bbox, caption_bbox):
                    parent_to_caption_indices[parent_idx].append(caption_idx)

        if self.CHECK_MULTIPLE_CAPTIONS_IN_PARENT:
            parent_label_map: Dict[int, str] = {
                idx: label for idx, label, _ in parent_boxes
            }

            for parent_idx, caption_idx_list in parent_to_caption_indices.items():
                if len(caption_idx_list) > self.MAX_CAPTION_PER_PARENT:
                    parent_label = parent_label_map.get(parent_idx, "UNKNOWN")
                    issues.append(
                        Issue(
                            shape_index=parent_idx,
                            error_type="부모 박스 내 CAPTION 중복",
                            error_message=(
                                f"{parent_label} 박스 내부 CAPTION {len(caption_idx_list)}개 존재"
                            ),
                            issue_code="MULTIPLE_CAPTIONS_IN_PARENT",
                        )
                    )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
