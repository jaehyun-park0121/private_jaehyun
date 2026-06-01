DIALOG_STYLESHEET = """
QDialog { background: #ffffff; }
QGroupBox {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 8px;
    margin-top: 0px;
    font-weight: 600;
    padding-top: 0px;
}
QGroupBox#titledCard {
    margin-top: 14px;
    padding-top: 4px;
    font-size: 12px;
}
QLineEdit, QPlainTextEdit, QSpinBox {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 6px;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 6px;
    padding: 6px 10px;
}
QPushButton:hover { background: #f8fafc; }
QPushButton#primaryRunButton {
    background: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    border-radius: 8px;
    font-weight: 600;
    padding: 6px 14px;
}
QPushButton#primaryRunButton:hover {
    background: #1d4ed8;
}
QPushButton#primaryRunButton[running="true"] {
    background: #ef4444;
    border: 1px solid #dc2626;
}
QPushButton#primaryRunButton[running="true"]:hover {
    background: #dc2626;
}
QWidget#parseLeftPanel {
    background: #ffffff;
}
QWidget#parseStatusRow {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}
QFrame#parseOptionCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}
QFrame#parseOptionCard[checked="true"] {
    background: #eaf2ff;
    border: 1px solid #60a5fa;
}
QFrame#parseOptionCard QCheckBox {
    color: #0f172a;
    font-weight: 600;
}
QFrame#labelRuleCard {
    background: #ffffff;
    border: 1px solid #dbe3ee;
    border-radius: 8px;
}
QFrame#labelRuleCard[active="true"] {
    border: 1px solid #3b82f6;
    background: #f8fbff;
}
QFrame#labelRuleCard[invalid="true"] {
    border: 1px solid #ef4444;
    background: #fff7f7;
}
QFrame#labelRuleCard[invalid="true"][active="true"] {
    border: 1px solid #3b82f6;
}
QPushButton#labelChoiceButton {
    background: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #334155;
    font-size: 11px;
    padding: 0px 10px;
}
QPushButton#labelChoiceButton:hover {
    background: #eef2f7;
}
QPushButton#labelChoiceButton:checked {
    background: #dbeafe;
    border: 1px solid #60a5fa;
    color: #1d4ed8;
    font-weight: 600;
}
QPushButton#labelCardDeleteButton {
    background: #fff5f5;
    color: #b91c1c;
    border: 1px solid #fecaca;
    border-radius: 6px;
    padding: 0;
    font-weight: 700;
}
QPushButton#labelCardDeleteButton:hover {
    background: #fee2e2;
}
QPushButton#labelAddSlotButton {
    background: #ffffff;
    border: 1px dashed #94a3b8;
    border-radius: 8px;
    color: #475569;
    font-size: 18px;
    font-weight: 700;
    padding: 10px;
}
QPushButton#labelAddSlotButton:hover {
    background: #f8fafc;
    border: 1px dashed #64748b;
}
QScrollArea { background: #ffffff; }
QSplitter { background: #ffffff; }
QPushButton#outputFieldButton {
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #64748b;
    font-size: 11px;
    padding: 3px 8px;
    min-height: 28px;
}
QPushButton#outputFieldButton:hover {
    background: #e2e8f0;
}
QPushButton#outputFieldButton[fieldState="required"] {
    background: #dbeafe;
    border: 1px solid #60a5fa;
    color: #1d4ed8;
    font-weight: 600;
}
QPushButton#outputFieldButton[fieldState="nonempty"] {
    background: #fef3c7;
    border: 1px solid #fbbf24;
    color: #92400e;
    font-weight: 600;
}
QLabel#outputFieldGroupLabel {
    color: #64748b;
    font-size: 11px;
    font-weight: 600;
}
"""
