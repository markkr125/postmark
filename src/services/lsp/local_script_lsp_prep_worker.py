"""QThread worker that runs :func:`prepare_local_script_lsp_attach`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from services.lsp.local_script_lsp_prep import (
    LocalScriptLspPrepResult,
    prepare_local_script_lsp_attach,
)


class LocalScriptLspPrepWorker(QThread):
    """Run local-script mirror/index prep off the GUI thread."""

    finished_with = Signal(int, object)  # attach_token, LocalScriptLspPrepResult

    def __init__(
        self,
        attach_token: int,
        script_id: int,
        language: str,
        buffer_text: str,
        workspace: Path,
        parent: Any | None = None,
    ) -> None:
        """Store prep inputs; parent may be the hosting pane."""
        super().__init__(parent)
        self._attach_token = attach_token
        self._script_id = script_id
        self._language = language
        self._buffer_text = buffer_text
        self._workspace = workspace

    def run(self) -> None:
        """Execute prep unless the thread was interrupted."""
        if self.isInterruptionRequested():
            result = LocalScriptLspPrepResult(
                ok=False,
                target_uri=None,
                index_changed=False,
                error_message="prep interrupted",
            )
            self.finished_with.emit(self._attach_token, result)
            return
        result = prepare_local_script_lsp_attach(
            script_id=self._script_id,
            language=self._language,
            buffer_text=self._buffer_text,
            workspace=self._workspace,
        )
        self.finished_with.emit(self._attach_token, result)


__all__ = ["LocalScriptLspPrepWorker"]
