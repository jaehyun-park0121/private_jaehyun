from PyQt5.QtWidgets import QToolBar, QAction
from PyQt5.QtCore import pyqtSignal


class EditorToolBar(QToolBar):
    """Toolbar for table editing operations."""

    open_file = pyqtSignal()
    save_file = pyqtSignal()
    merge_cells = pyqtSignal()
    split_cell = pyqtSignal()
    insert_row = pyqtSignal()
    delete_row = pyqtSignal()
    insert_col = pyqtSignal()
    delete_col = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Editor Toolbar", parent)
        self.setup_actions()

    def setup_actions(self):
        """Create toolbar actions."""
        open_action = QAction("Open", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file.emit)
        self.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_file.emit)
        self.addAction(save_action)

        self.addSeparator()

        merge_action = QAction("Merge", self)
        merge_action.triggered.connect(self.merge_cells.emit)
        self.addAction(merge_action)

        split_action = QAction("Split", self)
        split_action.triggered.connect(self.split_cell.emit)
        self.addAction(split_action)

        self.addSeparator()

        insert_row_action = QAction("+Row", self)
        insert_row_action.triggered.connect(self.insert_row.emit)
        self.addAction(insert_row_action)

        delete_row_action = QAction("-Row", self)
        delete_row_action.triggered.connect(self.delete_row.emit)
        self.addAction(delete_row_action)

        self.addSeparator()

        insert_col_action = QAction("+Col", self)
        insert_col_action.triggered.connect(self.insert_col.emit)
        self.addAction(insert_col_action)

        delete_col_action = QAction("-Col", self)
        delete_col_action.triggered.connect(self.delete_col.emit)
        self.addAction(delete_col_action)
