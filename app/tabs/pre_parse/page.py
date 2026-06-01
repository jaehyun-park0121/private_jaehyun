from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QSplitter, QVBoxLayout, QWidget

from app.common.panel_layout import DEFAULT_THREE_PANEL_SPLITTER_SIZES
from app.common.top_bar import TopBarWidget

from .features.media_store import PreParseMediaStoreMixin
from .features.page_support import PreParsePageSupportMixin
from .features.results.aggregator import ResultAggregator
from .features.results.exporter import ResultExporter
from .features.run_flow import PreParseRunFlowMixin
from .features.snapshot_flow import PreParseSnapshotFlowMixin
from .features.workflow import PreParseWorkflowMixin
from .panels.center_panel import CenterPanelWidget
from .panels.left_panel import LeftPanelWidget
from .panels.right_panel import RightPanelWidget
from .plugin_system.loader import PluginLoader
from .plugin_system.registry import CheckRegistry
from .plugin_system.runner import CheckRunner


class PreParseTabPage(
    PreParseWorkflowMixin,
    PreParseMediaStoreMixin,
    PreParseSnapshotFlowMixin,
    PreParseRunFlowMixin,
    PreParsePageSupportMixin,
    QWidget,
):
    def __init__(
        self,
        *,
        project_root: Path,
        config: dict,
        top_bar: TopBarWidget,
        status_callback: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = Path(project_root)
        self.config = copy.deepcopy(config)
        self.top_bar = top_bar
        self._status_callback = status_callback
        self._initial_splitter_sizes_applied = False
        self._initial_left_panel_minimum_width = 0

        self.registry = CheckRegistry()
        self.plugin_loader = PluginLoader(self.project_root / "app" / "tabs" / "pre_parse" / "plugins")
        self.check_runner = CheckRunner(self.registry)
        self.aggregator = ResultAggregator()
        self.exporter = ResultExporter(self.project_root / "outputs")
        self._label_color_map = self._load_label_color_map()

        self._initialize_pre_parse_state()
        self._initialize_preview_state()
        self._initialize_live_run_state()

        self.left_panel = LeftPanelWidget()
        self.center_panel = CenterPanelWidget()
        self.right_panel = RightPanelWidget()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.center_panel)
        splitter.addWidget(self.right_panel)
        splitter.setCollapsible(0, True)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes(DEFAULT_THREE_PANEL_SPLITTER_SIZES)
        self._splitter = splitter

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(splitter, 1)

        self._wire_pre_parse_events()
        self._load_plugins()
        self.left_panel.refresh_width_constraints()
        self._configure_problem_menu()
        QTimer.singleShot(0, self._ensure_initial_splitter_sizes)

    def _initialize_preview_state(self) -> None:
        self._preview_cache_dir = self.project_root / ".cache" / "preview_images"
        self._preview_cache_dir.mkdir(parents=True, exist_ok=True)
        self._json_cache_dir = self.project_root / ".cache" / "preview_json"
        self._json_cache_dir.mkdir(parents=True, exist_ok=True)
        self._preview_image_cache: Dict[str, str] = {}
        self._preview_json_cache: Dict[str, str] = {}
        self._json_payload_cache: Dict[str, Dict] = {}
        self._media_row_index: Dict[Tuple[str, str, str], dict] = {}

    def _initialize_live_run_state(self) -> None:
        self._pre_parse_live_bundles: Dict[str, dict] = {}
        self._pre_parse_live_book_totals: Dict[str, int] = {}
        self._pre_parse_live_book_completed: Dict[str, int] = {}
        self._pre_parse_live_displayed_books: set[str] = set()

    def _reset_live_run_state(self) -> None:
        self._pre_parse_live_bundles = {}
        self._pre_parse_live_book_totals = {}
        self._pre_parse_live_book_completed = {}
        self._pre_parse_live_displayed_books = set()

    def apply_shared_settings(
        self,
        config: dict,
        *,
        show_message: bool = False,
        refresh_s3: bool = True,
    ) -> None:
        self.config = copy.deepcopy(config)
        if refresh_s3:
            self.refresh_books_from_s3(show_message=show_message)

    def is_running(self) -> bool:
        return bool(self._pre_parse_is_running or self._pre_parse_snapshot_loading)

    def refresh_books_from_s3(self, *, show_message: bool = False) -> None:
        self._refresh_books_from_s3(show_message=show_message)

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
