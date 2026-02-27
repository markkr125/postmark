"""History panel showing recently sent HTTP requests.

Tracks requests that have been sent during the current session and
displays them in a scrollable list with method, URL, status, and timing.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui.theme import COLOR_BORDER, method_color

# Maximum number of history entries to keep
_MAX_HISTORY_ENTRIES = 50


class HistoryEntry:
    """Data class for a single history entry."""

    def __init__(
        self,
        method: str,
        url: str,
        status_code: int | None = None,
        elapsed_ms: float = 0,
    ) -> None:
        """Store a history entry."""
        self.method = method
        self.url = url
        self.status_code = status_code
        self.elapsed_ms = elapsed_ms


class HistoryPanel(QWidget):
    """Panel showing recently sent HTTP requests.

    Signals:
        entry_clicked(str, str): Emitted with ``(method, url)`` when a
            history entry is clicked.
    """

    entry_clicked = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the history panel."""
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QHBoxLayout()
        title = QLabel("History")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("linkButton")
        clear_btn.clicked.connect(self.clear)
        header.addWidget(clear_btn)
        root.addLayout(header)

        # Scroll area for entries
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"border-top: 1px solid {COLOR_BORDER};")
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(0)
        self._scroll_layout.addStretch()
        self._scroll.setWidget(self._scroll_content)
        root.addWidget(self._scroll, 1)

        self._entries: list[HistoryEntry] = []

    def add_entry(
        self,
        method: str,
        url: str,
        status_code: int | None = None,
        elapsed_ms: float = 0,
    ) -> None:
        """Add a new history entry at the top."""
        entry = HistoryEntry(method, url, status_code, elapsed_ms)
        self._entries.insert(0, entry)
        if len(self._entries) > _MAX_HISTORY_ENTRIES:
            self._entries = self._entries[:_MAX_HISTORY_ENTRIES]
        self._rebuild_list()

    def clear(self) -> None:
        """Remove all history entries."""
        self._entries.clear()
        self._rebuild_list()

    @property
    def entries(self) -> list[HistoryEntry]:
        """Return the current list of history entries."""
        return list(self._entries)

    def _rebuild_list(self) -> None:
        """Rebuild the displayed list of history entries."""
        # Remove old widgets (keep the trailing stretch)
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        for entry in self._entries:
            row = self._make_entry_widget(entry)
            idx = self._scroll_layout.count() - 1  # insert before stretch
            self._scroll_layout.insertWidget(idx, row)

    def _make_entry_widget(self, entry: HistoryEntry) -> QWidget:
        """Create a widget row for a single history entry."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        method_label = QLabel(entry.method)
        color = method_color(entry.method)
        method_label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 11px; font-family: monospace;"
        )
        method_label.setFixedWidth(40)
        layout.addWidget(method_label)

        url_label = QLabel(entry.url)
        url_label.setWordWrap(False)
        layout.addWidget(url_label, 1)

        if entry.status_code is not None:
            status = QLabel(str(entry.status_code))
            status.setObjectName("mutedLabel")
            layout.addWidget(status)

        if entry.elapsed_ms:
            time_label = QLabel(f"{entry.elapsed_ms:.0f}ms")
            time_label.setObjectName("mutedLabel")
            layout.addWidget(time_label)

        row.setStyleSheet(f"QWidget {{ border-bottom: 1px solid {COLOR_BORDER}; }}")
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setProperty("entry_method", entry.method)
        row.setProperty("entry_url", entry.url)
        row.installEventFilter(self)
        return row

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Emit ``entry_clicked`` when a history row is pressed."""
        if event.type() == QEvent.Type.MouseButtonPress:
            method = obj.property("entry_method")
            url = obj.property("entry_url")
            if method is not None and url is not None:
                self.entry_clicked.emit(str(method), str(url))
                return True
        return super().eventFilter(obj, event)
        return super().eventFilter(obj, event)
