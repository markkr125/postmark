"""Debug console panel showing application logs.

Captures Python log output and displays it in a scrollable text area.
Attaches a ``logging.Handler`` to the root logger so all log calls
are captured and displayed with thread-safe signal delivery.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ui.icons import phi

# Maximum number of log lines kept in the console output.
_MAX_LOG_LINES = 2000


class _LogSignalBridge(QObject):
    """Bridge between Python logging and Qt signals.

    ``logging.Handler`` callbacks may fire on any thread.  This QObject
    converts them into a signal that is safely delivered to the GUI thread.
    """

    log_message = Signal(str)


class _QtLogHandler(logging.Handler):
    """Logging handler that emits messages via a Qt signal bridge."""

    def __init__(self, bridge: _LogSignalBridge) -> None:
        """Initialise with the signal bridge."""
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        """Format the record and emit via the signal bridge."""
        try:
            msg = self.format(record)
            self._bridge.log_message.emit(msg)
        except Exception:
            self.handleError(record)


class ConsolePanel(QWidget):
    """Debug console widget that displays application log output.

    Attaches a ``logging.Handler`` to the root logger so all ``logger.info``,
    ``logger.warning``, etc. calls are captured and displayed.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the console panel and attach the log handler."""
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QHBoxLayout()
        title = QLabel("Console")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setIcon(phi("eraser"))
        clear_btn.setObjectName("linkButton")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        root.addLayout(header)

        # Console output
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setObjectName("consoleOutput")
        root.addWidget(self._output, 1)

        # Set up log handler
        self._bridge = _LogSignalBridge()
        self._bridge.log_message.connect(self._append_log)
        self._handler = _QtLogHandler(self._bridge)
        self._handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-5s %(name)s \u2014 %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logging.getLogger().addHandler(self._handler)

    @Slot(str)
    def _append_log(self, message: str) -> None:
        """Append a log message to the console output."""
        self._output.append(message)

        # Cap the document size to avoid unbounded memory growth.
        doc = self._output.document()
        if doc and doc.blockCount() > _MAX_LOG_LINES:
            cursor = self._output.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(
                cursor.MoveOperation.Down,
                cursor.MoveMode.KeepAnchor,
                doc.blockCount() - _MAX_LOG_LINES,
            )
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove the trailing newline

        # Auto-scroll to bottom
        sb = self._output.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _clear(self) -> None:
        """Clear the console output."""
        self._output.clear()

    def cleanup(self) -> None:
        """Remove the log handler (call on shutdown)."""
        logging.getLogger().removeHandler(self._handler)
        logging.getLogger().removeHandler(self._handler)
        logging.getLogger().removeHandler(self._handler)
        logging.getLogger().removeHandler(self._handler)
        logging.getLogger().removeHandler(self._handler)
