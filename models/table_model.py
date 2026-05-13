from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Cell:
    """Represents a single cell in the table grid."""
    text: str = ""
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False
    is_merged_ref: bool = False
    merge_parent: Optional[tuple[int, int]] = None

    def __repr__(self):
        return f"Cell(text='{self.text[:20]}...', rs={self.rowspan}, cs={self.colspan}, merged={self.is_merged_ref})"


class TableModel:
    """Internal data model for table editing."""

    def __init__(self, rows: int = 0, cols: int = 0):
        self.rows = rows
        self.cols = cols
        self.grid: list[list[Cell]] = [[Cell() for _ in range(cols)] for _ in range(rows)]

    def get_cell(self, row: int, col: int) -> Cell:
        """Get cell at specified position."""
        if 0 <= row < self.rows and 0 <= col < self.cols:
            return self.grid[row][col]
        raise IndexError(f"Cell position ({row}, {col}) out of bounds")

    def set_cell(self, row: int, col: int, cell: Cell) -> None:
        """Set cell at specified position."""
        if 0 <= row < self.rows and 0 <= col < self.cols:
            self.grid[row][col] = cell
        else:
            raise IndexError(f"Cell position ({row}, {col}) out of bounds")

    def set_text(self, row: int, col: int, text: str) -> None:
        """Set text content of a cell."""
        cell = self.get_cell(row, col)
        if cell.is_merged_ref and cell.merge_parent:
            parent_row, parent_col = cell.merge_parent
            self.grid[parent_row][parent_col].text = text
        else:
            cell.text = text

    def merge_cells(self, selection: list[tuple[int, int]]) -> None:
        """Merge selected cells into one."""
        if not selection:
            return

        min_row = min(r for r, c in selection)
        max_row = max(r for r, c in selection)
        min_col = min(c for r, c in selection)
        max_col = max(c for r, c in selection)

        rowspan = max_row - min_row + 1
        colspan = max_col - min_col + 1

        parent_cell = self.get_cell(min_row, min_col)
        parent_cell.rowspan = rowspan
        parent_cell.colspan = colspan

        texts = []
        for r, c in selection:
            cell = self.get_cell(r, c)
            if cell.text.strip():
                texts.append(cell.text.strip())

        parent_cell.text = " ".join(texts) if texts else parent_cell.text

        for r in range(min_row, max_row + 1):
            for c in range(min_col, max_col + 1):
                if r == min_row and c == min_col:
                    continue
                cell = self.get_cell(r, c)
                cell.is_merged_ref = True
                cell.merge_parent = (min_row, min_col)
                cell.text = ""

    def split_cell(self, row: int, col: int) -> None:
        """Split a merged cell back into individual cells."""
        cell = self.get_cell(row, col)

        if cell.is_merged_ref and cell.merge_parent:
            row, col = cell.merge_parent
            cell = self.get_cell(row, col)

        if cell.rowspan == 1 and cell.colspan == 1:
            return

        for r in range(row, row + cell.rowspan):
            for c in range(col, col + cell.colspan):
                target_cell = self.get_cell(r, c)
                target_cell.is_merged_ref = False
                target_cell.merge_parent = None
                if r == row and c == col:
                    target_cell.rowspan = 1
                    target_cell.colspan = 1

        cell.rowspan = 1
        cell.colspan = 1

    def insert_row(self, index: int) -> None:
        """Insert a new row at the specified index."""
        new_row = [Cell() for _ in range(self.cols)]
        self.grid.insert(index, new_row)
        self.rows += 1

        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.get_cell(r, c)
                if cell.merge_parent:
                    pr, pc = cell.merge_parent
                    if pr >= index:
                        cell.merge_parent = (pr + 1, pc)

        for r in range(index):
            for c in range(self.cols):
                cell = self.get_cell(r, c)
                if not cell.is_merged_ref and r + cell.rowspan > index:
                    cell.rowspan += 1
                    for extend_r in range(index, min(r + cell.rowspan, self.rows)):
                        for extend_c in range(c, min(c + cell.colspan, self.cols)):
                            if extend_r >= self.rows or extend_c >= self.cols:
                                continue
                            target = self.get_cell(extend_r, extend_c)
                            if extend_r != r or extend_c != c:
                                target.is_merged_ref = True
                                target.merge_parent = (r, c)

    def delete_row(self, index: int) -> None:
        """Delete a row at the specified index."""
        if self.rows <= 1:
            return

        for c in range(self.cols):
            cell = self.get_cell(index, c)
            if cell.is_merged_ref and cell.merge_parent:
                pr, pc = cell.merge_parent
                parent = self.get_cell(pr, pc)
                if pr < index:
                    parent.rowspan = max(1, parent.rowspan - 1)

        for c in range(self.cols):
            cell = self.get_cell(index, c)
            if not cell.is_merged_ref and cell.rowspan > 1:
                cell.rowspan -= 1

        del self.grid[index]
        self.rows -= 1

        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.get_cell(r, c)
                if cell.merge_parent:
                    pr, pc = cell.merge_parent
                    if pr > index:
                        cell.merge_parent = (pr - 1, pc)
                    elif pr == index:
                        cell.is_merged_ref = False
                        cell.merge_parent = None

    def insert_col(self, index: int) -> None:
        """Insert a new column at the specified index."""
        for row in self.grid:
            row.insert(index, Cell())
        self.cols += 1

        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.get_cell(r, c)
                if cell.merge_parent:
                    pr, pc = cell.merge_parent
                    if pc >= index:
                        cell.merge_parent = (pr, pc + 1)

        for r in range(self.rows):
            for c in range(index):
                cell = self.get_cell(r, c)
                if not cell.is_merged_ref and c + cell.colspan > index:
                    cell.colspan += 1
                    for extend_c in range(index, min(c + cell.colspan, self.cols)):
                        for extend_r in range(r, min(r + cell.rowspan, self.rows)):
                            if extend_r >= self.rows or extend_c >= self.cols:
                                continue
                            target = self.get_cell(extend_r, extend_c)
                            if extend_r != r or extend_c != c:
                                target.is_merged_ref = True
                                target.merge_parent = (r, c)

    def delete_col(self, index: int) -> None:
        """Delete a column at the specified index."""
        if self.cols <= 1:
            return

        for r in range(self.rows):
            cell = self.get_cell(r, index)
            if cell.is_merged_ref and cell.merge_parent:
                pr, pc = cell.merge_parent
                parent = self.get_cell(pr, pc)
                if pc < index:
                    parent.colspan = max(1, parent.colspan - 1)

        for r in range(self.rows):
            cell = self.get_cell(r, index)
            if not cell.is_merged_ref and cell.colspan > 1:
                cell.colspan -= 1

        for row in self.grid:
            del row[index]
        self.cols -= 1

        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.get_cell(r, c)
                if cell.merge_parent:
                    pr, pc = cell.merge_parent
                    if pc > index:
                        cell.merge_parent = (pr, pc - 1)
                    elif pc == index:
                        cell.is_merged_ref = False
                        cell.merge_parent = None
