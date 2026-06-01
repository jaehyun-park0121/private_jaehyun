from __future__ import annotations

from app.tabs.pre_parse.features.preview import PreParsePreviewMixin
from app.tabs.pre_parse.features.problem_sync_strict import PreParseProblemSyncStrictMixin
from app.tabs.pre_parse.features.row_builders import PreParseRowBuildersMixin
from app.tabs.pre_parse.features.state_ui import PreParseStateUiMixin


class PreParseWorkflowMixin(
    PreParseProblemSyncStrictMixin,
    PreParseStateUiMixin,
    PreParseRowBuildersMixin,
    PreParsePreviewMixin,
):
    pass
