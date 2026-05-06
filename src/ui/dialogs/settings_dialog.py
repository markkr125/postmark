"""Settings dialog — user preferences for appearance and behaviour.

Provides a category-list + detail-panel layout with Appearance, Tabs,
and Scripting pages.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, QThread, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.tab_settings_manager import (
    ACTIVATE_LEFT,
    ACTIVATE_MRU,
    ACTIVATE_RIGHT,
    LIMIT_CLOSE_UNCHANGED,
    LIMIT_CLOSE_UNUSED,
    MAX_TAB_LIMIT,
    MIN_TAB_LIMIT,
    WRAP_MULTIPLE_ROWS,
    WRAP_SINGLE_ROW,
    TabSettingsManager,
)
from ui.styling.theme_manager import (
    SCHEME_AUTO,
    SCHEME_DARK,
    SCHEME_LIGHT,
    SCHEMES,
    STYLE_FUSION,
    STYLES,
    ThemeManager,
)
from ui.widgets.deno_download_worker import DenoDownloadWorker
from services.scripting.runtime_settings import RuntimeSettings


class SettingsDialog(QDialog):
    """Modal settings dialog with category list and detail panels."""

    def __init__(
        self,
        theme_manager: ThemeManager | None,
        tab_settings_manager: TabSettingsManager | None = None,
        parent: QWidget | None = None,
        *,
        initial_category: str = "Appearance",
    ) -> None:
        """Initialise the settings dialog.

        *initial_category* is one of ``"Appearance"``, ``"Tabs"``, or
        ``"Scripting"`` (case-insensitive) and selects the list row and
        detail page on open.
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 340)
        self.resize(560, 380)
        self.setModal(True)

        self._tm = theme_manager
        self._tab_settings = tab_settings_manager or TabSettingsManager(self)
        self._deno_download_thread: QThread | None = None
        self._deno_download_worker: DenoDownloadWorker | None = None

        root = QVBoxLayout(self)

        # -- Splitter: category list | detail stack --------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Category list
        self._cat_list = QListWidget()
        self._cat_list.addItem("Appearance")
        self._cat_list.addItem("Tabs")
        self._cat_list.addItem("Scripting")
        self._cat_list.setFixedWidth(140)
        self._cat_list.setCurrentRow(0)
        self._cat_list.currentRowChanged.connect(self._on_category_changed)
        splitter.addWidget(self._cat_list)

        # Detail stack
        self._stack = QStackedWidget()
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(1, 1)

        # -- Appearance page -------------------------------------------
        self._build_appearance_page()
        self._build_tabs_page()
        self._build_scripting_page()

        # -- Button row ------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setIcon(phi("check"))
        apply_btn.setObjectName("primaryButton")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        close_btn = QPushButton("Close")
        close_btn.setIcon(phi("x"))
        close_btn.setObjectName("outlineButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        self._apply_initial_category(initial_category)

    def _apply_initial_category(self, name: str) -> None:
        """Select the settings category list row matching *name*."""
        options = ("Appearance", "Tabs", "Scripting")
        key = name.strip().casefold()
        for i, label in enumerate(options):
            if label.casefold() == key:
                self._cat_list.setCurrentRow(i)
                return

    # -- Page builders -------------------------------------------------

    def _build_appearance_page(self) -> None:
        """Build the Appearance settings page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        heading = QLabel("Appearance")
        heading.setObjectName("titleLabel")
        layout.addWidget(heading)

        # Style selector
        style_label = QLabel("Widget Style")
        style_label.setObjectName("sectionLabel")
        layout.addWidget(style_label)

        self._style_combo = QComboBox()
        for s in STYLES:
            display = f"{s} (recommended)" if s == STYLE_FUSION else s
            self._style_combo.addItem(display, userData=s)
        # Set current value
        current_style = self._tm.style if self._tm is not None else STYLE_FUSION
        idx = list(STYLES).index(current_style) if current_style in STYLES else 0
        self._style_combo.setCurrentIndex(idx)
        self._style_combo.setEnabled(self._tm is not None)
        layout.addWidget(self._style_combo)

        # Colour scheme selector
        scheme_label = QLabel("Colour Scheme")
        scheme_label.setObjectName("sectionLabel")
        layout.addWidget(scheme_label)

        self._scheme_combo = QComboBox()
        scheme_labels = {SCHEME_AUTO: "Auto-detect", SCHEME_LIGHT: "Light", SCHEME_DARK: "Dark"}
        for s in SCHEMES:
            self._scheme_combo.addItem(scheme_labels.get(s, s), userData=s)
        current_scheme = self._tm.scheme if self._tm is not None else SCHEME_AUTO
        idx = list(SCHEMES).index(current_scheme) if current_scheme in SCHEMES else 0
        self._scheme_combo.setCurrentIndex(idx)
        self._scheme_combo.setEnabled(self._tm is not None)
        layout.addWidget(self._scheme_combo)

        layout.addStretch()
        self._stack.addWidget(page)

    def _build_tabs_page(self) -> None:
        """Build the request-tab settings page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        heading = QLabel("Tabs")
        heading.setObjectName("titleLabel")
        layout.addWidget(heading)

        appearance_label = QLabel("Appearance")
        appearance_label.setObjectName("sectionLabel")
        layout.addWidget(appearance_label)

        wrap_mode_row = QHBoxLayout()
        wrap_mode_row.setContentsMargins(0, 0, 0, 0)
        wrap_mode_row.addWidget(QLabel("Tab rows"))
        self._wrap_mode_combo = QComboBox()
        self._wrap_mode_combo.addItem("Wrap onto multiple rows", userData=WRAP_MULTIPLE_ROWS)
        self._wrap_mode_combo.addItem("Keep a single row", userData=WRAP_SINGLE_ROW)
        for idx in range(self._wrap_mode_combo.count()):
            if self._wrap_mode_combo.itemData(idx) == self._tab_settings.wrap_mode:
                self._wrap_mode_combo.setCurrentIndex(idx)
                break
        wrap_mode_row.addWidget(self._wrap_mode_combo)
        wrap_mode_row.addStretch()
        layout.addLayout(wrap_mode_row)

        self._small_labels_check = QCheckBox("Use small font for labels")
        self._small_labels_check.setChecked(self._tab_settings.small_labels)
        layout.addWidget(self._small_labels_check)

        self._show_path_duplicates_check = QCheckBox("Show path for non-unique request names")
        self._show_path_duplicates_check.setChecked(self._tab_settings.show_path_for_duplicates)
        layout.addWidget(self._show_path_duplicates_check)

        self._mark_modified_check = QCheckBox("Mark modified requests")
        self._mark_modified_check.setChecked(self._tab_settings.mark_modified)
        layout.addWidget(self._mark_modified_check)

        self._show_full_path_hover_check = QCheckBox("Show full request path on hover")
        self._show_full_path_hover_check.setChecked(self._tab_settings.show_full_path_on_hover)
        layout.addWidget(self._show_full_path_hover_check)

        order_label = QLabel("Tab Order")
        order_label.setObjectName("sectionLabel")
        layout.addWidget(order_label)

        self._open_new_tabs_at_end_check = QCheckBox("Open new tabs at the end")
        self._open_new_tabs_at_end_check.setChecked(self._tab_settings.open_new_tabs_at_end)
        layout.addWidget(self._open_new_tabs_at_end_check)

        opening_label = QLabel("Opening Policy")
        opening_label.setObjectName("sectionLabel")
        layout.addWidget(opening_label)

        self._preview_tab_check = QCheckBox("Enable preview tab")
        self._preview_tab_check.setChecked(self._tab_settings.enable_preview_tab)
        layout.addWidget(self._preview_tab_check)

        closing_label = QLabel("Closing Policy")
        closing_label.setObjectName("sectionLabel")
        layout.addWidget(closing_label)

        limit_row = QHBoxLayout()
        limit_row.setContentsMargins(0, 0, 0, 0)
        limit_row.addWidget(QLabel("Tab limit"))
        self._tab_limit_spin = QSpinBox()
        self._tab_limit_spin.setRange(MIN_TAB_LIMIT, MAX_TAB_LIMIT)
        self._tab_limit_spin.setValue(self._tab_settings.tab_limit)
        limit_row.addWidget(self._tab_limit_spin)
        limit_row.addStretch()
        layout.addLayout(limit_row)

        self._tab_limit_policy_combo = QComboBox()
        self._tab_limit_policy_combo.addItem("Close unchanged", userData=LIMIT_CLOSE_UNCHANGED)
        self._tab_limit_policy_combo.addItem("Close unused", userData=LIMIT_CLOSE_UNUSED)
        for idx in range(self._tab_limit_policy_combo.count()):
            if self._tab_limit_policy_combo.itemData(idx) == self._tab_settings.tab_limit_policy:
                self._tab_limit_policy_combo.setCurrentIndex(idx)
                break
        layout.addWidget(self._tab_limit_policy_combo)

        self._activate_on_close_combo = QComboBox()
        self._activate_on_close_combo.addItem("Tab on the left", userData=ACTIVATE_LEFT)
        self._activate_on_close_combo.addItem("Tab on the right", userData=ACTIVATE_RIGHT)
        self._activate_on_close_combo.addItem("Most recently used tab", userData=ACTIVATE_MRU)
        for idx in range(self._activate_on_close_combo.count()):
            if self._activate_on_close_combo.itemData(idx) == self._tab_settings.activate_on_close:
                self._activate_on_close_combo.setCurrentIndex(idx)
                break
        layout.addWidget(self._activate_on_close_combo)

        layout.addStretch()
        self._stack.addWidget(page)

    def _build_scripting_page(self) -> None:
        """Build the Scripting settings page."""
        from ui.styling.theme_manager import _APP, _ORG

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        heading = QLabel("Scripting")
        heading.setObjectName("titleLabel")
        layout.addWidget(heading)

        self._enable_scripts_check = QCheckBox("Enable script execution")
        settings = QSettings(_ORG, _APP)
        enabled = settings.value("scripting/enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() not in {"0", "false", "no", "off", ""}
        self._enable_scripts_check.setChecked(bool(enabled))
        layout.addWidget(self._enable_scripts_check)

        note = QLabel(
            "When disabled, pre-request and test scripts are skipped\n"
            "for both single requests and collection runs."
        )
        note.setObjectName("mutedLabel")
        layout.addWidget(note)

        deno_label = QLabel("JavaScript (Deno)")
        deno_label.setObjectName("sectionLabel")
        layout.addWidget(deno_label)

        deno_row = QHBoxLayout()
        deno_row.setContentsMargins(0, 0, 0, 0)
        self._deno_path_edit = QLineEdit()
        self._deno_path_edit.setObjectName("settingsDenoPathEdit")
        self._deno_path_edit.setPlaceholderText("Default: PATH, then the managed download cache")
        raw_deno = settings.value("scripting/deno_path", "")
        if not isinstance(raw_deno, str):
            raw_deno = str(raw_deno or "")
        self._deno_path_edit.setText(raw_deno.strip())
        self._deno_path_edit.textChanged.connect(self._refresh_deno_status)
        deno_row.addWidget(self._deno_path_edit, 1)

        deno_browse = QPushButton("Browse")
        deno_browse.setObjectName("outlineButton")
        deno_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        deno_browse.clicked.connect(self._on_browse_deno)
        deno_row.addWidget(deno_browse)
        self._deno_autodetect_btn = QPushButton("Auto-detect")
        self._deno_autodetect_btn.setObjectName("settingsDenoAutodetectBtn")
        self._deno_autodetect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._deno_autodetect_btn.setToolTip(
            "Clear a custom path and use Deno on PATH or the managed cache."
        )
        self._deno_autodetect_btn.clicked.connect(self._on_deno_autodetect)
        deno_row.addWidget(self._deno_autodetect_btn)
        layout.addLayout(deno_row)

        deno_action_row = QHBoxLayout()
        deno_action_row.setContentsMargins(0, 0, 0, 0)
        self._deno_download_btn = QPushButton("Download managed Deno")
        self._deno_download_btn.setObjectName("settingsDenoDownloadBtn")
        self._deno_download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._deno_download_btn.setToolTip(
            "Download the pinned Deno build into the application data directory."
        )
        self._deno_download_btn.clicked.connect(self._on_deno_download)
        deno_action_row.addWidget(self._deno_download_btn)
        self._deno_download_progress = QProgressBar()
        self._deno_download_progress.setObjectName("settingsDenoDownloadProgress")
        self._deno_download_progress.setRange(0, 0)
        self._deno_download_progress.setFixedHeight(4)
        self._deno_download_progress.setTextVisible(False)
        self._deno_download_progress.setVisible(False)
        self._deno_download_progress.setMaximumWidth(200)
        deno_action_row.addWidget(self._deno_download_progress)
        deno_action_row.addStretch()
        layout.addLayout(deno_action_row)

        self._deno_status_label = QLabel()
        self._deno_status_label.setObjectName("settingsDenoStatusLabel")
        self._deno_status_label.setWordWrap(True)
        layout.addWidget(self._deno_status_label)

        py_label = QLabel("Python (RestrictedPython host)")
        py_label.setObjectName("sectionLabel")
        layout.addWidget(py_label)

        py_row = QHBoxLayout()
        py_row.setContentsMargins(0, 0, 0, 0)
        self._python_path_edit = QLineEdit()
        self._python_path_edit.setObjectName("settingsPythonPathEdit")
        self._python_path_edit.setPlaceholderText("Default: this application's Python interpreter")
        raw_py = settings.value("scripting/python_path", "")
        if not isinstance(raw_py, str):
            raw_py = str(raw_py or "")
        self._python_path_edit.setText(raw_py.strip())
        self._python_path_edit.textChanged.connect(self._refresh_python_status)
        py_row.addWidget(self._python_path_edit, 1)
        py_browse = QPushButton("Browse")
        py_browse.setObjectName("outlineButton")
        py_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        py_browse.clicked.connect(self._on_browse_python)
        py_row.addWidget(py_browse)
        self._python_reset_btn = QPushButton("Reset to app")
        self._python_reset_btn.setObjectName("outlineButton")
        self._python_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._python_reset_btn.setToolTip(
            "Use the current Postmark app Python (clear custom path)."
        )
        self._python_reset_btn.clicked.connect(self._on_python_reset)
        py_row.addWidget(self._python_reset_btn)
        layout.addLayout(py_row)

        self._python_status_label = QLabel()
        self._python_status_label.setObjectName("settingsPythonStatusLabel")
        self._python_status_label.setWordWrap(True)
        layout.addWidget(self._python_status_label)

        # Auto-save default
        auto_save_label = QLabel("Version Capture")
        auto_save_label.setObjectName("sectionLabel")
        layout.addWidget(auto_save_label)

        self._auto_save_default_check = QCheckBox("Auto-save scripts by default")
        auto_save_on = settings.value("scripting/auto_save_default", True)
        if isinstance(auto_save_on, str):
            auto_save_on = auto_save_on.lower() not in {"0", "false", "no", "off", ""}
        self._auto_save_default_check.setChecked(bool(auto_save_on))
        layout.addWidget(self._auto_save_default_check)

        auto_save_note = QLabel(
            "Automatically capture script versions while editing.\n"
            "Can be overridden per request or collection."
        )
        auto_save_note.setObjectName("mutedLabel")
        layout.addWidget(auto_save_note)

        self._refresh_deno_status()
        self._refresh_python_status()

        layout.addStretch()
        self._stack.addWidget(page)

    # -- Slots ---------------------------------------------------------

    def _on_category_changed(self, row: int) -> None:
        """Switch the detail stack to the selected category."""
        self._stack.setCurrentIndex(row)

    def _on_apply(self) -> None:
        """Persist settings and apply the theme."""
        style_data = self._style_combo.currentData()
        scheme_data = self._scheme_combo.currentData()

        if self._tm is not None:
            self._tm.style = style_data if isinstance(style_data, str) else STYLE_FUSION
            self._tm.scheme = scheme_data if isinstance(scheme_data, str) else SCHEME_AUTO
            self._tm.apply()

        wrap_mode = self._wrap_mode_combo.currentData()
        self._tab_settings.wrap_mode = (
            wrap_mode if isinstance(wrap_mode, str) else WRAP_MULTIPLE_ROWS
        )
        self._tab_settings.small_labels = self._small_labels_check.isChecked()
        self._tab_settings.show_path_for_duplicates = self._show_path_duplicates_check.isChecked()
        self._tab_settings.mark_modified = self._mark_modified_check.isChecked()
        self._tab_settings.show_full_path_on_hover = self._show_full_path_hover_check.isChecked()
        self._tab_settings.open_new_tabs_at_end = self._open_new_tabs_at_end_check.isChecked()
        self._tab_settings.enable_preview_tab = self._preview_tab_check.isChecked()
        self._tab_settings.tab_limit = self._tab_limit_spin.value()

        tab_limit_policy = self._tab_limit_policy_combo.currentData()
        self._tab_settings.tab_limit_policy = (
            tab_limit_policy if isinstance(tab_limit_policy, str) else LIMIT_CLOSE_UNUSED
        )

        activate_on_close = self._activate_on_close_combo.currentData()
        self._tab_settings.activate_on_close = (
            activate_on_close if isinstance(activate_on_close, str) else ACTIVATE_MRU
        )

        # Scripting
        from ui.styling.theme_manager import _APP, _ORG

        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", self._enable_scripts_check.isChecked())
        settings.setValue(
            "scripting/auto_save_default",
            self._auto_save_default_check.isChecked(),
        )

        d_text = self._deno_path_edit.text().strip()
        if d_text:
            RuntimeSettings.set_deno_path(d_text)
        else:
            RuntimeSettings.clear_deno_path()
        py_text = self._python_path_edit.text().strip()
        if py_text:
            RuntimeSettings.set_python_path(py_text)
        else:
            RuntimeSettings.clear_python_path()
        self._refresh_deno_status()
        self._refresh_python_status()

    def _provisional_deno_executable(self) -> str | None:
        """Deno path from the line edit, or auto-detect when the field is empty."""
        t = self._deno_path_edit.text().strip()
        if t:
            return t
        return RuntimeSettings.auto_detected_deno_path()

    def _provisional_python_executable(self) -> str:
        """Python path from the line edit, or the app default when empty."""
        t = self._python_path_edit.text().strip()
        if t:
            return t
        return sys.executable

    def _refresh_deno_status(self) -> None:
        """Update the Deno validation line under the text field."""
        cand = self._provisional_deno_executable()
        st = RuntimeSettings.validate_deno(cand)
        if st["available"]:
            ver = st["version"] or "Deno"
            self._deno_status_label.setText(ver)
        else:
            self._deno_status_label.setText(st["error"] or "Deno is not available.")
        self._deno_download_btn.setEnabled(not st["available"])
        if self._deno_download_thread is not None:
            self._deno_download_btn.setEnabled(False)

    def _refresh_python_status(self) -> None:
        """Update the Python validation line under the text field."""
        cand = self._provisional_python_executable()
        st = RuntimeSettings.validate_python(cand)
        if st["available"]:
            v = st["version"]
            self._python_status_label.setText(f"Valid — {v}" if v else "Valid")
        else:
            self._python_status_label.setText(
                st["error"] or "Python cannot load RestrictedPython with this path."
            )

    def _on_browse_deno(self) -> None:
        """Set the Deno path from a file dialog."""
        start = self._deno_path_edit.text().strip() or "/"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Deno executable",
            start,
            "Executables (*)",
        )
        if file_path:
            self._deno_path_edit.setText(file_path)

    def _on_browse_python(self) -> None:
        """Set the Python path from a file dialog."""
        start = self._python_path_edit.text().strip() or "/"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Python executable",
            start,
            "Executables (*)",
        )
        if file_path:
            self._python_path_edit.setText(file_path)

    def _on_deno_autodetect(self) -> None:
        """Clear a custom path so :meth:`RuntimeSettings.deno_path` can resolve."""
        self._deno_path_edit.clear()

    def _on_python_reset(self) -> None:
        """Clear a custom Python so :data:`sys.executable` is used on Apply."""
        self._python_path_edit.clear()

    def _on_deno_download(self) -> None:
        """Start the background Deno download; user-initiated only."""
        if self._deno_download_thread is not None:
            return
        self._deno_download_btn.setEnabled(False)
        self._deno_download_progress.setVisible(True)
        self._deno_download_progress.setRange(0, 0)

        self._deno_download_thread = QThread()
        self._deno_download_worker = DenoDownloadWorker()
        self._deno_download_worker.moveToThread(self._deno_download_thread)

        self._deno_download_thread.started.connect(self._deno_download_worker.run)
        self._deno_download_worker.progress.connect(self._on_deno_download_progress)
        self._deno_download_worker.finished.connect(self._on_deno_download_finished)
        self._deno_download_worker.error.connect(self._on_deno_download_error)

        self._deno_download_worker.finished.connect(self._deno_download_thread.quit)
        self._deno_download_worker.error.connect(self._deno_download_thread.quit)
        self._deno_download_worker.finished.connect(self._deno_download_worker.deleteLater)
        self._deno_download_worker.error.connect(self._deno_download_worker.deleteLater)
        self._deno_download_thread.finished.connect(self._deno_download_thread.deleteLater)
        self._deno_download_thread.finished.connect(self._on_deno_download_thread_done)

        self._deno_download_thread.start()

    def _on_deno_download_progress(self, received: int, total: int) -> None:
        """Update indeterminate or determinate download progress bar."""
        if total > 0:
            self._deno_download_progress.setRange(0, total)
            self._deno_download_progress.setValue(received)
        else:
            self._deno_download_progress.setRange(0, 0)

    def _on_deno_download_finished(self, _path: str) -> None:
        """Deno is installed; prefer the auto-resolved (managed) path."""
        self._deno_download_progress.setVisible(False)
        self._deno_path_edit.clear()
        self._refresh_deno_status()

    def _on_deno_download_error(self, err: str) -> None:
        """Show a download failure on the status label."""
        self._deno_download_progress.setVisible(False)
        self._deno_status_label.setText(f"Download failed: {err}")
        self._deno_download_btn.setEnabled(True)
        self._refresh_deno_status()

    def _on_deno_download_thread_done(self) -> None:
        """Clear thread state after a download attempt."""
        self._deno_download_thread = None
        self._deno_download_worker = None
