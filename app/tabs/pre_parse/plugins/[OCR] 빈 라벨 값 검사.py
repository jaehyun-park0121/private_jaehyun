from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from app.tabs.pre_parse.plugin_system.base import BaseCheckPlugin
from app.tabs.pre_parse.plugin_system.context import PageContext
from app.tabs.pre_parse.plugin_system.result_model import CheckResult, Issue
from app.tabs.pre_parse.plugin_system.shape_utils import (
    get_shape_flags,
    get_shape_flags_text,
    get_shape_label,
    iter_shape_dicts,
)


class Plugin(BaseCheckPlugin):
    TAG = "필수"
    DESCRIPTION = (
        "선택한 라벨의 빈 값 여부를 검사합니다.\n"
        "[검사 항목]\n"
        "- flags.text 값이 비어 있는지\n"
        "\n"
        "[라벨 목록]\n"
        "- 저장소 루트 label 폴더의 xlsx 파일에서 id 컬럼을 읽어옵니다.\n"
        "- 파일명은 고정하지 않고 첫 번째 유효한 xlsx를 사용합니다."
    )

    # label 폴더 안에서 첫 번째 유효한 xlsx 경로를 반환하는 함수
    def _get_label_excel_path(self) -> Path | None:
        # 현재 파일 기준 상위 폴더에서 label 폴더 경로를 찾음
        label_dir = Path(__file__).resolve().parents[4] / "label"

        # label 폴더가 없으면 None 반환
        if not label_dir.exists():
            return None

        # 정렬된 xlsx 파일 목록을 순회
        for path in sorted(label_dir.glob("*.xlsx")):
            # 엑셀 임시 파일은 제외
            if path.name.startswith("~$"):
                continue

            # 첫 번째 정상 xlsx 파일 반환
            return path

        # 유효한 파일이 없으면 None 반환
        return None

    # xlsx의 sharedStrings.xml을 읽어 문자열 테이블을 반환하는 함수
    def _read_shared_strings(self, zf: ZipFile) -> list[str]:
        # 결과를 담을 리스트
        shared_strings: list[str] = []

        try:
            # sharedStrings.xml 파일을 엶
            with zf.open("xl/sharedStrings.xml") as file:
                # XML 파싱
                root = ET.parse(file).getroot()
        except KeyError:
            # sharedStrings.xml이 없으면 빈 리스트 반환
            return shared_strings

        # 엑셀 XML 네임스페이스 정의
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        # 모든 shared string 항목을 순회
        for si in root.findall("a:si", ns):
            # 내부 텍스트를 모두 이어 붙임
            texts = [t.text or "" for t in si.findall(".//a:t", ns)]

            # 합친 문자열을 리스트에 추가
            shared_strings.append("".join(texts))

        # 결과 반환
        return shared_strings

    # 첫 번째 워크시트의 xml 경로를 찾는 함수
    def _get_first_sheet_path(self, zf: ZipFile) -> str | None:
        # workbook.xml용 네임스페이스 정의
        ns_main = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        try:
            # workbook.xml 파일을 엶
            with zf.open("xl/workbook.xml") as file:
                # XML 파싱
                workbook_root = ET.parse(file).getroot()
        except KeyError:
            # workbook.xml이 없으면 None 반환
            return None

        # sheets 노드를 찾음
        sheets = workbook_root.find("a:sheets", ns_main)

        # 시트가 없으면 None 반환
        if sheets is None or len(list(sheets)) == 0:
            return None

        # 첫 번째 시트 정보를 가져옴
        first_sheet = list(sheets)[0]

        # 관계 ID를 가져옴
        rel_id = first_sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )

        # 관계 ID가 없으면 None 반환
        if not rel_id:
            return None

        try:
            # workbook.xml.rels 파일을 엶
            with zf.open("xl/_rels/workbook.xml.rels") as file:
                # XML 파싱
                rels_root = ET.parse(file).getroot()
        except KeyError:
            # 관계 파일이 없으면 None 반환
            return None

        # 관계 목록을 순회
        for rel in rels_root:
            # 현재 관계가 첫 번째 시트의 rel_id와 다르면 건너뜀
            if rel.attrib.get("Id") != rel_id:
                continue

            # 대상 파일 경로를 가져옴
            target = rel.attrib.get("Target")

            # 대상 경로가 없으면 None 반환
            if not target:
                return None

            # 경로 구분자를 표준화
            normalized_target = str(target).replace("\\", "/")

            # xl/ 기준 전체 경로 반환
            return f"xl/{normalized_target}"

        # 매칭되는 관계가 없으면 None 반환
        return None

    # 셀 하나의 값을 읽는 함수
    def _get_cell_value(self, cell_elem, shared_strings: list[str]) -> str:
        # 셀 타입을 가져옴
        cell_type = cell_elem.attrib.get("t")

        # 값 노드를 찾음
        value_elem = cell_elem.find(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v"
        )

        # inlineStr 타입이면 별도 처리
        if cell_type == "inlineStr":
            # inline string 본문 노드를 찾음
            is_elem = cell_elem.find(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is"
            )

            # 노드가 없으면 빈 문자열 반환
            if is_elem is None:
                return ""

            # 내부 텍스트를 모두 수집
            texts = [
                t.text or ""
                for t in is_elem.findall(
                    ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                )
            ]

            # 이어 붙여 반환
            return "".join(texts)

        # 값 노드가 없으면 빈 문자열 반환
        if value_elem is None:
            return ""

        # 원시 값을 가져옴
        raw_value = value_elem.text or ""

        # shared string 타입이면 shared_strings 인덱스로 변환
        if cell_type == "s":
            try:
                # shared string 실제 값 반환
                return shared_strings[int(raw_value)]
            except Exception:
                # 인덱스 오류 시 빈 문자열 반환
                return ""

        # 일반 값이면 그대로 반환
        return raw_value

    # 라벨 xlsx에서 id 컬럼 목록을 읽어오는 함수
    def _load_label_ids(self) -> list[str]:
        # 라벨 엑셀 경로를 찾음
        excel_path = self._get_label_excel_path()

        # 경로가 없으면 빈 리스트 반환
        if excel_path is None:
            return []

        try:
            # 엑셀 파일을 zip으로 엶
            with ZipFile(excel_path, "r") as zf:
                # shared strings를 읽음
                shared_strings = self._read_shared_strings(zf)

                # 첫 번째 시트 경로를 찾음
                sheet_path = self._get_first_sheet_path(zf)

                # 시트 경로가 없으면 빈 리스트 반환
                if not sheet_path:
                    return []

                # 시트 xml을 엶
                with zf.open(sheet_path) as file:
                    # XML 파싱
                    sheet_root = ET.parse(file).getroot()
        except Exception:
            # 읽기 실패 시 빈 리스트 반환
            return []

        # 엑셀 시트 네임스페이스 정의
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        # 모든 row를 찾음
        rows = sheet_root.findall(".//a:sheetData/a:row", ns)

        # row가 없으면 빈 리스트 반환
        if not rows:
            return []

        # 헤더 행의 셀 목록을 가져옴
        header_cells = rows[0].findall("a:c", ns)

        # 헤더 값을 소문자로 읽음
        headers = [
            self._get_cell_value(cell, shared_strings).strip().lower()
            for cell in header_cells
        ]

        # id 컬럼이 없으면 빈 리스트 반환
        if "id" not in headers:
            return []

        # id 컬럼 인덱스를 찾음
        id_col_index = headers.index("id")

        # 결과 라벨 리스트 초기화
        label_ids: list[str] = []

        # 데이터 행을 순회
        for row in rows[1:]:
            # 행의 셀 목록을 가져옴
            cells = row.findall("a:c", ns)

            # 셀 값들을 읽음
            values = [self._get_cell_value(cell, shared_strings) for cell in cells]

            # id 컬럼이 없는 짧은 행이면 건너뜀
            if id_col_index >= len(values):
                continue

            # id 값을 대문자로 정리
            item = str(values[id_col_index]).strip().upper()

            # 값이 있고 아직 추가되지 않았다면 리스트에 추가
            if item and item not in label_ids:
                label_ids.append(item)

        # 라벨 목록 반환
        return label_ids

    # 옵션 스키마 정의
    def option_schema(self):
        # 검사 대상 라벨을 버튼형 멀티 선택으로 제공
        return [
            {
                "key": "target_labels",
                "label": "검사 대상 라벨",
                "type": "multi_select_buttons",
                "choices": self._load_label_ids(),
                "default": [],
                "columns": 3,
            }
        ]

    # 실제 검사 실행 함수
    def run(self, page_context: PageContext) -> CheckResult:
        # 오류 목록 초기화
        issues = []

        # shapes 목록을 가져옴
        shapes = page_context.json_data.get("shapes", [])

        # shapes가 리스트가 아니거나 비어 있으면 PASS 반환
        if not isinstance(shapes, list) or not shapes:
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        # 현재 플러그인 옵션을 가져옴
        options = (
            page_context.config.get(self.PLUGIN_ID, {})
            if isinstance(page_context.config, dict)
            else {}
        )

        # 선택한 라벨 목록을 가져옴
        selected_labels = options.get("target_labels", [])

        # 리스트가 아니면 빈 리스트로 보정
        if not isinstance(selected_labels, list):
            selected_labels = []

        # 공백 제거 및 대문자 통일 후 집합으로 변환
        selected_labels = {
            str(label).strip().upper()
            for label in selected_labels
            if str(label).strip()
        }

        # 선택 라벨이 없으면 PASS 반환
        if not selected_labels:
            return CheckResult(check_id=self.PLUGIN_ID, status="PASS", issues=[])

        # 모든 shape를 순회
        for idx, shape in iter_shape_dicts(page_context.json_data):
            # 라벨을 대문자로 통일
            label_upper = get_shape_label(shape)

            # 선택한 검사 대상 라벨이 아니면 건너뜀
            if label_upper not in selected_labels:
                continue

            # flags 값을 가져옴
            flags = get_shape_flags(shape)

            # flags가 dict일 때만 검사
            if not flags and not isinstance(shape.get("flags"), dict):
                continue

            # flags.text 값이 빈 문자열 또는 공백뿐인지 검사
            if get_shape_flags_text(shape).strip() == "":
                # 빈 값 오류를 추가
                issues.append(
                    Issue(
                        issue_code="EMPTY_LABEL",
                        shape_index=idx,
                        error_type=label_upper,
                        error_message=f"{label_upper} 라벨 flags.text 비어 있음"
                    )
                )

        return CheckResult(
            check_id=self.PLUGIN_ID,
            status="FAIL" if issues else "PASS",
            issues=issues,
        )
