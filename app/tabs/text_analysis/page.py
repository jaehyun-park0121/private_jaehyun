from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QWidget

from app.common.panel_layout import DEFAULT_THREE_PANEL_SPLITTER_SIZES

from .features.page_support import TextAnalysisPageSupportMixin
from .features.snapshot_flow import TextAnalysisSnapshotFlowMixin
from .features.workflow import TextAnalysisWorkflowMixin
from .panels.center_panel import CenterPanelWidget
from .panels.left_panel import TextAnalysisLeftPanelWidget
from .panels.right_panel import RightPanelWidget


class TextAnalysisTabPage(
    TextAnalysisPageSupportMixin,
    TextAnalysisSnapshotFlowMixin,
    TextAnalysisWorkflowMixin,
    QWidget,
):
    def __init__(
        self,
        *,
        project_root: Optional[Path] = None,
        config: Optional[dict] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[3]
        self.config = copy.deepcopy(config or {})
        self._status_callback = status_callback
        self._initial_splitter_sizes_applied = False
        self._initial_left_panel_minimum_width = 0

        self._initialize_text_analysis_state()
        self._initialize_media_store_state()
        self._initialize_tool_run_state()
        self._initialize_text_analysis_ui_state()

        self.left_panel = TextAnalysisLeftPanelWidget()
        self.center_panel = CenterPanelWidget()
        self.right_panel = RightPanelWidget()
        self.center_panel.set_active_tool_id(self.left_panel.selected_tool_id())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.center_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        self._splitter = splitter

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(splitter, 1)

        self._refresh_special_char_label_options()
        self._wire_events()
        self._configure_problem_menu()
        self._apply_placeholder_state()
        QTimer.singleShot(0, self._ensure_initial_splitter_sizes)

    def _apply_initial_splitter_sizes(self) -> None:
        self._initial_left_panel_minimum_width = self.left_panel.minimumWidth()
        self.left_panel.setMinimumWidth(DEFAULT_THREE_PANEL_SPLITTER_SIZES[0])
        self.left_panel.setMaximumWidth(DEFAULT_THREE_PANEL_SPLITTER_SIZES[0])
        self._splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        QTimer.singleShot(0, self._release_initial_left_panel_width)

    def _release_initial_left_panel_width(self) -> None:
        self.left_panel.setMaximumWidth(16777215)
        self.left_panel.setMinimumWidth(self._initial_left_panel_minimum_width)

    def _ensure_initial_splitter_sizes(self) -> None:
        if self._initial_splitter_sizes_applied:
            return
        self._apply_initial_splitter_sizes()
        self._initial_splitter_sizes_applied = True
