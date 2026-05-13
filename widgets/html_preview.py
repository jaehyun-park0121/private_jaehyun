from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QTabWidget
from PyQt5.QtGui import QFont


class HTMLPreview(QWidget):
    """HTML preview widget showing both rendered and source views."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QTabWidget()

        self.rendered_view = QTextEdit()
        self.rendered_view.setReadOnly(True)

        self.source_view = QTextEdit()
        self.source_view.setReadOnly(True)
        self.source_view.setFont(QFont("Courier New", 9))

        self.tab_widget.addTab(self.rendered_view, "Rendered")
        self.tab_widget.addTab(self.source_view, "HTML Source")

        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def set_html(self, html: str):
        """Set HTML content for preview."""
        self.rendered_view.setHtml(html)
        self.source_view.setPlainText(html)
