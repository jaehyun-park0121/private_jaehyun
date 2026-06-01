from __future__ import annotations

from .media_store import TextAnalysisMediaStoreMixin
from .problem_sync_strict import TextAnalysisProblemSyncStrictMixin
from .preview import TextAnalysisPreviewMixin
from .run_flow import TextAnalysisRunFlowMixin
from .row_builders import TextAnalysisRowBuildersMixin
from .state_ui import TextAnalysisStateUiMixin


class TextAnalysisWorkflowMixin(
    TextAnalysisProblemSyncStrictMixin,
    TextAnalysisRunFlowMixin,
    TextAnalysisStateUiMixin,
    TextAnalysisRowBuildersMixin,
    TextAnalysisPreviewMixin,
    TextAnalysisMediaStoreMixin,
):
    pass
