"""Import dialog -- multi-tab dialog for importing collections, environments, and requests.

Mirrors the Postman import window with a paste area for cURL/JSON/URL,
drag-and-drop zone for files and folders, and a progress/results panel.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QMimeData, QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.import_parser.models import ImportSummary
from services.import_service import ImportService
from ui.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DROP_ZONE_ACTIVE_BG,
    COLOR_DROP_ZONE_BG,
    COLOR_DROP_ZONE_BORDER,
    COLOR_IMPORT_ERROR,
    COLOR_IMPORT_SUCCESS,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WHITE,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Background worker for import operations
# ------------------------------------------------------------------


class _ImportWorker(QObject):
    """Runs import operations on a background thread."""

    finished = Signal(dict)  # ImportSummary dict
    error = Signal(str)

    def __init__(self) -> None:
        """Initialise the import worker."""
        super().__init__()
        self._files: list[Path] = []
        self._folder: Path | None = None
        self._text: str | None = None

    def set_files(self, paths: list[Path]) -> None:
        """Configure the worker to import files."""
        self._files = paths

    def set_folder(self, path: Path) -> None:
        """Configure the worker to import a folder."""
        self._folder = path

    def set_text(self, text: str) -> None:
        """Configure the worker to import raw text."""
        self._text = text

    def run(self) -> None:
        """Execute the import and emit result."""
        try:
            if self._text is not None:
                result = ImportService.import_text(self._text)
            elif self._folder is not None:
                result = ImportService.import_folder(self._folder)
            elif self._files:
                result = ImportService.import_files(self._files)
            else:
                result = ImportSummary(
                    collections_imported=0,
                    requests_imported=0,
                    responses_imported=0,
                    environments_imported=0,
                    errors=["No input provided"],
                )
            self.finished.emit(dict(result))
        except Exception as exc:
            logger.exception("Import worker failed")
            self.error.emit(str(exc))


# ------------------------------------------------------------------
# Drag-and-drop zone widget
# ------------------------------------------------------------------


class _DropZone(QFrame):
    """A drag-and-drop area that accepts files and folders."""

    files_dropped = Signal(list)  # list[str] — file paths

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the drop zone with dashed border styling."""
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._set_default_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        # Icon/text
        icon_label = QLabel("\U0001f4e5")  # inbox tray emoji
        icon_label.setStyleSheet(f"font-size: 36px; color: {COLOR_TEXT_MUTED}; border: none;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        drop_label = QLabel("Drop anywhere to import")
        drop_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLOR_TEXT}; border: none;")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drop_label)

        # "Or select files or folders" with clickable links
        links_row = QHBoxLayout()
        links_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        or_label = QLabel("Or select")
        or_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; border: none;")
        links_row.addWidget(or_label)

        self.files_btn = QPushButton("files")
        self.files_btn.setFlat(True)
        self.files_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.files_btn.setStyleSheet(
            f"color: {COLOR_ACCENT}; text-decoration: underline; border: none; font-weight: bold;"
        )
        links_row.addWidget(self.files_btn)

        or2_label = QLabel("or")
        or2_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; border: none;")
        links_row.addWidget(or2_label)

        self.folders_btn = QPushButton("folders")
        self.folders_btn.setFlat(True)
        self.folders_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folders_btn.setStyleSheet(
            f"color: {COLOR_ACCENT}; text-decoration: underline; border: none; font-weight: bold;"
        )
        links_row.addWidget(self.folders_btn)

        layout.addLayout(links_row)

    def _set_default_style(self) -> None:
        """Apply the default (non-hover) drop zone styling."""
        self.setStyleSheet(
            f"_DropZone {{ background: {COLOR_DROP_ZONE_BG}; "
            f"border: 2px dashed {COLOR_DROP_ZONE_BORDER}; border-radius: 8px; }}"
        )

    def _set_active_style(self) -> None:
        """Apply the active (hovering) drop zone styling."""
        self.setStyleSheet(
            f"_DropZone {{ background: {COLOR_DROP_ZONE_ACTIVE_BG}; "
            f"border: 2px dashed {COLOR_ACCENT}; border-radius: 8px; }}"
        )

    # -- Drag events ---------------------------------------------------

    def dragEnterEvent(self, event: Any) -> None:
        """Accept drag events that carry file URLs."""
        mime: QMimeData = event.mimeData()
        if mime.hasUrls():
            event.acceptProposedAction()
            self._set_active_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: Any) -> None:
        """Reset styling when drag leaves."""
        self._set_default_style()
        event.accept()

    def dropEvent(self, event: Any) -> None:
        """Handle dropped files and folders."""
        self._set_default_style()
        mime: QMimeData = event.mimeData()
        if mime.hasUrls():
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


# ------------------------------------------------------------------
# Main import dialog
# ------------------------------------------------------------------


class ImportDialog(QDialog):
    """Multi-tab import dialog modelled after the Postman import window.

    Provides three input methods:
    1. **Paste area** — for cURL commands, raw JSON, or URLs.
    2. **Drag-and-drop zone** — for files and folders.
    3. **Other Sources tab** — placeholder for future integrations.

    Import operations run on a background thread. Results are shown in
    a progress/log panel at the bottom.
    """

    # Emitted when an import completes successfully so the caller can
    # refresh the collection tree.
    import_completed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the import dialog."""
        super().__init__(parent)
        self.setWindowTitle("Import")
        self.setMinimumSize(620, 520)
        self.resize(660, 560)
        self.setStyleSheet(f"background: {COLOR_WHITE}; color: {COLOR_TEXT};")

        self._thread: QThread | None = None
        self._worker: _ImportWorker | None = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the full dialog layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Title
        title = QLabel("Import your API or Local Files")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_TEXT};")
        root.addWidget(title)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{ border: 1px solid {COLOR_BORDER}; border-top: none; }}
            QTabBar::tab {{
                padding: 6px 16px; border: 1px solid {COLOR_BORDER};
                border-bottom: none; background: {COLOR_DROP_ZONE_BG};
            }}
            QTabBar::tab:selected {{
                background: {COLOR_WHITE}; font-weight: bold;
            }}
            """
        )

        # Tab 1: Postmark Import
        self._import_tab = QWidget()
        self._build_import_tab()
        self._tabs.addTab(self._import_tab, "Postmark Import")

        # Tab 2: Other Sources (placeholder)
        other_tab = QWidget()
        other_layout = QVBoxLayout(other_tab)
        other_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder = QLabel("Other import sources coming soon.")
        placeholder.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 13px;")
        other_layout.addWidget(placeholder)
        self._tabs.addTab(other_tab, "Other Sources")

        root.addWidget(self._tabs, stretch=1)

        # Result / progress area
        self._build_result_area(root)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 6px 20px; border: 1px solid {COLOR_BORDER};
                border-radius: 4px; background: {COLOR_DROP_ZONE_BG};
                font-weight: bold;
            }}
            QPushButton:hover {{ background: {COLOR_BORDER}; }}
            """
        )
        self._dismiss_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._dismiss_btn)

        root.addLayout(btn_row)

    def _build_import_tab(self) -> None:
        """Build the main Postmark Import tab contents."""
        layout = QVBoxLayout(self._import_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Paste area row
        paste_row = QHBoxLayout()
        self._paste_input = QLineEdit()
        self._paste_input.setPlaceholderText("Paste cURL, Raw text or URL...")
        self._paste_input.setStyleSheet(
            f"""
            QLineEdit {{
                padding: 8px 12px; border: 1px solid {COLOR_BORDER};
                border-radius: 4px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {COLOR_ACCENT}; }}
            """
        )
        self._paste_input.returnPressed.connect(self._on_paste_submit)
        paste_row.addWidget(self._paste_input, stretch=1)

        go_btn = QPushButton("Import")
        go_btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 8px 18px; background: {COLOR_ACCENT};
                color: white; border: none; border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
            """
        )
        go_btn.clicked.connect(self._on_paste_submit)
        paste_row.addWidget(go_btn)

        layout.addLayout(paste_row)

        # Tip label
        tip = QLabel("Tip: You can also paste a full JSON collection or environment here.")
        tip.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(tip)

        # 2. Drag-and-drop zone
        self._drop_zone = _DropZone()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        self._drop_zone.files_btn.clicked.connect(self._on_select_files)
        self._drop_zone.folders_btn.clicked.connect(self._on_select_folder)
        layout.addWidget(self._drop_zone, stretch=1)

    def _build_result_area(self, parent_layout: QVBoxLayout) -> None:
        """Build the progress bar and result log at the bottom."""
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setStyleSheet(
            f"QProgressBar {{ border: none; background: {COLOR_DROP_ZONE_BG}; }}"
            f"QProgressBar::chunk {{ background: {COLOR_ACCENT}; }}"
        )
        self._progress_bar.hide()
        parent_layout.addWidget(self._progress_bar)

        # Log scroll area
        self._result_scroll = QScrollArea()
        self._result_scroll.setWidgetResizable(True)
        self._result_scroll.setMaximumHeight(120)
        self._result_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {COLOR_BORDER}; border-radius: 4px; }}"
        )
        self._result_scroll.hide()

        self._result_log = QTextEdit()
        self._result_log.setReadOnly(True)
        self._result_log.setStyleSheet(
            f"QTextEdit {{ font-size: 12px; color: {COLOR_TEXT}; border: none; padding: 6px; }}"
        )
        self._result_scroll.setWidget(self._result_log)
        parent_layout.addWidget(self._result_scroll)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def _on_paste_submit(self) -> None:
        """Handle paste-area import (cURL / JSON / URL)."""
        text = self._paste_input.text().strip()
        if not text:
            return
        self._start_import_text(text)

    def _on_select_files(self) -> None:
        """Open a file picker for JSON files."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files to import",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if paths:
            self._start_import_files([Path(p) for p in paths])

    def _on_select_folder(self) -> None:
        """Open a folder picker."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to import"
        )
        if folder:
            self._start_import_folder(Path(folder))

    def _on_files_dropped(self, paths: list[str]) -> None:
        """Handle files/folders dropped onto the drop zone."""
        path_objs = [Path(p) for p in paths]

        # If a single directory was dropped, import as folder.
        if len(path_objs) == 1 and path_objs[0].is_dir():
            self._start_import_folder(path_objs[0])
        else:
            self._start_import_files(path_objs)

    # ------------------------------------------------------------------
    # Import execution (background thread)
    # ------------------------------------------------------------------

    def _start_import_files(self, paths: list[Path]) -> None:
        """Launch a background import for the given file paths."""
        worker = _ImportWorker()
        worker.set_files(paths)
        self._run_worker(worker)

    def _start_import_folder(self, path: Path) -> None:
        """Launch a background import for a folder."""
        worker = _ImportWorker()
        worker.set_folder(path)
        self._run_worker(worker)

    def _start_import_text(self, text: str) -> None:
        """Launch a background import for pasted text."""
        worker = _ImportWorker()
        worker.set_text(text)
        self._run_worker(worker)

    def _run_worker(self, worker: _ImportWorker) -> None:
        """Execute the import worker on a background thread."""
        # Clean up any previous thread
        self._cleanup_thread()

        self._progress_bar.show()
        self._result_scroll.show()
        self._result_log.clear()
        self._result_log.append("Importing...")

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_import_finished)
        worker.error.connect(self._on_import_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        self._thread = thread
        self._worker = worker

        thread.start()

    def _on_import_finished(self, summary: dict[str, Any]) -> None:
        """Handle successful import completion."""
        self._progress_bar.hide()
        self._result_log.clear()

        colls = summary.get("collections_imported", 0)
        reqs = summary.get("requests_imported", 0)
        resps = summary.get("responses_imported", 0)
        envs = summary.get("environments_imported", 0)
        errors = summary.get("errors", [])

        parts: list[str] = []
        if colls:
            parts.append(f"{colls} collection(s)")
        if reqs:
            parts.append(f"{reqs} request(s)")
        if resps:
            parts.append(f"{resps} saved response(s)")
        if envs:
            parts.append(f"{envs} environment(s)")

        if parts:
            msg = "Imported " + ", ".join(parts) + "."
            self._result_log.append(
                f'<span style="color: {COLOR_IMPORT_SUCCESS}; font-weight: bold;">{msg}</span>'
            )
        else:
            self._result_log.append("No data was imported.")

        for err in errors:
            self._result_log.append(
                f'<span style="color: {COLOR_IMPORT_ERROR};">{err}</span>'
            )

        if parts:
            self.import_completed.emit()

        self._cleanup_thread()

    def _on_import_error(self, message: str) -> None:
        """Handle import worker error."""
        self._progress_bar.hide()
        self._result_log.clear()
        self._result_log.append(
            f'<span style="color: {COLOR_IMPORT_ERROR}; font-weight: bold;">Import failed: {message}</span>'
        )
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Clean up the background thread and worker."""
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(3000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
