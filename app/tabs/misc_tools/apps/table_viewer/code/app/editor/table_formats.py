"""표 원본 포맷(HTML/Markdown) 변환 유틸."""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import json
import re
from typing import Any


TABLE_FORMAT_HTML = "html"
TABLE_FORMAT_MARKDOWN = "markdown"
TABLE_FORMAT_LABELS = {
    TABLE_FORMAT_HTML: "HTML",
    TABLE_FORMAT_MARKDOWN: "Markdown",
}
TABLE_SPANS_ATTR = "table_spans"

_BR_RE = re.compile(r"(?i)<br\s*/?>")
_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")


class TableFormatError(ValueError):
    """표 포맷 변환/파싱 실패."""


def render_source_to_html(
    source_text: str,
    table_format: str,
    spans: list[dict[str, int]] | None = None,
) -> str:
    """원본 포맷 문자열을 렌더링 가능한 HTML 테이블 문자열로 변환."""
    text = (source_text or "").strip()
    if not text:
        return ""
    if table_format == TABLE_FORMAT_HTML:
        return text
    if table_format == TABLE_FORMAT_MARKDOWN:
        return markdown_to_html(text, spans=spans)
    raise TableFormatError(f"지원하지 않는 표 포맷입니다: {table_format}")


def render_html_to_source(table_html: str, table_format: str) -> str:
    """렌더링/편집 결과 HTML을 현재 원본 포맷 문자열로 되돌린다."""
    text, _spans = render_html_to_source_and_spans(table_html, table_format)
    return text


def format_source_pretty(source_text: str, table_format: str) -> str:
    """소스 탭에서 보기 좋게 정렬할 문자열을 만든다."""
    if table_format == TABLE_FORMAT_HTML:
        return format_html_pretty(source_text)
    if table_format == TABLE_FORMAT_MARKDOWN:
        return format_markdown_pretty(source_text)
    raise TableFormatError(f"지원하지 않는 표 포맷입니다: {table_format}")


def format_html_pretty(source_text: str) -> str:
    text = (source_text or "").strip()
    if not text:
        return ""
    parser = _PrettyHTMLParser()
    parser.feed(text)
    parser.close()
    return parser.result()


def format_markdown_pretty(source_text: str) -> str:
    lines = [line.strip() for line in (source_text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) < 2:
        raise TableFormatError("Markdown 표는 헤더 행과 구분선이 필요합니다.")

    rows = [_split_markdown_row(line) for line in lines]
    separator = rows[1]
    if not separator or not all(_SEPARATOR_RE.fullmatch(cell.strip()) for cell in separator):
        raise TableFormatError("두 번째 줄은 `| --- | --- |` 형태의 구분선이어야 합니다.")

    width = max(len(row) for row in rows)
    normalized = [_pad_cells(row, width) for row in rows]
    rendered_rows = [[_render_markdown_cell(cell) for cell in row] for row in normalized]
    col_widths = [
        max(
            3,
            max(len(rendered_rows[row_idx][col_idx]) for row_idx in range(len(rendered_rows))),
        )
        for col_idx in range(width)
    ]

    pretty_lines = [_format_pretty_markdown_row(rendered_rows[0], col_widths)]
    pretty_lines.append(_format_pretty_separator_row(separator, col_widths))
    pretty_lines.extend(
        _format_pretty_markdown_row(row, col_widths)
        for row in rendered_rows[2:]
    )
    return "\n".join(pretty_lines)


def render_html_to_source_and_spans(
    table_html: str,
    table_format: str,
) -> tuple[str, list[dict[str, int]]]:
    """렌더링/편집 결과 HTML을 원본 문자열과 Markdown 병합 메타로 분리한다."""
    html = (table_html or "").strip()
    if not html:
        return "", []
    if table_format == TABLE_FORMAT_HTML:
        return html, []
    if table_format == TABLE_FORMAT_MARKDOWN:
        return html_to_markdown_with_spans(html)
    raise TableFormatError(f"지원하지 않는 표 포맷입니다: {table_format}")


def spans_from_attr(value: Any) -> list[dict[str, int]]:
    """attributes['table_spans'] 문자열을 span 목록으로 파싱."""
    if not value:
        return []
    if not isinstance(value, str):
        raise TableFormatError("table_spans attributes 값은 JSON 문자열이어야 합니다.")
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise TableFormatError(f"table_spans JSON 파싱 실패: {exc}") from exc
    if not isinstance(raw, list):
        raise TableFormatError("table_spans 값은 배열이어야 합니다.")
    spans: list[dict[str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TableFormatError("table_spans 항목은 객체여야 합니다.")
        try:
            span = {
                "row": int(item["row"]),
                "col": int(item["col"]),
                "rowspan": int(item.get("rowspan", 1)),
                "colspan": int(item.get("colspan", 1)),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise TableFormatError("table_spans 항목 형식이 올바르지 않습니다.") from exc
        spans.append(span)
    return spans


def spans_to_attr(spans: list[dict[str, int]] | None) -> str:
    """span 목록을 attributes에 넣을 str:str용 JSON 문자열로 직렬화."""
    normalized = [
        {
            "row": int(span["row"]),
            "col": int(span["col"]),
            "rowspan": int(span.get("rowspan", 1)),
            "colspan": int(span.get("colspan", 1)),
        }
        for span in (spans or [])
        if int(span.get("rowspan", 1)) > 1 or int(span.get("colspan", 1)) > 1
    ]
    if not normalized:
        return ""
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def markdown_to_html(
    markdown_text: str,
    spans: list[dict[str, int]] | None = None,
) -> str:
    """GitHub 스타일 기본 Markdown 표를 HTML 테이블로 변환."""
    rows = _parse_markdown_table(markdown_text)
    if not rows:
        return ""

    width = max(len(row) for row in rows)
    normalized = [_pad_cells(row, width) for row in rows]
    span_map, covered = _build_span_maps(spans or [], len(normalized), width)

    row_html: list[str] = []
    for row_idx, row in enumerate(normalized):
        tag = "th" if row_idx == 0 else "td"
        cells: list[str] = []
        for col_idx, cell in enumerate(row):
            if (row_idx, col_idx) in covered:
                continue
            span = span_map.get((row_idx, col_idx), {"rowspan": 1, "colspan": 1})
            flat_cells = _covered_flat_cells(normalized, row_idx, col_idx, span)
            attrs = _span_attrs(span, flat_cells, cell)
            cells.append(f"<{tag}{attrs}>{_markdown_cell_to_html(cell)}</{tag}>")
        row_html.append("<tr>" + "".join(cells) + "</tr>")

    if _has_header_rowspan(span_map):
        return f"<table><tbody>{''.join(row_html)}</tbody></table>"

    thead = "<thead>" + row_html[0] + "</thead>"
    tbody = "<tbody>" + "".join(row_html[1:]) + "</tbody>" if len(row_html) > 1 else ""
    return f"<table>{thead}{tbody}</table>"


def html_to_markdown(table_html: str) -> str:
    """HTML 테이블을 평탄화 Markdown 표로 직렬화."""
    markdown, _spans = html_to_markdown_with_spans(table_html)
    return markdown


def html_to_markdown_with_spans(table_html: str) -> tuple[str, list[dict[str, int]]]:
    """HTML 테이블을 평탄화 Markdown 표와 병합 메타로 분리."""
    parser = _SimpleTableHTMLParser()
    parser.feed(table_html)
    parser.close()

    parsed_rows = parser.rows
    if not parsed_rows:
        return "", []

    grid, spans = _flatten_html_rows(parsed_rows)
    if not grid:
        return "", []

    width = max(len(row) for row in grid)
    normalized = [_pad_cells(row, width) for row in grid]

    lines = [
        _format_markdown_row(normalized[0]),
        _format_markdown_row(["---"] * width),
    ]
    lines.extend(_format_markdown_row(row) for row in normalized[1:])
    return "\n".join(lines), spans


def _parse_markdown_table(markdown_text: str) -> list[list[str]]:
    lines = [line.strip() for line in (markdown_text or "").splitlines() if line.strip()]
    if not lines:
        return []
    if len(lines) < 2:
        raise TableFormatError("Markdown 표는 헤더 행과 구분선이 필요합니다.")

    rows = [_split_markdown_row(line) for line in lines]
    separator = rows[1]
    if not separator or not all(_SEPARATOR_RE.fullmatch(cell.strip()) for cell in separator):
        raise TableFormatError("두 번째 줄은 `| --- | --- |` 형태의 구분선이어야 합니다.")

    data_rows = [rows[0], *rows[2:]]
    if not data_rows[0]:
        raise TableFormatError("Markdown 표 헤더가 비어 있습니다.")
    return data_rows


def _split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]

    cells: list[str] = []
    buf: list[str] = []
    escape_next = False
    for ch in text:
        if escape_next:
            buf.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if escape_next:
        buf.append("\\")
    cells.append("".join(buf).strip())
    return cells


def _build_span_maps(
    spans: list[dict[str, int]],
    row_count: int,
    col_count: int,
) -> tuple[dict[tuple[int, int], dict[str, int]], set[tuple[int, int]]]:
    span_map: dict[tuple[int, int], dict[str, int]] = {}
    occupied: dict[tuple[int, int], tuple[int, int]] = {}

    for raw_span in spans:
        row = int(raw_span["row"])
        col = int(raw_span["col"])
        rowspan = int(raw_span.get("rowspan", 1))
        colspan = int(raw_span.get("colspan", 1))
        if row < 0 or col < 0 or rowspan < 1 or colspan < 1:
            raise TableFormatError("table_spans에 음수 좌표나 0 크기 병합이 있습니다.")
        if row + rowspan > row_count or col + colspan > col_count:
            raise TableFormatError("table_spans가 Markdown 표 범위를 벗어났습니다.")
        if rowspan == 1 and colspan == 1:
            continue

        anchor = (row, col)
        span = {"row": row, "col": col, "rowspan": rowspan, "colspan": colspan}
        span_map[anchor] = span
        for rr in range(row, row + rowspan):
            for cc in range(col, col + colspan):
                pos = (rr, cc)
                if pos in occupied:
                    raise TableFormatError("table_spans에 겹치는 병합 영역이 있습니다.")
                occupied[pos] = anchor

    covered = {pos for pos, anchor in occupied.items() if pos != anchor}
    return span_map, covered


def _has_header_rowspan(span_map: dict[tuple[int, int], dict[str, int]]) -> bool:
    return any(
        row == 0 and int(span.get("rowspan", 1)) > 1
        for (row, _col), span in span_map.items()
    )


def _flatten_html_rows(
    parsed_rows: list[list[dict[str, Any]]],
) -> tuple[list[list[str]], list[dict[str, int]]]:
    grid: list[list[str]] = []
    occupied: set[tuple[int, int]] = set()
    spans: list[dict[str, int]] = []

    for row_idx, row in enumerate(parsed_rows):
        _ensure_grid_cell(grid, row_idx, 0)
        col_idx = 0
        for cell in row:
            while (row_idx, col_idx) in occupied:
                col_idx += 1

            text = str(cell.get("text", ""))
            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            _ensure_grid_cell(grid, row_idx, col_idx)
            grid[row_idx][col_idx] = text

            if rowspan > 1 or colspan > 1:
                spans.append({
                    "row": row_idx,
                    "col": col_idx,
                    "rowspan": rowspan,
                    "colspan": colspan,
                })

            for rr in range(row_idx, row_idx + rowspan):
                for cc in range(col_idx, col_idx + colspan):
                    _ensure_grid_cell(grid, rr, cc)
                    if rr == row_idx and cc == col_idx:
                        continue
                    occupied.add((rr, cc))
            if rowspan > 1 or colspan > 1:
                for flat_cell in cell.get("flat_cells", []):
                    rr = row_idx + int(flat_cell.get("dr", 0))
                    cc = col_idx + int(flat_cell.get("dc", 0))
                    if rr == row_idx and cc == col_idx:
                        continue
                    _ensure_grid_cell(grid, rr, cc)
                    grid[rr][cc] = str(flat_cell.get("text", ""))
                if str(cell.get("anchor_text", text)) != text:
                    for rr in range(row_idx, row_idx + rowspan):
                        for cc in range(col_idx, col_idx + colspan):
                            if rr == row_idx and cc == col_idx:
                                continue
                            _ensure_grid_cell(grid, rr, cc)
                            grid[rr][cc] = text
            col_idx += colspan

    return grid, spans


def _ensure_grid_cell(grid: list[list[str]], row: int, col: int):
    while len(grid) <= row:
        grid.append([])
    while len(grid[row]) <= col:
        grid[row].append("")


def _covered_flat_cells(
    rows: list[list[str]],
    row: int,
    col: int,
    span: dict[str, int],
) -> list[dict[str, Any]]:
    flat_cells: list[dict[str, Any]] = []
    rowspan = int(span.get("rowspan", 1))
    colspan = int(span.get("colspan", 1))
    if rowspan == 1 and colspan == 1:
        return flat_cells
    for rr in range(row, row + rowspan):
        for cc in range(col, col + colspan):
            if rr == row and cc == col:
                continue
            value = rows[rr][cc]
            if value:
                flat_cells.append({"dr": rr - row, "dc": cc - col, "text": value})
    return flat_cells


def _span_attrs(
    span: dict[str, int],
    flat_cells: list[dict[str, Any]] | None = None,
    anchor_text: str = "",
) -> str:
    attrs: list[str] = []
    rowspan = int(span.get("rowspan", 1))
    colspan = int(span.get("colspan", 1))
    if rowspan > 1:
        attrs.append(f' rowspan="{rowspan}"')
    if colspan > 1:
        attrs.append(f' colspan="{colspan}"')
    if flat_cells:
        payload = json.dumps(flat_cells, ensure_ascii=False, separators=(",", ":"))
        attrs.append(f' data-flat-cells="{escape(payload, quote=True)}"')
    if rowspan > 1 or colspan > 1:
        attrs.append(f' data-anchor-text="{escape(_normalize_cell_text(anchor_text), quote=True)}"')
    return "".join(attrs)


def _pad_cells(cells: list[str], width: int) -> list[str]:
    if len(cells) >= width:
        return list(cells)
    return [*cells, *([""] * (width - len(cells)))]


def _markdown_cell_to_html(cell: str) -> str:
    text = _normalize_cell_text(cell)
    if not text:
        return "&nbsp;"
    placeholder = "__CODEX_BR__"
    safe = _BR_RE.sub(placeholder, text)
    safe = escape(safe, quote=False)
    return safe.replace(placeholder, "<br>")


def _normalize_cell_text(text: str) -> str:
    value = (text or "").replace("\xa0", " ").strip()
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\s*\n\s*", "<br>", value)
    value = _BR_RE.sub("<br>", value)
    parts = [segment.strip() for segment in value.split("<br>")]
    return "<br>".join(parts)


def _format_markdown_row(cells: list[str]) -> str:
    rendered: list[str] = []
    for cell in cells:
        rendered.append(_render_markdown_cell(cell))
    return "|" + "|".join(rendered) + "|"


def _render_markdown_cell(cell: str) -> str:
    return _normalize_cell_text(cell).replace("|", r"\|")


def _format_pretty_markdown_row(cells: list[str], col_widths: list[int]) -> str:
    padded = [
        cell.ljust(col_widths[idx])
        for idx, cell in enumerate(_pad_cells(cells, len(col_widths)))
    ]
    return "| " + " | ".join(padded) + " |"


def _format_pretty_separator_row(separator: list[str], col_widths: list[int]) -> str:
    cells: list[str] = []
    padded_separator = _pad_cells(separator, len(col_widths))
    for idx, cell in enumerate(padded_separator):
        value = cell.strip()
        left = value.startswith(":")
        right = value.endswith(":")
        dash_count = max(3, col_widths[idx] - int(left) - int(right))
        rendered = ("-" * dash_count)
        if left:
            rendered = ":" + rendered
        if right:
            rendered = rendered + ":"
        cells.append(rendered.ljust(col_widths[idx]))
    return "| " + " | ".join(cells) + " |"


def _format_attrs(attrs: list[tuple[str, str | None]]) -> str:
    parts: list[str] = []
    for name, value in attrs:
        if name in {"rowspan", "colspan"} and str(value or "").strip() == "1":
            continue
        if value is None:
            parts.append(f" {name}")
        else:
            parts.append(f' {name}="{escape(str(value), quote=True)}"')
    return "".join(parts)


class _PrettyHTMLParser(HTMLParser):
    """테이블 HTML을 소스 보기용으로 들여쓰기한다."""

    _BLOCK_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "caption", "colgroup"}
    _CELL_TAGS = {"td", "th"}
    _VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "base", "col", "area", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._lines: list[str] = []
        self._current = ""
        self._indent = 0

    def result(self) -> str:
        self._flush_current()
        return "\n".join(line for line in self._lines if line.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        start = f"<{tag}{_format_attrs(attrs)}>"
        if tag in self._BLOCK_TAGS:
            self._flush_current()
            self._append_line(start)
            self._indent += 1
            return
        if tag in self._CELL_TAGS:
            self._flush_current()
            self._current = self._indent_text() + start
            return
        if tag in self._VOID_TAGS:
            self._append_inline(start)
            return
        self._append_inline(start)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self._append_inline(f"<{tag}{_format_attrs(attrs)} />")

    def handle_endtag(self, tag: str):
        end = f"</{tag}>"
        if tag in self._BLOCK_TAGS:
            self._flush_current()
            self._indent = max(0, self._indent - 1)
            self._append_line(end)
            return
        if tag in self._CELL_TAGS:
            self._append_inline(end)
            self._flush_current()
            return
        self._append_inline(end)

    def handle_data(self, data: str):
        text = data.strip()
        if text:
            self._append_inline(text)

    def handle_entityref(self, name: str):
        self._append_inline(f"&{name};")

    def handle_charref(self, name: str):
        self._append_inline(f"&#{name};")

    def handle_comment(self, data: str):
        self._flush_current()
        self._append_line(f"<!--{data}-->")

    def _indent_text(self) -> str:
        return "  " * self._indent

    def _append_line(self, text: str):
        self._lines.append(self._indent_text() + text)

    def _append_inline(self, text: str):
        if not self._current:
            self._current = self._indent_text()
        self._current += text

    def _flush_current(self):
        if self._current.strip():
            self._lines.append(self._current.rstrip())
        self._current = ""


class _SimpleTableHTMLParser(HTMLParser):
    """Markdown 직렬화가 가능한 테이블을 파싱."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, Any]]] = []
        self._inside_table = False
        self._table_depth = 0
        self._current_row: list[dict[str, Any]] | None = None
        self._current_cell: dict[str, Any] | None = None
        self._current_text: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag == "table":
            if not self._inside_table:
                self._inside_table = True
            self._table_depth += 1
            return
        if not self._inside_table:
            return
        if tag == "tfoot":
            raise TableFormatError("Markdown 모드는 <tfoot>을 지원하지 않습니다.")
        if tag == "tr":
            self._current_row = []
            return
        if tag in {"td", "th"}:
            if self._current_row is None:
                return
            attrs_map = dict(attrs)
            try:
                colspan = int(attrs_map.get("colspan") or "1")
                rowspan = int(attrs_map.get("rowspan") or "1")
            except ValueError as exc:
                raise TableFormatError("rowspan/colspan 값이 올바르지 않습니다.") from exc
            if colspan < 1 or rowspan < 1:
                raise TableFormatError("rowspan/colspan은 1 이상이어야 합니다.")
            flat_cells = []
            if attrs_map.get("data-flat-cells"):
                try:
                    flat_cells = json.loads(attrs_map["data-flat-cells"] or "[]")
                except json.JSONDecodeError:
                    flat_cells = []
            self._current_cell = {
                "rowspan": rowspan,
                "colspan": colspan,
                "flat_cells": flat_cells if isinstance(flat_cells, list) else [],
                "anchor_text": _normalize_cell_text(attrs_map.get("data-anchor-text") or ""),
            }
            self._current_text = []
            return
        if tag == "br" and self._current_text is not None:
            self._current_text.append("<br>")

    def handle_endtag(self, tag: str):
        if tag == "table" and self._inside_table:
            self._table_depth -= 1
            if self._table_depth <= 0:
                self._inside_table = False
                self._table_depth = 0
            return
        if not self._inside_table:
            return
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_cell["text"] = _normalize_cell_text("".join(self._current_text or []))
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._current_text = None
            return
        if tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str):
        if self._current_text is not None:
            self._current_text.append(data)
