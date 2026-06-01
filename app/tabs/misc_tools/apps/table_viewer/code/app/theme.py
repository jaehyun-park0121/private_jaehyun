"""애플리케이션 QSS 스타일."""

from .constants import (
    COLOR_BG,
    COLOR_BODY_TEXT,
    COLOR_BORDER,
    COLOR_BORDER_LIGHT,
    COLOR_PANEL,
    COLOR_PANEL_MUTED,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_SUBTEXT,
    COLOR_TEXT,
)


def build_qss() -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {COLOR_BG};
    color: {COLOR_BODY_TEXT};
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    font-size: 12px;
}}
QFrame#panel {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QFrame#darkHeader {{
    background-color: #111217;
    border: none;
    border-bottom: 1px solid #202431;
    border-radius: 0px;
}}
QFrame#metaPill {{
    background-color: #1e2230;
    border: 1px solid #2f3647;
    border-radius: 4px;
}}
QFrame#sectionBox {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QFrame#editRail {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QPushButton {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px 10px;
    color: {COLOR_BODY_TEXT};
    font-size: 11px;
    font-weight: 600;
    min-height: 26px;
}}
QPushButton:hover {{
    background-color: {COLOR_PANEL_MUTED};
    border-color: {COLOR_BORDER};
}}
QPushButton:disabled {{
    color: #94a3b8;
    background: #f1f5f9;
    border-color: {COLOR_BORDER};
}}
QPushButton#primary {{
    background-color: {COLOR_PANEL};
    border-color: {COLOR_BORDER};
    color: {COLOR_BODY_TEXT};
}}
QPushButton#primary:hover {{
    background-color: {COLOR_PANEL_MUTED};
    border-color: {COLOR_BORDER};
}}
QPushButton#headerActionBtn {{
    background: transparent;
    color: #d7d9e0;
    border: 1px solid #3c4355;
    border-radius: 8px;
    padding: 4px 10px;
}}
QPushButton#headerActionBtn:hover {{
    background: #232834;
    color: #ffffff;
    border-color: #4d5670;
}}
QPushButton#toggle {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 14px;
    padding: 4px 12px;
    color: {COLOR_SUBTEXT};
    font-weight: 600;
}}
QPushButton#toggle:hover {{
    background-color: {COLOR_PANEL_MUTED};
    border-color: {COLOR_BORDER};
    color: {COLOR_BODY_TEXT};
}}
QPushButton#toggle:checked {{
    background-color: {COLOR_PRIMARY};
    border-color: {COLOR_PRIMARY};
    color: white;
}}
QPushButton#toggle:checked:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
    border-color: {COLOR_PRIMARY_HOVER};
    color: white;
}}
QLabel {{
    background: transparent;
    border: none;
}}
QListWidget {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    outline: 0;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {COLOR_BORDER_LIGHT};
}}
QListWidget::item:selected {{
    background-color: #dbeafe;
    color: {COLOR_TEXT};
}}
QTreeWidget {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    outline: 0;
}}
QTreeWidget::item {{
    padding: 4px 6px;
}}
QTreeWidget::item:selected {{
    background-color: #dbeafe;
    color: {COLOR_TEXT};
}}
QTreeWidget::branch:selected {{
    background-color: #dbeafe;
}}
QLineEdit, QComboBox, QPlainTextEdit {{
    background-color: #f3f4f6;
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 4px 8px;
    color: {COLOR_BODY_TEXT};
    font-size: 11px;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    background-color: {COLOR_PANEL};
    border-color: {COLOR_BORDER};
}}
QLabel#title {{
    font-size: 14px;
    font-weight: 700;
    color: {COLOR_TEXT};
    background: transparent;
    border: none;
}}
QLabel#subtitle {{
    color: {COLOR_SUBTEXT};
    background: transparent;
    border: none;
    font-size: 11px;
}}
QLabel#fieldLabel {{
    color: {COLOR_SUBTEXT};
    background: transparent;
    border: none;
    padding: 0px;
    font-size: 11px;
    font-weight: 600;
}}
QFrame#toolbarRow {{
    background: transparent;
    border: none;
}}
QLabel#toolbarLabel {{
    color: {COLOR_SUBTEXT};
    background: transparent;
    border: none;
    padding: 0px 4px 0px 0px;
    font-size: 11px;
    font-weight: 700;
}}
QPushButton#toolbarButton {{
    background-color: #f8fafc;
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    color: {COLOR_BODY_TEXT};
    padding: 2px 8px;
    min-height: 22px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#toolbarButton:hover {{
    background-color: #eef2f7;
    border-color: #c6d0dd;
    color: {COLOR_TEXT};
}}
QPushButton#toolbarButton:disabled {{
    background: #f1f5f9;
    color: #94a3b8;
    border-color: {COLOR_BORDER};
}}
QToolButton#railButton {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    color: {COLOR_BODY_TEXT};
    font-size: 11px;
    font-weight: 700;
}}
QToolButton#railButton:hover {{
    background-color: {COLOR_PANEL_MUTED};
    border-color: #c6d0dd;
}}
QToolButton#railButton:disabled {{
    background-color: #f1f5f9;
    color: #94a3b8;
    border-color: {COLOR_BORDER};
}}
QToolButton#railButton::menu-indicator {{
    image: none;
    width: 0px;
}}
QMenu {{
    background-color: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px;
    color: {COLOR_BODY_TEXT};
}}
QMenu::item {{
    padding: 5px 18px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {COLOR_PANEL_MUTED};
    color: {COLOR_TEXT};
}}
QLabel#darkTitle {{
    color: #ffffff;
    font-weight: 700;
    background: transparent;
    border: none;
}}
QLabel#infoTag {{
    color: #a4adbe;
    font-weight: 600;
    padding: 2px 4px;
    background: transparent;
    border: none;
}}
QLabel#infoValue {{
    color: #f2f4f8;
    background: transparent;
    border: none;
    padding: 3px 8px;
}}
QCheckBox {{
    color: {COLOR_BODY_TEXT};
    spacing: 6px;
}}
QGroupBox {{
    background: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    margin-top: 10px;
    color: {COLOR_BODY_TEXT};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    background: transparent;
    color: {COLOR_SUBTEXT};
    font-size: 11px;
}}
QStatusBar {{
    background-color: #f7f8fa;
    color: #9ca3af;
    border-top: 1px solid #e5e7eb;
    font-size: 11px;
}}
QSplitter::handle {{
    background-color: #dfe5ef;
}}
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 0px;
    top: -1px;
    background: {COLOR_PANEL};
}}
QTabBar::tab {{
    background: #eef1f5;
    color: {COLOR_BODY_TEXT};
    padding: 5px 12px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 0px;
    font-size: 11px;
    font-weight: 600;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border-bottom: 1px solid {COLOR_PANEL};
}}
QTabBar::tab:!selected {{
    margin-top: 1px;
}}
QGraphicsView {{
    background: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}
QPlainTextEdit {{
    font-family: 'Consolas', 'D2Coding', monospace;
    font-size: 12px;
}}
QScrollBar:vertical {{
    background: #f6f8fc;
    width: 8px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: #f6f8fc;
    height: 8px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: #cbd5e1;
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
"""
