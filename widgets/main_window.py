from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QSplitter, QListWidget, QLabel, QFileDialog,
                             QMessageBox)
from PyQt5.QtCore import Qt
from pathlib import Path

from widgets.toolbar import EditorToolBar
from widgets.table_editor import TableEditor
from widgets.html_preview import HTMLPreview
from parsers.json_handler import JSONHandler
from parsers.html_parser import parse_html_table
from parsers.html_generator import generate_html_table


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.json_handler = JSONHandler()
        self.current_table_index = -1
        self.setup_ui()

    def setup_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("HTML Table Merge Editor")
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        self.toolbar = EditorToolBar()
        self.addToolBar(self.toolbar)

        self.toolbar.open_file.connect(self.open_json_file)
        self.toolbar.save_file.connect(self.save_json_file)
        self.toolbar.merge_cells.connect(self.merge_cells)
        self.toolbar.split_cell.connect(self.split_cell)
        self.toolbar.insert_row.connect(self.insert_row)
        self.toolbar.delete_row.connect(self.delete_row)
        self.toolbar.insert_col.connect(self.insert_col)
        self.toolbar.delete_col.connect(self.delete_col)

        content_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)

        left_layout.addWidget(QLabel("Current File:"))
        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        left_layout.addWidget(self.file_label)

        left_layout.addWidget(QLabel("Tables:"))
        self.table_list = QListWidget()
        self.table_list.currentRowChanged.connect(self.on_table_selected)
        left_layout.addWidget(self.table_list)

        right_splitter = QSplitter(Qt.Vertical)

        self.table_editor = TableEditor()
        self.table_editor.table_modified.connect(self.on_table_modified)

        self.html_preview = HTMLPreview()

        right_splitter.addWidget(self.table_editor)
        right_splitter.addWidget(self.html_preview)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)

        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(right_splitter)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 4)

        main_layout.addWidget(content_splitter)

    def open_json_file(self):
        """Open a JSON file containing table data."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open JSON File",
            str(Path.home()),
            "JSON Files (*.json)"
        )

        if not file_path:
            return

        if self.json_handler.load(file_path):
            self.file_label.setText(Path(file_path).name)
            self.update_table_list()

            if self.json_handler.get_table_count() > 0:
                self.table_list.setCurrentRow(0)
        else:
            QMessageBox.warning(self, "Error", "Failed to load JSON file")

    def update_table_list(self):
        """Update the list of tables in the current file."""
        self.table_list.clear()

        for i in range(self.json_handler.get_table_count()):
            info = self.json_handler.get_table_info(i)
            self.table_list.addItem(f"Table {i + 1}")

    def on_table_selected(self, index: int):
        """Handle table selection from the list."""
        if index < 0:
            return

        self.current_table_index = index

        html = self.json_handler.get_table_html(index)

        if html:
            table_model = parse_html_table(html)
            self.table_editor.load_table_model(table_model)
            self.update_preview()

    def on_table_modified(self):
        """Handle table modifications."""
        self.update_preview()

    def update_preview(self):
        """Update the HTML preview."""
        table_model = self.table_editor.get_table_model()
        html = generate_html_table(table_model)
        self.html_preview.set_html(html)

    def save_json_file(self):
        """Save the modified table back to JSON file."""
        if self.current_table_index < 0:
            QMessageBox.warning(self, "Error", "No table selected")
            return

        table_model = self.table_editor.get_table_model()
        html = generate_html_table(table_model)

        if self.json_handler.set_table_html(self.current_table_index, html):
            if self.json_handler.save():
                QMessageBox.information(self, "Success", "File saved successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to save file")
        else:
            QMessageBox.warning(self, "Error", "Failed to update table data")

    def merge_cells(self):
        """Merge selected cells."""
        self.table_editor.merge_selected_cells()

    def split_cell(self):
        """Split selected cell."""
        self.table_editor.split_selected_cell()

    def insert_row(self):
        """Insert a new row."""
        self.table_editor.insert_row_at_selection()

    def delete_row(self):
        """Delete selected row."""
        self.table_editor.delete_row_at_selection()

    def insert_col(self):
        """Insert a new column."""
        self.table_editor.insert_col_at_selection()

    def delete_col(self):
        """Delete selected column."""
        self.table_editor.delete_col_at_selection()
