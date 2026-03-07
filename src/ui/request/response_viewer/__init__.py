"""Response viewer sub-package.

Re-exports :class:`ResponseViewerWidget` so external imports
(``from ui.request.response_viewer import ResponseViewerWidget``)
remain stable.
"""

from __future__ import annotations

from ui.request.response_viewer.viewer_widget import ResponseViewerWidget

__all__ = ["ResponseViewerWidget"]
