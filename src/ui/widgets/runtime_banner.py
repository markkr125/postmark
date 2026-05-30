"""Runtime download banner — prompts the user to install or configure Deno.

Shown above a JavaScript script editor when :class:`RuntimeSettings` reports
no usable Deno executable (PATH, managed install, or Settings custom path).
The banner includes a link to open Scripting settings, a download button, and
a progress bar.  It stays visible until Deno becomes available (no dismiss
control).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from ui.styling.icons import phi
from ui.widgets.deno_download_worker import DenoDownloadWorker

# Rich text: link href is handled in :meth:`RuntimeBanner._on_message_link`.
_BANNER_HTML = (
    'JavaScript scripts run with Deno. <a href="action:scripting">Open Scripting settings</a> '
    "to choose a path, or use <b>Download Deno</b> for the managed runtime."
)


class RuntimeBanner(QFrame):
    """Thin banner prompting the user to download the Deno runtime.

    Signals:
        download_completed: Emitted when the Deno binary is installed.
        open_settings_clicked: Emitted when the user clicks the Scripting settings link.
    """

    download_completed = Signal()
    open_settings_clicked = Signal()

    def __init__(self, parent: QFrame | None = None) -> None:
        """Initialise the banner with link, download button, and progress bar."""
        super().__init__(parent)
        self.setObjectName("RuntimeBanner")

        self._thread: QThread | None = None
        self._worker: DenoDownloadWorker | None = None

        # -- Layout ----------------------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # Row 1: icon + message + download.
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(phi("warning", size=16).pixmap(16, 16))
        row.addWidget(icon_label)

        self._message = QLabel()
        self._message.setObjectName("bannerMessage")
        self._message.setWordWrap(True)
        self._set_message_rich_default()
        self._message.setOpenExternalLinks(False)
        self._message.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._message.linkActivated.connect(self._on_message_link)
        row.addWidget(self._message, 1)

        self._download_btn = QPushButton("Download Deno")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setObjectName("bannerDownloadBtn")
        self._download_btn.clicked.connect(self._start_download)
        row.addWidget(self._download_btn)

        outer.addLayout(row)

        # Row 2: progress bar + status (hidden by default).
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        outer.addWidget(self._progress_bar)

        self._status_label = QLabel()
        self._status_label.setObjectName("mutedLabel")
        self._status_label.setVisible(False)
        outer.addWidget(self._status_label)

    def _set_message_rich_default(self) -> None:
        """Set the default HTML message (link to Scripting settings)."""
        self._message.setTextFormat(Qt.TextFormat.RichText)
        self._message.setText(_BANNER_HTML)

    def _set_message_plain(self, text: str) -> None:
        """Set a plain-text status line (install result or error)."""
        self._message.setTextFormat(Qt.TextFormat.PlainText)
        self._message.setText(text)

    def _on_message_link(self, url: str) -> None:
        """Handle the in-message link to open Settings on the Scripting page."""
        if url == "action:scripting":
            self.open_settings_clicked.emit()

    # -- Download flow -------------------------------------------------

    def _start_download(self) -> None:
        """Launch the background download."""
        if self._thread is not None:
            return

        self._set_message_rich_default()
        self._download_btn.setEnabled(False)
        self._download_btn.setText("Downloading\u2026")
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._status_label.setVisible(True)
        self._status_label.setText("Connecting\u2026")

        self._thread = QThread()
        self._worker = DenoDownloadWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.error.connect(self._on_download_error)

        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_cleanup)

        self._thread.start()

    def _on_progress(self, received: int, total: int) -> None:
        """Update the progress bar."""
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(received)
            mb_received = received / 1_048_576
            mb_total = total / 1_048_576
            self._status_label.setText(f"Downloading\u2026 {mb_received:.1f} / {mb_total:.1f} MB")
        else:
            self._progress_bar.setRange(0, 0)
            mb_received = received / 1_048_576
            self._status_label.setText(f"Downloading\u2026 {mb_received:.1f} MB")

    def _on_download_finished(self, path: str) -> None:
        """Handle successful download."""
        self._set_message_plain("Deno runtime installed successfully.")
        self._download_btn.setVisible(False)
        self._progress_bar.setVisible(False)
        self._status_label.setText(path)
        self.download_completed.emit()

    def _on_download_error(self, error: str) -> None:
        """Handle download failure — show error and retry button."""
        self._set_message_plain(f"Download failed: {error}")
        self._download_btn.setEnabled(True)
        self._download_btn.setText("Retry")
        self._progress_bar.setVisible(False)
        self._status_label.setVisible(False)

    def _on_thread_cleanup(self) -> None:
        """Reset thread references after the worker thread finishes."""
        self._thread = None
        self._worker = None
