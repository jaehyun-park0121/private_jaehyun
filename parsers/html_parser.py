from html.parser import HTMLParser
from models.table_model import TableModel, Cell


class TableHTMLParser(HTMLParser):
    """Parse HTML table string into TableModel."""

    def __init__(self):
        super().__init__()
        self.rows_data: list[list[dict]] = []
        self.current_row: list[dict] = []
        self.current_cell: dict = {}
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.cell_content: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "table":
            self.in_table = True
            self.rows_data = []

        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []

        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell_content = []
            self.current_cell = {
                "is_header": tag == "th",
                "rowspan": int(attrs_dict.get("rowspan", 1)),
                "colspan": int(attrs_dict.get("colspan", 1)),
                "text": ""
            }

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False

        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows_data.append(self.current_row)

        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.current_cell["text"] = "".join(self.cell_content).strip()
            self.current_row.append(self.current_cell)

    def handle_data(self, data):
        if self.in_cell:
            self.cell_content.append(data)


def parse_html_table(html_string: str) -> TableModel:
    """Parse HTML table string and return TableModel."""
    parser = TableHTMLParser()
    parser.feed(html_string)

    if not parser.rows_data:
        return TableModel(0, 0)

    max_cols = 0
    for row_cells in parser.rows_data:
        col_count = sum(cell["colspan"] for cell in row_cells)
        max_cols = max(max_cols, col_count)

    grid: list[list[Cell | None]] = []
    for _ in range(len(parser.rows_data)):
        grid.append([None] * max_cols)

    for r_idx, row_cells in enumerate(parser.rows_data):
        col_offset = 0
        for cell_data in row_cells:
            while col_offset < max_cols and grid[r_idx][col_offset] is not None:
                col_offset += 1

            if col_offset >= max_cols:
                break

            rowspan = cell_data["rowspan"]
            colspan = cell_data["colspan"]

            cell = Cell(
                text=cell_data["text"],
                rowspan=rowspan,
                colspan=colspan,
                is_header=cell_data["is_header"]
            )

            grid[r_idx][col_offset] = cell

            for dr in range(rowspan):
                for dc in range(colspan):
                    target_r = r_idx + dr
                    target_c = col_offset + dc

                    if target_r >= len(grid) or target_c >= max_cols:
                        continue

                    if dr == 0 and dc == 0:
                        continue

                    if grid[target_r][target_c] is None:
                        merged_cell = Cell(
                            is_merged_ref=True,
                            merge_parent=(r_idx, col_offset)
                        )
                        grid[target_r][target_c] = merged_cell

            col_offset += colspan

    for row in grid:
        for c_idx, cell in enumerate(row):
            if cell is None:
                row[c_idx] = Cell()

    model = TableModel(len(grid), max_cols)
    model.grid = grid

    return model
