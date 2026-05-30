"""Collection runner shared widgets (config, results, worker).

The inline runner lives in :mod:`ui.request.folder_editor.runner_panel`.
"""

from __future__ import annotations

from .config import RunnerConfigView
from .results import RunnerResultsView
from .worker import RunnerWorker

__all__ = ["RunnerConfigView", "RunnerResultsView", "RunnerWorker"]
