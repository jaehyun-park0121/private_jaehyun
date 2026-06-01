from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFrame, QGridLayout, QLabel, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app.tabs.misc_tools.base import BaseMiscToolApp
from app.tabs.misc_tools.loader import MiscToolAppLoader


class MiscToolCard(QFrame):
    clicked = pyqtSignal(str)
    PREFERRED_CARD_SIDE = 296
    MIN_CARD_SIDE = 148

    def __init__(self, app: BaseMiscToolApp, card_side: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app_id = app.metadata().app_id
        meta = app.metadata()
        self._card_side = -1
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setObjectName("miscToolCard")
        self.setToolTip(meta.description)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(6)

        title = QLabel(meta.app_name)
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        title.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; background: transparent;")

        path_label = QLabel(self._folder_stem(app, meta))
        path_label.setWordWrap(True)
        path_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        path_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        path_label.setStyleSheet("font-size: 11px; color: #64748b; background: transparent;")

        desc = QLabel(meta.summary)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        desc.setStyleSheet("font-size: 11px; color: #334155; background: transparent;")
        desc.setMaximumHeight(48)

        status = QLabel(meta.status_text)
        status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status.setStyleSheet(
            "background: #eef1f5; color: #334155; border-radius: 10px; padding: 3px 7px; font-size: 10px; font-weight: 700;"
        )

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(path_label)
        layout.addWidget(desc)
        layout.addStretch(1)
        layout.addWidget(status, alignment=Qt.AlignRight)

        self.setStyleSheet(
            """
            QFrame#miscToolCard {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 18px;
            }
            QFrame#miscToolCard:hover {
                background: #eef1f5;
                border: 1px solid #94a3b8;
            }
            """
        )
        self.set_card_side(card_side)

    @classmethod
    def _folder_stem(cls, app: BaseMiscToolApp, meta) -> str:
        source_file = getattr(app, "source_file", None)
        if source_file:
            try:
                return Path(source_file).resolve().parent.name
            except Exception:
                pass

        module_path = str(getattr(meta, "module_path", "") or "").strip()
        if module_path:
            path_obj = Path(module_path)
            if path_obj.suffix and path_obj.parent.name:
                return path_obj.parent.name
            if path_obj.name:
                return path_obj.name

        return str(getattr(meta, "app_id", "") or "unknown")

    def set_card_side(self, side: int) -> None:
        normalized = max(self.MIN_CARD_SIDE, min(self.PREFERRED_CARD_SIDE, int(side)))
        if normalized == self._card_side:
            return
        self._card_side = normalized
        self.setFixedSize(normalized, normalized)

    def hasHeightForWidth(self) -> bool:  # type: ignore[override]
        return True

    def heightForWidth(self, width: int) -> int:  # type: ignore[override]
        return width

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(self._card_side, self._card_side)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app_id)
        super().mousePressEvent(event)


class MiscToolsTabPage(QWidget):
    MAX_HORIZONTAL_COLUMNS = 6

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo_root = Path(__file__).resolve().parents[3]
        self._loader = MiscToolAppLoader(Path(__file__).resolve().parent / "apps")
        self._apps = self._loader.load_apps()
        self._cards: Dict[str, MiscToolCard] = {}
        self._card_columns = 0
        self._card_side = MiscToolCard.PREFERRED_CARD_SIDE
        self._layout_refresh_pending = False

        self.card_scroll = QScrollArea()
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setFrameShape(QFrame.NoFrame)
        self.card_host = QWidget()
        self.card_host.setObjectName("miscCardHost")
        self.card_grid = QGridLayout(self.card_host)
        self.card_grid.setContentsMargins(24, 28, 24, 24)
        self.card_grid.setHorizontalSpacing(32)
        self.card_grid.setVerticalSpacing(32)
        self.card_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.card_scroll.setWidget(self.card_host)
        self.card_scroll.viewport().installEventFilter(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.card_scroll)

        self.setStyleSheet(
            """
            MiscToolsTabPage {
                background: #f8fafc;
            }
            #miscCardHost {
                background: #f8fafc;
            }
            QScrollArea {
                background: transparent;
            }
            """
        )

        self._render_cards()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_layout_if_needed()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._schedule_layout_refresh()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.card_scroll.viewport() and event.type() == QEvent.Resize:
            self._refresh_layout_if_needed()
        return super().eventFilter(watched, event)

    def _schedule_layout_refresh(self) -> None:
        if self._layout_refresh_pending:
            return
        self._layout_refresh_pending = True
        QTimer.singleShot(0, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._layout_refresh_pending = False
        self._refresh_layout_if_needed(force=True)

    def _refresh_layout_if_needed(self, *, force: bool = False) -> None:
        columns, card_side = self._compute_grid_shape()
        if force or columns != self._card_columns or card_side != self._card_side:
            self._render_cards()

    def _compute_grid_shape(self) -> Tuple[int, int]:
        viewport_width = max(self.card_scroll.viewport().width(), 1)
        margins = self.card_grid.contentsMargins()
        usable_width = max(1, viewport_width - margins.left() - margins.right())
        spacing = max(self.card_grid.horizontalSpacing(), 0)
        min_slot = MiscToolCard.MIN_CARD_SIDE + spacing
        max_columns_by_min = max(1, (usable_width + spacing) // max(min_slot, 1))

        app_count = len(self._apps)
        max_columns_target = min(app_count, self.MAX_HORIZONTAL_COLUMNS) if app_count > 0 else 1

        # Default to filling horizontally up to MAX_HORIZONTAL_COLUMNS.
        # If width is insufficient, reduce columns and wrap to the next row.
        columns = min(max_columns_target, max_columns_by_min)
        columns = max(1, int(columns))
        card_side = (usable_width - spacing * (columns - 1)) // max(columns, 1)
        card_side = max(MiscToolCard.MIN_CARD_SIDE, min(MiscToolCard.PREFERRED_CARD_SIDE, card_side))
        return int(columns), int(card_side)

    def _render_cards(self) -> None:
        while self.card_grid.count():
            item = self.card_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards = {}

        columns, card_side = self._compute_grid_shape()
        self._card_columns = columns
        self._card_side = card_side
        for idx, app in enumerate(self._apps):
            card = MiscToolCard(app, card_side=card_side)
            card.clicked.connect(self._launch_app)
            self._cards[app.metadata().app_id] = card
            self.card_grid.addWidget(card, idx // columns, idx % columns, alignment=Qt.AlignTop | Qt.AlignLeft)

    def _selected_app(self, app_id: str) -> Optional[BaseMiscToolApp]:
        return next((app for app in self._apps if app.metadata().app_id == app_id), None)

    def _launch_app(self, app_id: str) -> None:
        app = self._selected_app(app_id)
        if app is None:
            return
        result = app.run_tool(self._repo_root)
        if result:
            return
        meta = app.metadata()
        QMessageBox.information(
            self,
            meta.app_name,
            f"{meta.summary}\n\n경로: {meta.module_path or '-'}\n\n{meta.description}",
        )
