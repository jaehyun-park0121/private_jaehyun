from __future__ import annotations

import re
from datetime import datetime

from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QPlainTextEdit


class LogHandler:
    def __init__(
        self, document_view: QPlainTextEdit, page_view: QPlainTextEdit
    ) -> None:
        self._document_view = document_view
        self._page_view = page_view
        self._line_buffer = ""

    def clear(self) -> None:
        self._document_view.clear()
        self._page_view.clear()
        self._line_buffer = ""

    def reset_buffer(self) -> None:
        self._line_buffer = ""

    def append_log(self, message: str, target: str = "document") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_raw(f"[{timestamp}] {message}\n", target=target)

    def append_stream_text(self, text: str) -> None:
        if not text:
            return
        merged = f"{self._line_buffer}{text}"
        merged = merged.replace("\r\n", "\n").replace("\r", "\n")
        parts = merged.split("\n")
        if merged.endswith("\n"):
            self._line_buffer = ""
            if parts:
                parts = parts[:-1]
        else:
            self._line_buffer = parts.pop() if parts else ""

        for line in parts:
            target = self._classify_line(line)
            self._append_raw(f"{line}\n", target=target)

    def flush_buffer(self) -> None:
        if not self._line_buffer:
            return
        line = self._line_buffer
        self._line_buffer = ""
        target = self._classify_line(line)
        self._append_raw(f"{line}\n", target=target)

    def _append_raw(self, text: str, target: str = "document") -> None:
        if not text:
            return
        if target == "page":
            self._append_to_view(self._page_view, text)
            return
        if target == "both":
            self._append_to_view(self._document_view, text)
            self._append_to_view(self._page_view, text)
            return
        self._append_to_view(self._document_view, text)

    @staticmethod
    def _append_to_view(view: QPlainTextEdit, text: str) -> None:
        if not text:
            return
        view.moveCursor(QTextCursor.End)
        view.insertPlainText(text)
        view.moveCursor(QTextCursor.End)

    @staticmethod
    def _classify_line(line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return "document"

        upper_line = stripped.upper()
        if "[PAGE]" in upper_line:
            return "page"
        if "[DOC]" in upper_line:
            return "document"

        if "페이지" in stripped:
            return "page"
        if re.search(
            r"(^|[_/\\-])\d{2,6}\.json\b", stripped, flags=re.IGNORECASE
        ):
            return "page"
        lowered = stripped.lower()
        if ".json" in lowered and ("warning" in lowered or "경고" in stripped):
            return "page"
        return "document"
