from PyQt5.QtWidgets import (QTableWidget, QTableWidgetItem, QMenu,
                             QHeaderView, QAbstractItemView)
from PyQt5.QtCore import Qt, pyqtSignal
from models.table_model import TableModel, Cell


class TableEditor(QTableWidget):
    """Table editor widget based on QTableWidget."""

    table_modified = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_data: TableModel = TableModel()
        self.setup_ui()

    def setup_ui(self):
        """Initialize UI settings."""
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.itemChanged.connect(self.on_item_changed)

    def load_table_model(self, model: TableModel):
        """Load a TableModel into the editor."""
        self.model_data = model
        self.blockSignals(True)

        self.clear()
        self.setRowCount(model.rows)
        self.setColumnCount(model.cols)

        for r in range(model.rows):
            for c in range(model.cols):
                cell = model.get_cell(r, c)

                if cell.is_merged_ref:
                    continue

                item = QTableWidgetItem(cell.text)
                self.setItem(r, c, item)

                if cell.rowspan > 1 or cell.colspan > 1:
                    self.setSpan(r, c, cell.rowspan, cell.colspan)

                if cell.is_header:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

        self.blockSignals(False)

    def on_item_changed(self, item: QTableWidgetItem):
        """Handle cell text changes."""
        row = item.row()
        col = item.column()
        text = item.text()

        self.model_data.set_text(row, col, text)
        self.table_modified.emit()

    def get_selected_cells(self) -> list[tuple[int, int]]:
        """Get list of selected cell coordinates."""
        selected_ranges = self.selectedRanges()
        cells = []

        for sel_range in selected_ranges:
            for r in range(sel_range.topRow(), sel_range.bottomRow() + 1):
                for c in range(sel_range.leftColumn(), sel_range.rightColumn() + 1):
                    cells.append((r, c))

        return list(set(cells))

    def merge_selected_cells(self):
        """Merge currently selected cells."""
        selection = self.get_selected_cells()

        if len(selection) < 2:
            return

        self.model_data.merge_cells(selection)
        self.load_table_model(self.model_data)
        self.table_modified.emit()

    def split_selected_cell(self):
        """Split the selected merged cell."""
        selection = self.get_selected_cells()

        if not selection:
            return

        row, col = selection[0]
        self.model_data.split_cell(row, col)
        self.load_table_model(self.model_data)
        self.table_modified.emit()

    def insert_row_at_selection(self):
        """Insert a new row at the current selection."""
        selection = self.get_selected_cells()

        if selection:
            row = min(r for r, c in selection)
        else:
            row = self.currentRow()
            if row < 0:
                row = self.model_data.rows

        self.model_data.insert_row(row)
        self.load_table_model(self.model_data)
        self.table_modified.emit()

    def delete_row_at_selection(self):
        """Delete the row at current selection."""
        selection = self.get_selected_cells()

        if selection:
            row = min(r for r, c in selection)
        else:
            row = self.currentRow()

        if row >= 0:
            self.model_data.delete_row(row)
            self.load_table_model(self.model_data)
            self.table_modified.emit()

    def insert_col_at_selection(self):
        """Insert a new column at the current selection."""
        selection = self.get_selected_cells()

        if selection:
            col = min(c for r, c in selection)
        else:
            col = self.currentColumn()
            if col < 0:
                col = self.model_data.cols

        self.model_data.insert_col(col)
        self.load_table_model(self.model_data)
        self.table_modified.emit()

    def delete_col_at_selection(self):
        """Delete the column at current selection."""
        selection = self.get_selected_cells()

        if selection:
            col = min(c for r, c in selection)
        else:
            col = self.currentColumn()

        if col >= 0:
            self.model_data.delete_col(col)
            self.load_table_model(self.model_data)
            self.table_modified.emit()

    def show_context_menu(self, pos):
        """Show context menu on right-click."""
        menu = QMenu(self)

        selection = self.get_selected_cells()

        if len(selection) >= 2:
            merge_action = menu.addAction("Merge Cells")
            merge_action.triggered.connect(self.merge_selected_cells)

        if selection:
            split_action = menu.addAction("Split Cell")
            split_action.triggered.connect(self.split_selected_cell)

        menu.addSeparator()

        insert_row_action = menu.addAction("Insert Row")
        insert_row_action.triggered.connect(self.insert_row_at_selection)

        delete_row_action = menu.addAction("Delete Row")
        delete_row_action.triggered.connect(self.delete_row_at_selection)

        menu.addSeparator()

        insert_col_action = menu.addAction("Insert Column")
        insert_col_action.triggered.connect(self.insert_col_at_selection)

        delete_col_action = menu.addAction("Delete Column")
        delete_col_action.triggered.connect(self.delete_col_at_selection)

        menu.exec_(self.mapToGlobal(pos))

    def get_table_model(self) -> TableModel:
        """Get the current TableModel."""
        return self.model_data
