"""WebView에 표시할 HTML 템플릿 빌더 (읽기 모드 + 편집 모드)."""

from ..assets import table_edit_js
from ..constants import (
    COLOR_BODY_TEXT,
    COLOR_BORDER_STRONG,
    COLOR_PANEL,
    COLOR_PANEL_MUTED,
    COLOR_SUBTEXT,
    COLOR_TH_BG,
)


_BASE_CSS = f"""
body {{
    background: {COLOR_PANEL};
    color: {COLOR_BODY_TEXT};
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    padding: 14px;
    margin: 0;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    background: {COLOR_PANEL};
}}
th, td {{
    border: 1px solid {COLOR_BORDER_STRONG};
    padding: 6px 10px;
    text-align: center;
    font-size: 12px;
    color: {COLOR_BODY_TEXT};
}}
th {{
    background: {COLOR_TH_BG};
    font-weight: 600;
}}
caption {{
    color: {COLOR_SUBTEXT};
    padding: 6px;
    font-size: 11px;
}}
tfoot td {{
    background: {COLOR_PANEL_MUTED};
    color: {COLOR_SUBTEXT};
    text-align: left;
    font-size: 11px;
}}
.empty {{
    color: {COLOR_SUBTEXT};
    text-align: center;
    padding: 40px;
}}
#editable, #editable * {{ outline: none; }}
"""

_MATHJAX_TAGS = """
<script>
window.MathJax = {
  tex: { inlineMath: [['$','$']] },
  svg: { fontCache: 'global' }
};
</script>
<script async src="mathjax/tex-svg.js"></script>
"""

_EMPTY_BODY = '<div class="empty">파일을 선택하고 BBOX를 클릭하세요.</div>'


def render_page(table_html: str, edit_mode: bool, table_format: str) -> str:
    """주어진 표 HTML을 읽기/편집 모드에 맞게 완성된 HTML 페이지로 만든다."""
    if not table_html:
        body = _EMPTY_BODY
        extra_head = ""
    elif edit_mode:
        body = (
            f'<div id="editable" data-table-format="{table_format}">{table_html}</div>'
            f'<script>{table_edit_js()}</script>'
        )
        extra_head = ""
    else:
        body = f'<div id="rendered">{table_html}</div>'
        extra_head = _MATHJAX_TAGS

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{_BASE_CSS}</style>
{extra_head}
</head>
<body>
{body}
</body>
</html>"""
