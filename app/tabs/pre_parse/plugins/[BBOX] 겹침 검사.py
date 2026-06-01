from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    bbox_area,
    bbox_intersection_area,
    get_shape_bbox,
    get_shape_label,
    iter_shape_dicts,
)



class Plugin(BaseCheckPlugin):  # pre_parse 겹침 검사 플러그인 정의
    TAG = "선택"  # UI에 표시될 플러그인 분류명
    DESCRIPTION = (
        "라벨 간 pre_parse 겹침을 검사합니다.\n"
        "교집합 면적을 각 박스 면적으로 나눈 비율로 판정합니다."
    )

    VALID_LABELS = {"TEXT", "FORMULA", "TABLE", "FOOTNOTE", "IMAGE", "CHART", "TITLE"}  # 검사 대상 라벨 정의

    def option_schema(self):  # 옵션 UI 스키마 정의
        return [
            {
                "key": "overlap_min_threshold",  # 겹침 비율 하한값 key
                "label": "이상",  # 옵션 라벨명
                "type": "text",  # 입력 타입
                "default": "0.80",  # 기본값
                "placeholder": "예: 0.80",  # 플레이스홀더
            },
            {
                "key": "overlap_max_threshold",  # 겹침 비율 상한값 key
                "label": "미만",  # 옵션 라벨명
                "type": "text",  # 입력 타입
                "default": "1.00",  # 기본값
                "placeholder": "예: 1.00",  # 플레이스홀더
            },
        ]

    def run(self, page_context: PageContext) -> CheckResult:  # 페이지 단위 검사 실행
        issues: List[Issue] = []  # 오류 결과를 담을 리스트 초기화
        json_data = page_context.json_data if isinstance(page_context.json_data, dict) else {}  # json_data 안전 확인
        shapes = json_data.get("shapes", [])  # 현재 페이지의 shapes 목록 조회
        options = page_context.config.get(self.PLUGIN_ID, {}) if isinstance(page_context.config, dict) else {}  # 플러그인 옵션 조회

        min_threshold, max_threshold, include_max_threshold = self._parse_threshold_range(
            min_value=options.get("overlap_min_threshold", "0.80"),
            max_value=options.get("overlap_max_threshold", "1.00"),
            default_min=0.80,
            default_max=1.00,
        )  # 구간 기준값 파싱

        if not isinstance(shapes, list):  # shapes가 리스트가 아니면 검사 종료
            return CheckResult(
                check_id=self.PLUGIN_ID,  # 검사 ID 설정
                status="PASS",  # 검사 통과 처리
                issues=[],  # 이슈 없음
            )

        candidates: List[Tuple[int, Tuple[float, float, float, float], str]] = []  # 검사 대상 pre_parse/라벨 저장 리스트

        for idx, shape in iter_shape_dicts(json_data):  # 모든 shape 순회
            label = get_shape_label(shape)  # 라벨 값 추출
            if label not in self.VALID_LABELS:  # 검사 대상 라벨만 유지
                continue

            box = get_shape_bbox(shape)  # points를 bbox로 변환
            if box is None:  # pre_parse 변환 실패 시 제외
                continue

            candidates.append((idx, box, label))  # 검사 대상 목록에 추가

        for i in range(len(candidates)):  # 첫 번째 박스 index 순회
            idx1, box1, label1 = candidates[i]  # 첫 번째 후보 언패킹

            for j in range(i + 1, len(candidates)):  # 두 번째 박스 index 순회
                idx2, box2, label2 = candidates[j]  # 두 번째 후보 언패킹

                inter_area = bbox_intersection_area(box1, box2)  # 두 박스 간 교집합 면적 계산
                if inter_area <= 0.0:  # 겹치는 영역이 없으면 검사 제외
                    continue

                area1 = bbox_area(box1)  # 첫 번째 박스 면적 계산
                area2 = bbox_area(box2)  # 두 번째 박스 면적 계산
                if area1 <= 0.0 or area2 <= 0.0:  # 면적이 비정상이면 검사 제외
                    continue

                overlap_ratio_1 = inter_area / area1  # 첫 번째 박스 기준 겹침 비율 계산
                overlap_ratio_2 = inter_area / area2  # 두 번째 박스 기준 겹침 비율 계산

                matched_1 = self._is_in_range(
                    overlap_ratio_1,
                    min_threshold,
                    max_threshold,
                    include_max_threshold,
                )  # 첫 번째 박스 기준 조건 판정
                matched_2 = self._is_in_range(
                    overlap_ratio_2,
                    min_threshold,
                    max_threshold,
                    include_max_threshold,
                )  # 두 번째 박스 기준 조건 판정

                if not (matched_1 or matched_2):  # 둘 중 하나도 조건을 만족하지 않으면 오류 아님
                    continue

                overlap_score = self._select_overlap_score(
                    overlap_ratio_1,
                    overlap_ratio_2,
                    min_threshold,
                    max_threshold,
                    include_max_threshold,
                )
                overlap_score_text = self._format_overlap_score(overlap_score)
                error_type = f"겹침 수치 {overlap_score_text}"
                message = f"({label1}/{label2}) 겹침 수치 {overlap_score_text}"




                issues.append(  # 첫 번째 박스 이슈 추가
                    Issue(
                        shape_index=idx1,  # 오류가 발생한 첫 번째 shape 인덱스
                        error_type=error_type,  # 오류 유형명
                        error_message=message,  # 세부 오류 메시지
                        issue_code="BBOX_OVERLAP_RATIO",  # 내부 식별용 코드
                    )
                )

                issues.append(  # 두 번째 박스 이슈 추가
                    Issue(
                        shape_index=idx2,  # 오류가 발생한 두 번째 shape 인덱스
                        error_type=error_type,  # 오류 유형명
                        error_message=message,  # 세부 오류 메시지
                        issue_code="BBOX_OVERLAP_RATIO",  # 내부 식별용 코드
                    )
                )

        return CheckResult(
            check_id=self.PLUGIN_ID,  # 플러그인 검사 ID 반환
            status="FAIL" if issues else "PASS",  # 오류 존재 여부에 따라 상태 결정
            issues=issues,  # 오류 목록 반환
        )

    def _parse_threshold(self, value, default: float) -> float:  # threshold 문자열을 float로 안전 변환
        try:  # float 변환 시도
            threshold = float(value)  # 문자열을 float로 변환
        except (TypeError, ValueError):  # 변환 실패 시
            threshold = default  # 기본값 사용

        if threshold < 0.0:  # 하한 보정
            threshold = 0.0
        if threshold > 1.0:  # 상한 보정
            threshold = 1.0

        return threshold  # 최종 threshold 반환

    def _parse_threshold_range(
        self,
        *,
        min_value,
        max_value,
        default_min: float,
        default_max: float,
    ) -> Tuple[float, float, bool]:
        min_threshold = self._parse_threshold(min_value, default=default_min)
        raw_max_threshold = self._parse_raw_threshold(max_value, default=default_max)
        max_threshold = self._parse_threshold(max_value, default=default_max)
        include_max_threshold = raw_max_threshold > 1.0

        if max_threshold < min_threshold:
            return (default_min, default_max, default_max >= 1.0)

        if max_threshold == min_threshold and not include_max_threshold:
            return (default_min, default_max, default_max >= 1.0)

        return (min_threshold, max_threshold, include_max_threshold)

    def _parse_raw_threshold(self, value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _is_in_range(
        self,
        value: float,
        min_threshold: float,
        max_threshold: float,
        include_max_threshold: bool,
    ) -> bool:
        if include_max_threshold:
            return min_threshold <= value <= max_threshold
        return min_threshold <= value < max_threshold

    def _select_overlap_score(
        self,
        ratio_1: float,
        ratio_2: float,
        min_threshold: float,
        max_threshold: float,
        include_max_threshold: bool,
    ) -> float:
        matched_values = [
            value
            for value in (ratio_1, ratio_2)
            if self._is_in_range(value, min_threshold, max_threshold, include_max_threshold)
        ]
        if matched_values:
            return max(matched_values)
        return max(ratio_1, ratio_2)

    def _format_overlap_score(self, value: float) -> str:
        return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

