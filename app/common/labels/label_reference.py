from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Dict, List
from zipfile import ZipFile
import xml.etree.ElementTree as ET


_MAIN_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _usable_xlsx_path(project_root: Path) -> Path | None:
    label_dir = project_root / "label"
    if not label_dir.exists():
        return None

    for path in sorted(label_dir.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        return path
    return None


def _read_shared_strings(zf: ZipFile) -> List[str]:
    strings: List[str] = []
    try:
        with zf.open("xl/sharedStrings.xml") as file:
            root = ET.parse(file).getroot()
    except KeyError:
        return strings

    for item in root.findall("a:si", _MAIN_NS):
        parts: List[str] = []
        for text in item.findall(".//a:t", _MAIN_NS):
            parts.append(text.text or "")
        strings.append("".join(parts))
    return strings


def _first_sheet_path(zf: ZipFile) -> str | None:
    try:
        with zf.open("xl/workbook.xml") as file:
            workbook_root = ET.parse(file).getroot()
    except KeyError:
        return None

    sheets = workbook_root.find("a:sheets", _MAIN_NS)
    if sheets is None:
        return None
    first_sheet = next(iter(list(sheets)), None)
    if first_sheet is None:
        return None

    rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    if not rel_id:
        return None

    try:
        with zf.open("xl/_rels/workbook.xml.rels") as file:
            rels_root = ET.parse(file).getroot()
    except KeyError:
        return None

    for rel in rels_root:
        if rel.attrib.get("Id") != rel_id:
            continue
        target = str(rel.attrib.get("Target", "")).replace("\\", "/").strip()
        if not target:
            return None
        return f"xl/{target}"
    return None


def _cell_value(cell_elem, shared_strings: List[str]) -> str:
    cell_type = cell_elem.attrib.get("t")
    value_elem = cell_elem.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")

    if cell_type == "inlineStr":
        is_elem = cell_elem.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is")
        if is_elem is None:
            return ""
        parts = []
        for text in is_elem.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
            parts.append(text.text or "")
        return "".join(parts)

    if value_elem is None:
        return ""

    raw_value = value_elem.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except Exception:
            return ""
    return raw_value


def _normalize_color(value: str) -> str:
    color = str(value or "").strip()
    if not color:
        return ""
    if color.startswith("#") and len(color) == 7:
        return color
    if len(color) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in color):
        return f"#{color}"
    return ""


def load_label_ids(project_root: Path) -> List[str]:
    xlsx_path = _usable_xlsx_path(project_root)
    if xlsx_path is None:
        return []

    try:
        with ZipFile(xlsx_path, "r") as zf:
            shared_strings = _read_shared_strings(zf)
            sheet_path = _first_sheet_path(zf)
            if not sheet_path:
                return []
            with zf.open(sheet_path) as file:
                sheet_root = ET.parse(file).getroot()
    except Exception:
        return []

    rows = sheet_root.findall(".//a:sheetData/a:row", _MAIN_NS)
    if not rows:
        return []

    header_cells = rows[0].findall("a:c", _MAIN_NS)
    header = [_cell_value(cell, shared_strings).strip().lower() for cell in header_cells]
    try:
        id_idx = header.index("id")
    except ValueError:
        return []

    label_ids: List[str] = []
    seen: set[str] = set()
    for row in rows[1:]:
        cells = row.findall("a:c", _MAIN_NS)
        values = [_cell_value(cell, shared_strings) for cell in cells]
        if id_idx >= len(values):
            continue
        label_id = str(values[id_idx]).strip().upper()
        if not label_id or label_id in seen:
            continue
        seen.add(label_id)
        label_ids.append(label_id)
    return label_ids


def load_label_entries(project_root: Path) -> List[dict]:
    """xlsx 첫 번째 시트에서 라벨 정보를 읽어 반환합니다.

    반환값: List[{"id": str, "title": str, "is_text_analysis": bool}]
    - id: 라벨 ID (대문자, e.g. "TEXT")
    - title: 표시 이름 (e.g. "텍스트")
    - is_text_analysis: flags 옵션 JSON에 {"id": "text"}가 있으면 True
                        (CHART처럼 RADIO 선택형은 False)

    load_text_label_options 와 동일하게 openpyxl 우선, 실패 시 ZipFile/XML 폴백.
    """
    xlsx_path = _usable_xlsx_path(project_root)
    if xlsx_path is None:
        return []

    raw_rows: List[tuple] = []

    # openpyxl 우선 (load_text_label_options 와 동일한 패턴 — 이 xlsx 에서 안정적으로 동작)
    try:
        from openpyxl import load_workbook  # type: ignore
        wb = load_workbook(xlsx_path, data_only=True, read_only=True)
        try:
            raw_rows = list(wb.worksheets[0].iter_rows(values_only=True))
        finally:
            wb.close()
    except ImportError:
        pass
    except Exception:
        pass

    # openpyxl 실패 시 ZipFile/XML 폴백
    if not raw_rows:
        try:
            with ZipFile(xlsx_path, "r") as zf:
                shared_strings = _read_shared_strings(zf)
                sheet_path = _first_sheet_path(zf)
                if not sheet_path:
                    return []
                with zf.open(sheet_path) as file:
                    sheet_root = ET.parse(file).getroot()
            xml_rows = sheet_root.findall(".//a:sheetData/a:row", _MAIN_NS)
            for xml_row in xml_rows:
                cells = xml_row.findall("a:c", _MAIN_NS)
                raw_rows.append(tuple(_cell_value(c, shared_strings) for c in cells))
        except Exception:
            return []

    if not raw_rows:
        return []

    # 첫 행이 헤더 행인지 자동 감지
    first_row_lower = [str(v or "").strip().lower() for v in raw_rows[0]]
    _ID_CANDS = ("id", "label id", "label_id", "category id", "category_id", "code")
    _TITLE_CANDS = ("title", "label title", "name", "label", "라벨", "라벨명", "카테고리", "카테고리명")
    _OPT_CANDS = ("options", "flags", "flag", "schema", "annotation")

    id_idx = next((i for i, v in enumerate(first_row_lower) if v in _ID_CANDS), -1)

    if id_idx >= 0:
        # 헤더 행 있음
        data_start = 1
        title_idx = next((i for i, v in enumerate(first_row_lower) if v in _TITLE_CANDS), -1)
        options_idx = next((i for i, v in enumerate(first_row_lower) if v in _OPT_CANDS), -1)
        if options_idx < 0 and len(first_row_lower) >= 5:
            options_idx = len(first_row_lower) - 1
    else:
        # 헤더 없음 → 고정 컬럼 위치: 0=id, 1=title, 4=options JSON
        data_start = 0
        id_idx, title_idx = 0, 1
        options_idx = 4 if len(first_row_lower) >= 5 else -1

    entries: List[dict] = []
    seen: set = set()

    for row in raw_rows[data_start:]:
        if not row:
            continue
        row_vals = [str(v or "").strip() for v in row]

        if id_idx >= len(row_vals):
            continue
        label_id = row_vals[id_idx].upper()
        if not label_id or label_id in seen or label_id.lower() in _ID_CANDS:
            continue
        seen.add(label_id)

        title = row_vals[title_idx] if 0 <= title_idx < len(row_vals) else ""

        is_text_analysis = True
        if 0 <= options_idx < len(row_vals):
            options_str = row_vals[options_idx]
            if options_str:
                try:
                    opts = _json.loads(options_str)
                    is_text_analysis = any(
                        isinstance(o, dict) and str(o.get("id", "")).strip().lower() == "text"
                        for o in opts
                    )
                except Exception:
                    pass

        entries.append({
            "id": label_id,
            "title": title or label_id,
            "is_text_analysis": is_text_analysis,
        })

    return entries


def load_label_color_map(project_root: Path) -> Dict[str, str]:
    xlsx_path = _usable_xlsx_path(project_root)
    if xlsx_path is None:
        return {}

    try:
        with ZipFile(xlsx_path, "r") as zf:
            shared_strings = _read_shared_strings(zf)
            sheet_path = _first_sheet_path(zf)
            if not sheet_path:
                return {}
            with zf.open(sheet_path) as file:
                sheet_root = ET.parse(file).getroot()
    except Exception:
        return {}

    rows = sheet_root.findall(".//a:sheetData/a:row", _MAIN_NS)
    if not rows:
        return {}

    header_cells = rows[0].findall("a:c", _MAIN_NS)
    header = [_cell_value(cell, shared_strings).strip().lower() for cell in header_cells]
    try:
        id_idx = header.index("id")
        color_idx = header.index("color")
    except ValueError:
        return {}

    color_map: Dict[str, str] = {}
    for row in rows[1:]:
        cells = row.findall("a:c", _MAIN_NS)
        values = [_cell_value(cell, shared_strings) for cell in cells]
        if id_idx >= len(values) or color_idx >= len(values):
            continue
        key = str(values[id_idx]).strip().upper()
        color = _normalize_color(values[color_idx])
        if not key or not color:
            continue
        color_map[key] = color
    return color_map
