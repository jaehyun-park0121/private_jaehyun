from models.table_model import TableModel


def generate_html_table(model: TableModel) -> str:
    """Generate HTML table string from TableModel."""
    if model.rows == 0 or model.cols == 0:
        return "<table></table>"

    lines = ["<table>"]

    for r in range(model.rows):
        lines.append("  <tr>")

        for c in range(model.cols):
            cell = model.get_cell(r, c)

            if cell.is_merged_ref:
                continue

            tag = "th" if cell.is_header else "td"

            attrs = []
            if cell.colspan > 1:
                attrs.append(f'colspan="{cell.colspan}"')
            if cell.rowspan > 1:
                attrs.append(f'rowspan="{cell.rowspan}"')

            attr_str = " " + " ".join(attrs) if attrs else ""

            lines.append(f"    <{tag}{attr_str}>{cell.text}</{tag}>")

        lines.append("  </tr>")

    lines.append("</table>")

    return "\n".join(lines)
