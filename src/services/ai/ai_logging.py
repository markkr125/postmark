"""AI settings connection log — terminal + optional UI callbacks."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

_LOGGER_NAME = "postmark.ai"
_CONFIGURED = False
_UI_SINK: Callable[[str], None] | None = None


def configure_ai_logging() -> None:
    """Attach a stderr handler for AI provider setup (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)
    _CONFIGURED = True


def set_ui_log_sink(sink: Callable[[str], None] | None) -> None:
    """Register a GUI-thread callback (e.g. ``QPlainTextEdit.append``)."""
    global _UI_SINK
    _UI_SINK = sink


def _on_gui_thread() -> bool:
    try:
        from PySide6.QtCore import QCoreApplication, QThread

        app = QCoreApplication.instance()
        if app is None:
            return False
        return QThread.currentThread() is app.thread()
    except ImportError:
        return False


def log(message: str) -> None:
    """Write *message* to stderr; mirror to the UI sink only on the GUI thread."""
    configure_ai_logging()
    logging.getLogger(_LOGGER_NAME).info("%s", message)
    if _UI_SINK is not None and _on_gui_thread():
        try:
            _UI_SINK(message)
        except RuntimeError:
            # Tests may delete the settings dialog while async AI setup still logs.
            set_ui_log_sink(None)


__all__ = ["configure_ai_logging", "log", "set_ui_log_sink"]
