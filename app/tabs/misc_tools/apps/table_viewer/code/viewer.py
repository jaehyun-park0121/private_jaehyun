"""금융 문서 JSON + 이미지 검수 뷰어 (PyQt6) — 진입점.

사용법:
    pip install -r requirements.txt
    python viewer.py
"""

import sys

from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.theme import build_qss


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(build_qss())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
