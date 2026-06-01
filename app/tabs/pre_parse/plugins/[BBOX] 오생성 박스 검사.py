from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    bbox_area,
    bbox_intersection_area,
    get_bbox_from_points,
    get_shape_label,
    iter_shape_dicts,
    normalize_points,
)


class Plugin(BaseCheckPlugin):
    TAG = "선택"
    DESCRIPTION = (
        "오생성 박스를 검사합니다.\n"
        "[검사 항목]\n"
        "- 기준 면적보다 작은 박스\n"
        "- 페이지 밖에 있는 박스\n"
        "- imageWidth, imageHeight 정보 누락\n"
        "\n"
        "[작은 박스 기준]\n"
        "- 기본 기준 박스 크기: 15px × 10px\n"
        "- 기준 면적: 150px²\n"
        "- 입력칸에는 기준 면적값만 숫자로 입력합니다.\n"
        "- 값을 입력하지 않으면 기본값 150px²로 검사합니다.\n"
        "\n"
        "[기준 면적 값 입력 방법]\n"
        "- 박스의 좌표 값 [x2 - x1],[y2 - y1]의 면적을 px²로 계산하여 입력합니다\n"
        "- 예시: 15px × 10px = 150px² → 입력칸에 '150'으로 입력\n"
        "\n"
        "[판정 방식]\n"
        "- 일부 면적이라도 페이지 외부에 존재: 박스 면적 중 페이지 밖 영역이 조금이라도 있으면 오류\n"
        "- 전체 면적이 페이지 외부에 존재: 박스 면적 전체가 페이지 밖에 있을 때만 오류"
    )

    DEFAULT_MIN_BOX_WIDTH_PX = 15.0
    DEFAULT_MIN_BOX_HEIGHT_PX = 10.0
    DEFAULT_MIN_BOX_AREA_PX2 = DEFAULT_MIN_BOX_WIDTH_PX * DEFAULT_MIN_BOX_HEIGHT_PX

    def _compute_bbox(self, normalized_points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
        bbox = get_bbox_from_points(normalized_points)
        if bbox is None:
            return (0.0, 0.0, 0.0, 0.0)
        return bbox

    def _compute_outside_area(
        self,
        box: tuple[float, float, float, float],
        page_width: float,
        page_height: float,
    ) -> tuple[float, float]:
        if page_width <= 0 or page_height <= 0:
            return (0.0, 0.0)

        box_area = bbox_area(box)
        if box_area <= 0.0:
            return (0.0, 0.0)

        page_box = (0.0, 0.0, page_width, page_height)
        inside_area = bbox_intersection_area(box, page_box)
        inside_area = min(max(inside_area, 0.0), box_area)
        outside_area = max(0.0, box_area - inside_area)
        return (inside_area, outside_area)

    def _evaluate_out_of_page(
        self,
        box: tuple[float, float, float, float],
        page_width: float,
        page_height: float,
        outside_mode: str,
    ) -> tuple[bool, float, float]:
        box_area = bbox_area(box)
        if box_area <= 0.0:
            return (False, 0.0, 0.0)

        inside_area, outside_area = self._compute_outside_area(
            box=box,
            page_width=page_width,
            page_height=page_height,
        )
        eps = 1e-6

        if outside_mode == "일부 면적이라도 페이지 외부에 존재":
            return (outside_area > eps, outside_area, box_area)

        if outside_mode == "전체 면적이 페이지 외부에 존재":
            return (inside_area <= eps, outside_area, box_area)

        return (outside_area > eps, outside_area, box_area)

    # 체크박스는 제거하고, 면적 기준과 판정 방식만 노출
    def option_schema(self):
        return [
            {
                "key": "min_box_area_px2",
                "label": "면적 기준(px²)",
                "type": "text",
                "default": str(self.DEFAULT_MIN_BOX_AREA_PX2),
                "placeholder": f"기본값: {self.DEFAULT_MIN_BOX_AREA_PX2}",
            },
            {
                "key": "outside_mode",
                "label": "판정 방식",
                "type": "select",
                "choices": ["일부 면적이라도 페이지 외부에 존재", "전체 면적이 페이지 외부에 존재"],
                "default": "일부 면적이라도 페이지 외부에 존재",
                "placeholder": "판정 방식을 선택하세요.",
            },
        ]

    def run(self, page_context: PageContext) -> CheckResult:
        issues = []
        json_data = page_context.json_data if isinstance(page_context.json_data, dict) else {}
        page_width = float(json_data.get("imageWidth", 0) or 0)
        page_height = float(json_data.get("imageHeight", 0) or 0)
        has_page_size = page_width > 0 and page_height > 0

        if not has_page_size:
            issues.append(
                Issue(
                    shape_index=-1,
                    error_type="페이지 크기 정보 누락",
                    error_message="imageWidth, imageHeight 정보 존재하지 않음",
                    issue_code="IMAGE_SIZE_MISSING",
                )
            )

        shapes = json_data.get("shapes", [])

        if not isinstance(shapes, list) or not shapes:
            return CheckResult(
                check_id=self.PLUGIN_ID,
                status="FAIL" if issues else "PASS",
                issues=issues,
            )

        # 작은 박스 검사와 페이지 밖 박스 검사는 항상 수행
        options = page_context.config.get(self.PLUGIN_ID, {}) if isinstance(page_context.config, dict) else {}
        outside_mode = str(
            options.get("outside_mode", "일부 면적이라도 페이지 외부에 존재") or "일부 면적이라도 페이지 외부에 존재"
        ).strip()

        # 입력이 비어 있으면 default 값으로 검사, 입력이 있으면 입력값으로 검사
        raw_min_box_area = options.get("min_box_area_px2", self.DEFAULT_MIN_BOX_AREA_PX2)
        if raw_min_box_area is None or str(raw_min_box_area).strip() == "":
            min_box_area_px2 = self.DEFAULT_MIN_BOX_AREA_PX2
        else:
            try:
                min_box_area_px2 = float(str(raw_min_box_area).strip())
            except (TypeError, ValueError):
                min_box_area_px2 = self.DEFAULT_MIN_BOX_AREA_PX2

        min_box_area_px2 = max(0.0, min_box_area_px2)

        # 각 shape에 대해 작은 박스 검사 후 페이지 밖 박스 검사를 수행
        for idx, shape in iter_shape_dicts(page_context.json_data):
            label_upper = get_shape_label(shape) or "UNKNOWN"
            normalized_points = normalize_points(shape.get("points", []))

            if not normalized_points:
                continue

            x1, y1, x2, y2 = self._compute_bbox(normalized_points)
            box_width = max(0.0, x2 - x1)
            box_height = max(0.0, y2 - y1)
            box_area = box_width * box_height

            if box_area <= min_box_area_px2:
                issues.append(
                    Issue(
                        shape_index=idx,
                        error_type="작은 박스 오류",
                        error_message=(
                            f"{label_upper} 박스 면적 기준 이하 ({box_area:.2f}px²)"
                        ),
                        issue_code="SMALL_BOX",
                    )
                )
                continue

            if has_page_size:
                is_out_of_page, outside_area, total_box_area = self._evaluate_out_of_page(
                    box=(x1, y1, x2, y2),
                    page_width=page_width,
                    page_height=page_height,
                    outside_mode=outside_mode,
                )

                if is_out_of_page:
                    issues.append(
                        Issue(
                            shape_index=idx,
                            error_type="페이지 밖 박스 오류",
                            error_message=(
                                f"{label_upper} 박스 페이지 범위 벗어남 "
                                f"({outside_area:.2f}px²/{total_box_area:.2f}px²)"
                            ),
                            issue_code="BOX_OUT_OF_PAGE",
                        )
                    )
                    continue

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
