"""Runtime download banner — prompts the user to install Deno.

Shown above the script editor when a script uses features that require
the Deno runtime (``async``/``await``, ``require("npm:...")``).
The banner includes a download button, progress bar, and dismiss button.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ui.styling.icons import phi


class _DownloadWorker(QObject):
    """Background worker that downloads the Deno binary."""

    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def run(self) -> None:
        """Download Deno and emit progress updates."""
        from services.scripting.deno_manager import DenoManager

        try:
            path = DenoManager.download(
                progress_callback=lambda received, total: self.progress.emit(received, total),
            )
            self.finished.emit(str(path))
        except Exception as exc:
            self.error.emit(str(exc))


class RuntimeBanner(QFrame):
    """Thin banner prompting the user to download the Deno runtime.

    Signals:
        download_completed: Emitted when the Deno binary is installed.
        dismissed: Emitted when the user clicks the dismiss button.
    """

    download_completed = Signal()
    dismissed = Signal()

    def __init__(self, parent: QFrame | None = None) -> None:
        """Initialise the banner with download button and progress bar."""
        super().__init__(parent)
        self.setObjectName("RuntimeBanner")

        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None

        # -- Layout ----------------------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # Row 1: icon + message + buttons.
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(phi("warning", size=16).pixmap(16, 16))
        row.addWidget(icon_label)

        self._message = QLabel("This script uses features that require the Deno runtime.")
        self._message.setObjectName("bannerMessage")
        row.addWidget(self._message, 1)

        self._download_btn = QPushButton("Download Deno")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setObjectName("bannerDownloadBtn")
        self._download_btn.clicked.connect(self._start_download)
        row.addWidget(self._download_btn)

        self._dismiss_btn = QPushButton()
        self._dismiss_btn.setIcon(phi("x", size=14))
        self._dismiss_btn.setFixedSize(24, 24)
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.setObjectName("iconButton")
        self._dismiss_btn.setToolTip("Dismiss")
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        row.addWidget(self._dismiss_btn)

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

    # -- Download flow -------------------------------------------------

    def _start_download(self) -> None:
        """Launch the background download."""
        if self._thread is not None:
            return

        self._download_btn.setEnabled(False)
        self._download_btn.setText("Downloading\u2026")
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)
        self._status_label.setVisible(True)
        self._status_label.setText("Connecting\u2026")

        self._thread = QThread()
        self._worker = _DownloadWorker()
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
        self._message.setText("Deno runtime installed successfully.")
        self._download_btn.setVisible(False)
        self._progress_bar.setVisible(False)
        self._status_label.setText(path)
        self.download_completed.emit()

    def _on_download_error(self, error: str) -> None:
        """Handle download failure — show error and retry button."""
        self._message.setText(f"Download failed: {error}")
        self._download_btn.setEnabled(True)
        self._download_btn.setText("Retry")
        self._progress_bar.setVisible(False)
        self._status_label.setVisible(False)

    def _on_thread_cleanup(self) -> None:
        """Reset thread references after the worker thread finishes."""
        self._thread = None
        self._worker = None

    def _on_dismiss(self) -> None:
        """Hide the banner and emit the dismissed signal."""
        self.setVisible(False)
        self.dismissed.emit()
