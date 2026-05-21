"""Settings dialog — user preferences for appearance and behaviour.

Provides a category-list + detail-panel layout with Appearance, Tabs,
and Scripting pages.
"""

from __future__ import annotations

import contextlib
import sys
import uuid
from typing import Any, Literal, cast

from PySide6.QtCore import QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.scripting.runtime_settings import (
    PyPIConfig,
    PyPIIndex,
    RegistryEntry,
    RuntimeSettings,
)
from services.scripting.secret_store import backend_status
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
        # Sized as a percentage of the available screen so the dialog scales
        # with the user's monitor; clamped to a generous floor so detail
        # panels (Tabs, Scripting) don't squash on small displays.
        screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            min_w = max(760, int(geom.width() * 0.35))
            min_h = max(520, int(geom.height() * 0.45))
            init_w = max(min_w, int(geom.width() * 0.50))
            init_h = max(min_h, int(geom.height() * 0.60))
        else:
            min_w, min_h = 760, 520
            init_w, init_h = 900, 620
        self.setMinimumSize(min_w, min_h)
        self.resize(init_w, init_h)
        self.setModal(True)

        self._tm = theme_manager
        self._tab_settings = tab_settings_manager or TabSettingsManager(self)
        self._deno_download_thread: QThread | None = None
        self._deno_download_worker: DenoDownloadWorker | None = None

        root = QVBoxLayout(self)

        # -- Splitter: category list | detail stack --------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Category tree — wider than the old flat list so the Private packages
        # branch (with provider children) breathes. Splitter still owns the
        # exact width so it doesn't claim a fixed slice of the dialog.
        self._cat_tree = QTreeWidget()
        self._cat_tree.setHeaderHidden(True)
        self._cat_tree.setMaximumWidth(220)
        self._cat_tree.setMinimumWidth(160)
        self._cat_tree.setRootIsDecorated(True)
        self._cat_tree.setIndentation(14)
        self._cat_tree.currentItemChanged.connect(self._on_category_changed)
        splitter.addWidget(self._cat_tree)

        # Detail stack — each tree leaf maps to a stack page via the item's
        # ``UserRole`` page index. Parent items (e.g. "Private packages")
        # also point at a landing page so clicking the group header shows an
        # overview rather than an empty pane.
        self._stack = QStackedWidget()
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, max(1, init_w - 180)])

        # Build pages first (populates the stack), then add tree nodes that
        # reference the stack indices via ``UserRole``.
        self._page_indices: dict[str, int] = {}
        self._build_appearance_page()
        self._build_tabs_page()
        self._build_scripting_page()
        self._build_private_packages_pages()
        self._populate_category_tree()

        # -- Button row ------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        # Apply uses an explicit light icon colour; the default
        # ``phi("check")`` renders in ``COLOR_TEXT_MUTED`` which disappears on
        # the accent-coloured ``primaryButton`` background.
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setIcon(phi("check", color="#ffffff"))
        self._apply_btn.setObjectName("primaryButton")
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.clicked.connect(self._on_apply)
        self._apply_btn.setEnabled(False)
        btn_row.addWidget(self._apply_btn)

        close_btn = QPushButton("Close")
        close_btn.setIcon(phi("x"))
        close_btn.setObjectName("outlineButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        self._apply_initial_category(initial_category)
        # Track changes so Apply is enabled only when something differs.
        self._wire_dirty_tracking()

    def _populate_category_tree(self) -> None:
        """Add tree rows pointing at stack page indices.

        Tree layout::

            Appearance
            Tabs
            Scripting
            Private packages          ← landing page (overview + secret backend)
            ├─ npm
            ├─ JSR
            └─ PyPI

        Each item carries a ``UserRole`` int that's the page index in
        ``self._stack``. ``_on_category_changed`` reads that role to switch
        the stack — no string comparison, no fragile order coupling.
        """

        def _leaf(parent: QTreeWidget | QTreeWidgetItem, label: str, idx: int) -> QTreeWidgetItem:
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, idx)
            if isinstance(parent, QTreeWidget):
                parent.addTopLevelItem(item)
            else:
                parent.addChild(item)
            return item

        appearance = _leaf(self._cat_tree, "Appearance", self._page_indices["appearance"])
        _leaf(self._cat_tree, "Tabs", self._page_indices["tabs"])
        _leaf(self._cat_tree, "Scripting", self._page_indices["scripting"])

        private_parent = QTreeWidgetItem(["Private packages"])
        private_parent.setData(0, Qt.ItemDataRole.UserRole, self._page_indices["private_overview"])
        font = private_parent.font(0)
        font.setBold(True)
        private_parent.setFont(0, font)
        self._cat_tree.addTopLevelItem(private_parent)
        _leaf(private_parent, "npm", self._page_indices["private_npm"])
        _leaf(private_parent, "JSR", self._page_indices["private_jsr"])
        _leaf(private_parent, "PyPI", self._page_indices["private_pypi"])
        self._cat_tree.expandItem(private_parent)

        # Default to Appearance.
        self._cat_tree.setCurrentItem(appearance)

    def _apply_initial_category(self, name: str) -> None:
        """Select the tree node matching *name* (case-insensitive)."""
        key = (name or "").strip().casefold()
        matches = {
            "appearance": "Appearance",
            "tabs": "Tabs",
            "scripting": "Scripting",
            "private packages": "Private packages",
            "private": "Private packages",
            "npm": "npm",
            "jsr": "JSR",
            "pypi": "PyPI",
        }
        target = matches.get(key)
        if target is None:
            return
        for top in range(self._cat_tree.topLevelItemCount()):
            top_item = self._cat_tree.topLevelItem(top)
            if top_item is None:
                continue
            if top_item.text(0) == target:
                self._cat_tree.setCurrentItem(top_item)
                return
            for child in range(top_item.childCount()):
                child_item = top_item.child(child)
                if child_item is None:
                    continue
                if child_item.text(0) == target:
                    self._cat_tree.setCurrentItem(child_item)
                    self._cat_tree.expandItem(top_item)
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
        self._page_indices["appearance"] = self._stack.addWidget(page)

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
        self._page_indices["tabs"] = self._stack.addWidget(page)

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

        self._lsp_enabled_check = QCheckBox("Enable language server (LSP) for scripts")
        self._lsp_enabled_check.setChecked(RuntimeSettings.lsp_enabled())
        layout.addWidget(self._lsp_enabled_check)

        self._npm_type_resolution_check = QCheckBox("Resolve npm/jsr types for pm.require (LSP)")
        self._npm_type_resolution_check.setChecked(RuntimeSettings.enable_npm_type_resolution())
        layout.addWidget(self._npm_type_resolution_check)

        self._format_on_save_check = QCheckBox("Format script on save (idle, 500ms)")
        self._format_on_save_check.setChecked(RuntimeSettings.format_on_save())
        layout.addWidget(self._format_on_save_check)

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

        # Private packages used to live inline on this page — it's now its own
        # branch in the category tree (see ``_build_private_packages_pages``).

        self._refresh_deno_status()
        self._refresh_python_status()

        layout.addStretch()
        self._page_indices["scripting"] = self._stack.addWidget(page)

    # -- Private packages pages ----------------------------------------

    _REG_COLS = ("Scope", "Registry URL", "Auth")  # Type column dropped — implied by page.

    def _build_private_packages_pages(self) -> None:
        """Build the four pages under the **Private packages** tree branch.

        Splits what used to be one giant inline section on the Scripting
        page into four focused sub-pages so each provider has room to
        breathe (the original cramming was the audit's prompt for this
        refactor):

        * **Overview** — secret-backend status + per-provider summary stats.
        * **npm** — npm-only scope table + default-npm registry override.
        * **JSR** — JSR-only scope table.
        * **PyPI** — Pyodide PyPI primary/extra URLs + auth.

        All four pages share the same ``self._registries`` master list and
        the same ``self._pypi_*`` fields; UI changes round-trip through
        ``_sync_<kind>_table()`` so a switch between npm and JSR doesn't
        lose unsaved edits.
        """
        self._registries: list[RegistryEntry] = list(RuntimeSettings.get_registries())

        # PyPI state owned at dialog scope (used by Overview + PyPI page).
        pypi_cfg = RuntimeSettings.get_pypi_config()
        # Legacy single-pair PyPI fields are gone (the page is a table now).
        # ``_pypi_indexes`` holds the N-index list; per-row auth lives inline
        # on each entry.

        # Default-npm state (Overview + npm page).
        default_url, default_auth_ref, default_auth_kind = (
            RuntimeSettings.get_default_npm_registry()
        )
        self._default_npm_initial_url = default_url
        self._default_npm_auth_ref = default_auth_ref or "npm:__default__"
        self._default_npm_auth_kind: str = default_auth_kind or "token"

        self._build_private_overview_page()
        self._build_private_provider_page(
            kind="npm",
            page_key="private_npm",
            heading="npm (private scoped registries)",
            intro=(
                'Route <code>pm.require("npm:…")</code> calls through your '
                "own npm-compatible mirror. One row per <code>@scope</code>; "
                "public packages stay on registry.npmjs.org unless you "
                "configure the **Override default npm registry** field below."
            ),
            include_default_override=True,
            pypi_cfg=None,
        )
        self._build_private_provider_page(
            kind="jsr",
            page_key="private_jsr",
            heading="JSR (private scoped registries)",
            intro=(
                "JSR.io does not host private packages — most enterprises "
                "proxy JSR through an npm-compatible upstream (Cloudsmith, "
                "Artifactory). Add the proxy here as a scope row; "
                '<code>pm.require("jsr:@scope/pkg")</code> resolves through '
                "the same <code>.npmrc</code> machinery as npm."
            ),
            include_default_override=False,
            pypi_cfg=None,
        )
        self._build_private_pypi_page(pypi_cfg)

    # ---- Overview --------------------------------------------------------

    def _build_private_overview_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        heading = QLabel("Private package registries")
        heading.setObjectName("titleLabel")
        layout.addWidget(heading)

        intro = QLabel(
            'Route <code>pm.require("npm:…")</code>, '
            '<code>pm.require("jsr:…")</code> and Python <code>pm.require(…)'
            "</code> calls through your own private registries. Pick a provider "
            "from the tree to configure scope mappings, default-registry "
            "overrides, and credentials."
        )
        intro.setObjectName("mutedLabel")
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        backend_label = QLabel()
        backend_label.setObjectName("mutedLabel")
        backend_label.setTextFormat(Qt.TextFormat.RichText)
        self._secret_backend_label = backend_label
        layout.addWidget(backend_label)
        self._refresh_secret_backend_label()

        self._overview_summary_label = QLabel()
        self._overview_summary_label.setObjectName("mutedLabel")
        self._overview_summary_label.setTextFormat(Qt.TextFormat.RichText)
        self._overview_summary_label.setWordWrap(True)
        layout.addWidget(self._overview_summary_label)
        self._refresh_overview_summary()

        layout.addStretch()
        self._page_indices["private_overview"] = self._stack.addWidget(page)

    def _refresh_overview_summary(self) -> None:
        """Recompute the per-provider summary shown on the overview page."""
        if not hasattr(self, "_overview_summary_label"):
            return
        npm_count = sum(1 for e in self._registries if e["kind"] == "npm")
        jsr_count = sum(1 for e in self._registries if e["kind"] == "jsr")
        default_npm = getattr(self, "_default_npm_edit", None)
        default_npm_text = (
            default_npm.text().strip() if default_npm else self._default_npm_initial_url
        )
        pypi_count = len(getattr(self, "_pypi_indexes", []))
        if pypi_count == 0:
            pypi_summary = "using public PyPI"
        elif pypi_count == 1:
            pypi_summary = "1 index (primary)"
        else:
            pypi_summary = f"{pypi_count} indexes (primary + {pypi_count - 1} extra)"
        lines = [
            f"<b>npm</b>: {npm_count} scoped registr{'y' if npm_count == 1 else 'ies'}"
            f"{', default override set' if default_npm_text else ''}.",
            f"<b>JSR</b>: {jsr_count} scoped registr{'y' if jsr_count == 1 else 'ies'}.",
            f"<b>PyPI</b>: {pypi_summary}.",
        ]
        self._overview_summary_label.setText("<br>".join(lines))

    # ---- Per-provider provider page (npm / jsr) --------------------------

    def _build_private_provider_page(
        self,
        *,
        kind: Literal["npm", "jsr"],
        page_key: str,
        heading: str,
        intro: str,
        include_default_override: bool,
        pypi_cfg: Any,
    ) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel(heading)
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        intro_label = QLabel(intro)
        intro_label.setObjectName("mutedLabel")
        intro_label.setTextFormat(Qt.TextFormat.RichText)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        table = self._build_registries_table(kind)
        if kind == "npm":
            self._npm_table = table
        else:
            self._jsr_table = table
        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton(f"Add {kind} registry")
        add_btn.setIcon(phi("plus"))
        add_btn.setObjectName("outlineButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(lambda _ck=False, k=kind: self._on_add_registry_row(k))
        btn_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove selected")
        remove_btn.setIcon(phi("trash"))
        remove_btn.setObjectName("outlineButton")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda _ck=False, k=kind: self._on_remove_registry_row(k))
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        if include_default_override:
            default_label = QLabel("Override default npm registry (optional)")
            default_label.setObjectName("sectionLabel")
            layout.addWidget(default_label)

            default_hint = QLabel(
                "Set this only if you want **every** unscoped "
                '<code>pm.require("npm:…")</code> call to go through your '
                "mirror instead of registry.npmjs.org. Scoped rows above still "
                "win for their specific scopes."
            )
            default_hint.setObjectName("mutedLabel")
            default_hint.setTextFormat(Qt.TextFormat.RichText)
            default_hint.setWordWrap(True)
            layout.addWidget(default_hint)

            default_row = QHBoxLayout()
            default_row.setContentsMargins(0, 0, 0, 0)
            self._default_npm_edit = QLineEdit()
            self._default_npm_edit.setObjectName("settingsDefaultNpmEdit")
            self._default_npm_edit.setPlaceholderText(
                "Leave empty for registry.npmjs.org (default)"
            )
            self._default_npm_edit.setText(self._default_npm_initial_url)
            default_row.addWidget(self._default_npm_edit, 1)
            self._default_npm_auth_btn = QPushButton("Auth…")
            self._default_npm_auth_btn.setObjectName("outlineButton")
            self._default_npm_auth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._default_npm_auth_btn.clicked.connect(self._on_default_npm_auth_clicked)
            default_row.addWidget(self._default_npm_auth_btn)
            layout.addLayout(default_row)

        layout.addStretch()
        self._page_indices[page_key] = self._stack.addWidget(page)

    # ---- PyPI page --------------------------------------------------------

    _PYPI_COLS = ("#", "Index URL", "Auth")

    def _build_private_pypi_page(self, pypi_cfg: PyPIConfig) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel("PyPI (Pyodide runtime)")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        intro = QLabel(
            "Route Python <code>pm.require(…)</code> calls through your own "
            "PyPI mirrors. Add as many index URLs as you need — the top row "
            "is the **primary** (replaces the public PyPI); every row below "
            "is an extra checked when the primary doesn't carry the package. "
            "Each row has its own auth slot so a token-authed corporate "
            "mirror can sit alongside a public fallback. Tokens are stored "
            "separately from this settings file. RestrictedPython subprocess "
            "runtime has no install step — only the Pyodide path uses these."
        )
        intro.setObjectName("mutedLabel")
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._pypi_indexes: list[PyPIIndex] = list(RuntimeSettings.get_pypi_indexes())
        self._pypi_table = self._build_pypi_indexes_table()
        layout.addWidget(self._pypi_table)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton("Add PyPI index")
        add_btn.setIcon(phi("plus"))
        add_btn.setObjectName("outlineButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_pypi_index_row)
        btn_row.addWidget(add_btn)
        remove_btn = QPushButton("Remove selected")
        remove_btn.setIcon(phi("trash"))
        remove_btn.setObjectName("outlineButton")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(self._on_remove_pypi_index_row)
        btn_row.addWidget(remove_btn)
        up_btn = QPushButton("Move up")
        up_btn.setIcon(phi("arrow-up"))
        up_btn.setObjectName("outlineButton")
        up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        up_btn.clicked.connect(lambda _ck=False: self._on_move_pypi_index_row(-1))
        btn_row.addWidget(up_btn)
        down_btn = QPushButton("Move down")
        down_btn.setIcon(phi("arrow-down"))
        down_btn.setObjectName("outlineButton")
        down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        down_btn.clicked.connect(lambda _ck=False: self._on_move_pypi_index_row(1))
        btn_row.addWidget(down_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        pypi_warning = QLabel(
            "⚠ Multiple indexes risk dependency-confusion attacks. Prefer hosting "
            "your private mirror as the primary (top) index whenever possible."
        )
        pypi_warning.setObjectName("mutedLabel")
        pypi_warning.setWordWrap(True)
        layout.addWidget(pypi_warning)

        layout.addStretch()
        self._page_indices["private_pypi"] = self._stack.addWidget(page)

    def _build_pypi_indexes_table(self) -> QTableWidget:
        """Table for the N-index PyPI list (priority order, top = primary)."""
        table = QTableWidget(0, len(self._PYPI_COLS) + 1)  # +1 for hidden ``id``
        table.setObjectName("pypiIndexesTable")
        table.setHorizontalHeaderLabels((*self._PYPI_COLS, "id"))
        table.setColumnHidden(len(self._PYPI_COLS), True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        table.setMinimumHeight(160)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for entry in self._pypi_indexes:
            self._append_pypi_row_widget(table, entry)
        table.cellChanged.connect(self._on_pypi_cell_changed)
        return table

    def _append_pypi_row_widget(self, table: QTableWidget, entry: PyPIIndex) -> None:
        """Append one row reflecting *entry*. ``#`` column is read-only."""
        table.blockSignals(True)
        row = table.rowCount()
        table.insertRow(row)
        # ``#`` column: priority badge (Primary / extra index). Read-only so
        # the user reorders via the Move up/down buttons, not by typing.
        priority_item = QTableWidgetItem(self._pypi_priority_label(row))
        priority_item.setFlags(priority_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row, 0, priority_item)
        table.setItem(row, 1, QTableWidgetItem(entry.get("url", "")))
        auth_btn = QPushButton("Auth…")
        auth_btn.setObjectName("outlineButton")
        auth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row_id = entry.get("id", "")
        auth_btn.clicked.connect(
            lambda _ck=False, rid=row_id: self._on_pypi_auth_clicked_by_id(rid)
        )
        table.setCellWidget(row, 2, auth_btn)
        id_item = QTableWidgetItem(row_id)
        id_item.setFlags(Qt.ItemFlag.NoItemFlags)
        table.setItem(row, len(self._PYPI_COLS), id_item)
        table.blockSignals(False)

    @staticmethod
    def _pypi_priority_label(row: int) -> str:
        return "Primary" if row == 0 else f"Extra {row}"

    def _pypi_entry_by_id(self, row_id: str) -> PyPIIndex | None:
        for entry in self._pypi_indexes:
            if entry["id"] == row_id:
                return entry
        return None

    def _pypi_row_id_at(self, row: int) -> str:
        item = self._pypi_table.item(row, len(self._PYPI_COLS))
        return item.text() if item else ""

    def _sync_pypi_table_into_indexes(self) -> None:
        """Pull URL edits from the table back into ``self._pypi_indexes``."""
        table = self._pypi_table
        for row in range(table.rowCount()):
            row_id = self._pypi_row_id_at(row)
            entry = self._pypi_entry_by_id(row_id)
            if entry is None:
                continue
            url_item = table.item(row, 1)
            if url_item is not None:
                entry["url"] = url_item.text().strip()

    def _refresh_pypi_priority_labels(self) -> None:
        table = self._pypi_table
        table.blockSignals(True)
        try:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None:
                    item.setText(self._pypi_priority_label(row))
        finally:
            table.blockSignals(False)

    def _on_add_pypi_index_row(self) -> None:
        new_entry: PyPIIndex = {
            "id": uuid.uuid4().hex,
            "url": "https://",
            "auth_kind": "none",
            "auth_ref": "",
        }
        self._pypi_indexes.append(new_entry)
        self._append_pypi_row_widget(self._pypi_table, new_entry)
        self._refresh_pypi_priority_labels()
        self._refresh_url_field_validation()
        self._refresh_overview_summary()
        self._mark_dirty()

    def _on_remove_pypi_index_row(self) -> None:
        row = self._pypi_table.currentRow()
        if row < 0:
            return
        row_id = self._pypi_row_id_at(row)
        entry = self._pypi_entry_by_id(row_id)
        if entry is None:
            self._pypi_table.removeRow(row)
            return
        ref = entry.get("auth_ref", "")
        if ref:
            from services.scripting.secret_store import get_default_store

            with contextlib.suppress(Exception):
                get_default_store().delete(ref)
        self._pypi_indexes = [e for e in self._pypi_indexes if e["id"] != row_id]
        self._pypi_table.removeRow(row)
        self._refresh_pypi_priority_labels()
        self._refresh_auth_button_states()
        self._refresh_overview_summary()
        self._mark_dirty()

    def _on_move_pypi_index_row(self, delta: int) -> None:
        """Move the selected row up (delta=-1) or down (delta=+1)."""
        row = self._pypi_table.currentRow()
        new_row = row + delta
        if row < 0 or new_row < 0 or new_row >= len(self._pypi_indexes):
            return
        self._sync_pypi_table_into_indexes()
        self._pypi_indexes[row], self._pypi_indexes[new_row] = (
            self._pypi_indexes[new_row],
            self._pypi_indexes[row],
        )
        # Rebuild the table since per-cell move is fiddly with cellWidgets.
        self._pypi_table.blockSignals(True)
        try:
            self._pypi_table.setRowCount(0)
            for entry in self._pypi_indexes:
                self._append_pypi_row_widget(self._pypi_table, entry)
        finally:
            self._pypi_table.blockSignals(False)
        self._pypi_table.selectRow(new_row)
        self._refresh_pypi_priority_labels()
        self._refresh_auth_button_states()
        self._refresh_overview_summary()
        self._mark_dirty()

    def _on_pypi_cell_changed(self, _row: int, _col: int) -> None:
        self._sync_pypi_table_into_indexes()
        self._refresh_url_field_validation()
        self._refresh_overview_summary()
        self._mark_dirty()

    def _on_pypi_auth_clicked_by_id(self, row_id: str) -> None:
        from ui.dialogs.secret_entry_dialog import SecretEntryDialog

        self._sync_pypi_table_into_indexes()
        entry = self._pypi_entry_by_id(row_id)
        if entry is None:
            return
        ref = entry.get("auth_ref") or f"pypi:{row_id}"
        dlg = SecretEntryDialog(
            ref=ref,
            kind_hint=entry.get("auth_kind", "token"),
            title=f"PyPI authentication ({entry.get('url') or 'row'})",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            kind_raw = dlg.saved_kind() or "none"
            entry["auth_kind"] = cast(
                Literal["token", "basic", "none"],
                kind_raw if kind_raw in ("token", "basic", "none") else "none",
            )
            entry["auth_ref"] = dlg.saved_ref()
            self._refresh_auth_button_states()
            self._mark_dirty()

    # ---- Shared registries-table machinery -------------------------------

    def _build_registries_table(self, kind: Literal["npm", "jsr"]) -> QTableWidget:
        """Build a kind-filtered registries table.

        The Type column is gone (the page itself implies the kind); a hidden
        column carries the entry's ``id`` so per-row operations look the
        right entry up in ``self._registries`` regardless of position.
        """
        table = QTableWidget(0, len(self._REG_COLS) + 1)  # +1 for hidden ``id``
        table.setObjectName(f"registriesTable_{kind}")
        table.setHorizontalHeaderLabels((*self._REG_COLS, "id"))
        table.setColumnHidden(len(self._REG_COLS), True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        table.setMinimumHeight(180)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for entry in self._registries:
            if entry["kind"] != kind:
                continue
            self._append_registry_row_widget(table, entry)
        table.cellChanged.connect(lambda r, c, k=kind: self._on_registry_cell_changed(k, r, c))
        return table

    def _append_registry_row_widget(self, table: QTableWidget, entry: RegistryEntry) -> None:
        """Append one row to *table* reflecting *entry* (no Type combo)."""
        table.blockSignals(True)
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(entry.get("scope", "")))
        table.setItem(row, 1, QTableWidgetItem(entry.get("url", "")))
        auth_btn = QPushButton("Auth…")
        auth_btn.setObjectName("outlineButton")
        auth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row_id = entry.get("id", "")
        auth_btn.clicked.connect(
            lambda _ck=False, rid=row_id: self._on_registry_auth_clicked_by_id(rid)
        )
        table.setCellWidget(row, 2, auth_btn)
        # Hidden ``id`` so per-row operations don't depend on row index.
        id_item = QTableWidgetItem(row_id)
        id_item.setFlags(Qt.ItemFlag.NoItemFlags)
        table.setItem(row, len(self._REG_COLS), id_item)
        table.blockSignals(False)

    def _table_for_kind(self, kind: Literal["npm", "jsr"]) -> QTableWidget:
        return self._npm_table if kind == "npm" else self._jsr_table

    def _entry_by_id(self, row_id: str) -> RegistryEntry | None:
        for entry in self._registries:
            if entry["id"] == row_id:
                return entry
        return None

    def _row_id_at(self, table: QTableWidget, row: int) -> str:
        item = table.item(row, len(self._REG_COLS))
        return item.text() if item else ""

    def _sync_table_into_registries(self, kind: Literal["npm", "jsr"]) -> None:
        """Copy scope/URL cells from the registry table into ``self._registries``.

        Pull scope/URL edits out of the kind's table back into the
        master ``self._registries`` list, identifying entries by stable
        ``id`` so reorderings or row index drift don't lose data.
        """
        table = self._table_for_kind(kind)
        for row in range(table.rowCount()):
            row_id = self._row_id_at(table, row)
            entry = self._entry_by_id(row_id)
            if entry is None:
                continue
            scope_item = table.item(row, 0)
            url_item = table.item(row, 1)
            if scope_item is not None:
                entry["scope"] = scope_item.text().strip()
            if url_item is not None:
                entry["url"] = url_item.text().strip()

    def _on_add_registry_row(self, kind: Literal["npm", "jsr"]) -> None:
        new_entry: RegistryEntry = {
            "id": uuid.uuid4().hex,
            "scope": "@new",
            "url": "https://",
            "kind": kind,
            "auth_kind": "none",
            "auth_ref": "",
        }
        self._registries.append(new_entry)
        self._append_registry_row_widget(self._table_for_kind(kind), new_entry)
        self._refresh_overview_summary()
        self._mark_dirty()

    def _on_remove_registry_row(self, kind: Literal["npm", "jsr"]) -> None:
        table = self._table_for_kind(kind)
        row = table.currentRow()
        if row < 0:
            return
        row_id = self._row_id_at(table, row)
        entry = self._entry_by_id(row_id)
        if entry is None:
            table.removeRow(row)
            return
        # B3: delete the keychain entry so removing a row doesn't leak the secret.
        ref = entry.get("auth_ref", "")
        if ref:
            from services.scripting.secret_store import get_default_store

            with contextlib.suppress(Exception):
                get_default_store().delete(ref)
        self._registries = [e for e in self._registries if e["id"] != row_id]
        table.removeRow(row)
        self._refresh_auth_button_states()
        self._refresh_overview_summary()
        self._mark_dirty()

    def _on_registry_cell_changed(self, kind: Literal["npm", "jsr"], _row: int, _col: int) -> None:
        self._sync_table_into_registries(kind)
        self._refresh_registry_row_validation()
        self._refresh_url_field_validation()
        self._refresh_overview_summary()
        self._mark_dirty()

    @staticmethod
    def _scope_is_valid(scope: str) -> bool:
        """``@`` prefix + at least one non-space character after it."""
        scope = (scope or "").strip()
        return bool(scope) and scope.startswith("@") and len(scope) > 1

    @staticmethod
    def _registry_url_is_valid(url: str) -> bool:
        """Require an explicit ``https://`` scheme + host.

        We deliberately reject ``http://`` because ``.npmrc`` auth lines for
        plain HTTP leak the bearer token over the wire — Cloudsmith /
        Verdaccio / Nexus all default to TLS in production. Loopback is
        rare enough to keep an escape hatch as ``http://localhost`` if
        someone really needs it.
        """
        url = (url or "").strip()
        if not url:
            return False
        if url.startswith("https://") and len(url) > len("https://"):
            return True
        return bool(url.startswith("http://localhost") or url.startswith("http://127."))

    def _refresh_registry_row_validation(self) -> None:
        """Colour invalid Scope / URL cells red + tooltip the rule.

        Saved rows that are empty or malformed are silently dropped at read
        time (``get_registries``) — this method makes that fate visible
        before the user clicks Apply. Runs across both the npm and JSR
        tables.
        """
        bad = QBrush(QColor("#c62828"))
        good = QBrush(QColor("transparent"))
        for table in self._registry_tables():
            table.blockSignals(True)
            try:
                for row in range(table.rowCount()):
                    scope_item = table.item(row, 0)
                    url_item = table.item(row, 1)
                    if scope_item is not None:
                        if self._scope_is_valid(scope_item.text()):
                            scope_item.setForeground(good)
                            scope_item.setToolTip("")
                        else:
                            scope_item.setForeground(bad)
                            scope_item.setToolTip("Scope must start with '@' (e.g. @mycompany).")
                    if url_item is not None:
                        if self._registry_url_is_valid(url_item.text()):
                            url_item.setForeground(good)
                            url_item.setToolTip("")
                        else:
                            url_item.setForeground(bad)
                            url_item.setToolTip(
                                "Registry URL must be https:// (tokens leak over plain "
                                "HTTP). Use http://localhost for local dev only."
                            )
            finally:
                table.blockSignals(False)

    def _registry_tables(self) -> list[QTableWidget]:
        """Return the npm and JSR table widgets (in that order)."""
        out: list[QTableWidget] = []
        npm_t = getattr(self, "_npm_table", None)
        jsr_t = getattr(self, "_jsr_table", None)
        if npm_t is not None:
            out.append(npm_t)
        if jsr_t is not None:
            out.append(jsr_t)
        return out

    def _refresh_url_field_validation(self) -> None:
        """Tooltip-only validation for default-npm URL field.

        Empty is fine (means "use the public default"); non-empty values
        must be HTTPS. We don't block save — settings still persist — but
        the dialog warns the user before they hit Apply. PyPI URLs live in
        the table now and are flagged inline via
        :meth:`_refresh_registry_row_validation`-style cell colouring.
        """
        edits: list[tuple[QLineEdit, str]] = []
        if hasattr(self, "_default_npm_edit"):
            edits.append((self._default_npm_edit, "Default npm registry URL"))
        for edit, label in edits:
            value = edit.text().strip()
            if not value or self._registry_url_is_valid(value):
                edit.setStyleSheet("")
                edit.setToolTip("")
            else:
                edit.setStyleSheet("QLineEdit { border: 1px solid #c62828; }")
                edit.setToolTip(f"{label} must be https:// (or http://localhost for local dev).")

    def _on_registry_auth_clicked_by_id(self, row_id: str) -> None:
        """Auth-button handler keyed by the entry's stable ``id``.

        Avoids any reliance on row index (which is per-table now), and stays
        correct even if the user has just renamed the scope. The keychain
        ref is always ``f"registry:{id}"`` (anchored to the row's UUID),
        so renaming a scope cannot orphan the stored secret.
        """
        from ui.dialogs.secret_entry_dialog import SecretEntryDialog

        # Pull in any pending scope/URL edits before opening the modal so
        # the dialog title reflects the user's typed scope.
        for kind in ("npm", "jsr"):
            self._sync_table_into_registries(cast(Literal["npm", "jsr"], kind))
        entry = self._entry_by_id(row_id)
        if entry is None:
            return
        scope = entry.get("scope") or f"row {row_id[:6]}"
        ref = entry.get("auth_ref") or f"registry:{row_id}"
        dlg = SecretEntryDialog(
            ref=ref,
            kind_hint=entry.get("auth_kind", "token"),
            title=f"Authentication for {scope}",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            kind_raw = dlg.saved_kind() or "none"
            entry["auth_kind"] = cast(
                Literal["token", "basic", "none"],
                kind_raw if kind_raw in ("token", "basic", "none") else "none",
            )
            entry["auth_ref"] = dlg.saved_ref()
            self._refresh_auth_button_states()
            self._mark_dirty()

    def _on_default_npm_auth_clicked(self) -> None:
        from ui.dialogs.secret_entry_dialog import SecretEntryDialog

        dlg = SecretEntryDialog(
            ref=self._default_npm_auth_ref,
            kind_hint=self._default_npm_auth_kind or "token",
            title="Default npm registry authentication",
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._default_npm_auth_ref = dlg.saved_ref()
            self._default_npm_auth_kind = dlg.saved_kind() or "none"
            self._refresh_auth_button_states()
            self._mark_dirty()

    def _refresh_auth_button_states(self) -> None:
        """Mark every ``Auth…`` button to reflect whether a secret is stored.

        Sets the button text to ``Auth ✓`` when ``auth_kind != "none"`` and a
        non-empty ``auth_ref`` is recorded; otherwise resets to ``Auth…``.
        Tooltip mirrors the auth kind so the user can tell Token vs Basic
        without re-opening the modal.
        """
        for table in self._registry_tables():
            for row in range(table.rowCount()):
                btn = table.cellWidget(row, 2)  # Auth column index after Type dropped
                if not isinstance(btn, QPushButton):
                    continue
                row_id = self._row_id_at(table, row)
                reg_entry = self._entry_by_id(row_id)
                self._style_auth_button(
                    btn,
                    kind=reg_entry.get("auth_kind", "none") if reg_entry else "none",
                    has_ref=bool(reg_entry and reg_entry.get("auth_ref")),
                )
        # Default-npm auth button.
        if hasattr(self, "_default_npm_auth_btn"):
            self._style_auth_button(
                self._default_npm_auth_btn,
                kind=self._default_npm_auth_kind,
                has_ref=bool(
                    self._default_npm_edit.text().strip()
                    and self._default_npm_auth_ref
                    and self._default_npm_auth_kind != "none"
                ),
            )
        # PyPI per-row auth buttons (table is N-index; each row owns its auth).
        pypi_table = getattr(self, "_pypi_table", None)
        if pypi_table is not None:
            for row in range(pypi_table.rowCount()):
                btn = pypi_table.cellWidget(row, 2)
                if not isinstance(btn, QPushButton):
                    continue
                row_id = self._pypi_row_id_at(row)
                pypi_entry = self._pypi_entry_by_id(row_id)
                self._style_auth_button(
                    btn,
                    kind=pypi_entry.get("auth_kind", "none") if pypi_entry else "none",
                    has_ref=bool(pypi_entry and pypi_entry.get("auth_ref")),
                )

    @staticmethod
    def _style_auth_button(btn: QPushButton, *, kind: str, has_ref: bool) -> None:
        if has_ref and kind in ("token", "basic"):
            label = "token" if kind == "token" else "basic"
            btn.setText("Auth ✓")
            btn.setToolTip(f"Auth configured ({label}). Click to change or clear.")
        else:
            btn.setText("Auth…")
            btn.setToolTip("No auth configured. Click to set token or basic credentials.")

    def _partition_valid_registries(
        self, entries: list[RegistryEntry]
    ) -> tuple[list[RegistryEntry], list[RegistryEntry]]:
        """Split *entries* into kept vs dropped using the same rules as the UI.

        Split *entries* into ``(kept, dropped)`` by the same validation
        the inline UI cues use (scope must start with ``@``, URL must be
        https or loopback).
        """
        kept: list[RegistryEntry] = []
        dropped: list[RegistryEntry] = []
        for entry in entries:
            scope = entry.get("scope", "")
            url = entry.get("url", "")
            if self._scope_is_valid(scope) and self._registry_url_is_valid(url):
                kept.append(entry)
            else:
                dropped.append(entry)
        return kept, dropped

    def _reload_registries_table(self) -> None:
        """Rebuild both per-kind tables from ``self._registries`` (used after Apply).

        Each table only renders entries matching its kind; clearing both
        first guarantees rows dropped on Apply visibly disappear.
        """
        for table_kind in ("npm", "jsr"):
            kind = cast(Literal["npm", "jsr"], table_kind)
            table = self._table_for_kind(kind)
            table.blockSignals(True)
            try:
                table.setRowCount(0)
                for entry in self._registries:
                    if entry["kind"] == kind:
                        self._append_registry_row_widget(table, entry)
            finally:
                table.blockSignals(False)
        self._refresh_registry_row_validation()
        self._refresh_auth_button_states()

    def _announce_dropped_registries(self, count: int) -> None:
        """Show a short warning on the secret-backend label.

        Surfaces a transient message so the user notices when half-typed rows
        are stripped on Apply. Uses a short label flash instead of a
        QMessageBox that would steal focus.
        """
        if count <= 0 or not hasattr(self, "_secret_backend_label"):
            return
        msg = f"⚠ {count} invalid registry row(s) were dropped on save."
        self._secret_backend_label.setText(msg)
        # Restore the normal backend status after a short delay so the
        # warning doesn't stick around forever. Bind the timer to the
        # dialog (``self`` as receiver) so a dialog closed before 5s
        # elapses doesn't crash on a dead-method callback.
        QTimer.singleShot(5000, self, self._refresh_secret_backend_label)

    def _refresh_secret_backend_label(self) -> None:
        status = backend_status()
        if status["tone"] == "ok":
            colour = "#2e7d32"
            prefix = "✓"
        elif status["tone"] == "warn":
            colour = "#b26a00"
            prefix = "⚠"
        else:
            colour = "#c62828"
            prefix = "✕"
        self._secret_backend_label.setText(
            f"Secrets stored in: <span style='color:{colour};'>{prefix} {status['label']}</span>"
        )

    # -- Slots ---------------------------------------------------------

    def _on_category_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None = None,
    ) -> None:
        """Switch the detail stack to the page indexed by the tree item.

        Each tree item's ``UserRole`` holds the stack page index — see
        :meth:`_populate_category_tree`. ``None`` happens when the tree is
        cleared programmatically; ignore it.
        """
        if current is None:
            return
        idx = current.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(idx, int) and 0 <= idx < self._stack.count():
            self._stack.setCurrentIndex(idx)

    def _wire_dirty_tracking(self) -> None:
        """Mark the dialog dirty (Apply enabled) when any input value changes.

        Hooked AFTER all page builders have populated their widgets, so the
        initial ``setCurrentIndex`` / ``setChecked`` / ``setValue`` calls in
        ``_build_*_page`` do not flag the dialog as dirty before the user
        has touched anything.
        """
        # Combo boxes
        for combo in (
            self._style_combo,
            self._scheme_combo,
            self._wrap_mode_combo,
            self._tab_limit_policy_combo,
            self._activate_on_close_combo,
        ):
            combo.currentIndexChanged.connect(self._mark_dirty)
        # Checkboxes
        for check in (
            self._small_labels_check,
            self._show_path_duplicates_check,
            self._mark_modified_check,
            self._show_full_path_hover_check,
            self._open_new_tabs_at_end_check,
            self._preview_tab_check,
            self._enable_scripts_check,
            self._lsp_enabled_check,
            self._npm_type_resolution_check,
            self._format_on_save_check,
            self._auto_save_default_check,
        ):
            check.toggled.connect(self._mark_dirty)
        # Spin + line edits
        self._tab_limit_spin.valueChanged.connect(self._mark_dirty)
        self._deno_path_edit.textChanged.connect(self._mark_dirty)
        self._python_path_edit.textChanged.connect(self._mark_dirty)
        # Private packages: default-npm URL drives validation styling.
        # PyPI URLs live in a table now — its ``cellChanged`` signal
        # already routes through ``_on_pypi_cell_changed`` which calls
        # both ``_mark_dirty`` and ``_refresh_url_field_validation``.
        # The npm/JSR row buttons fire ``_mark_dirty`` from their own
        # handlers.
        self._default_npm_edit.textChanged.connect(self._mark_dirty)
        self._default_npm_edit.textChanged.connect(self._refresh_url_field_validation)
        # Seed validation cues for any pre-populated rows / fields.
        self._refresh_registry_row_validation()
        self._refresh_url_field_validation()
        self._refresh_auth_button_states()
        # Clearing the default-npm URL clears its "Auth ✓" badge too.
        self._default_npm_edit.textChanged.connect(self._refresh_auth_button_states)

    def _mark_dirty(self, *_args: Any) -> None:
        """Enable Apply on the first user-driven change."""
        if not self._apply_btn.isEnabled():
            self._apply_btn.setEnabled(True)

    def _on_apply(self) -> None:
        """Persist settings and apply the theme.

        Visual feedback: Apply switches to ``"Applying…"`` with a wait
        cursor while the (sometimes-slow) global QSS re-application runs,
        then re-enables only if the user makes further changes.
        """
        from PySide6.QtGui import QCursor

        self._apply_btn.setEnabled(False)
        original_text = self._apply_btn.text()
        self._apply_btn.setText("Applying…")
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        # Flush the UI update before the synchronous reflow kicks in, so the
        # cursor + button text are actually visible during the freeze.
        QApplication.processEvents()
        try:
            self._do_apply()
        finally:
            QApplication.restoreOverrideCursor()
            self._apply_btn.setText(original_text)
            # Stay disabled: nothing left to apply until the user changes
            # another field (which re-enables via :meth:`_mark_dirty`).

    def _do_apply(self) -> None:
        """Synchronous body of Apply — extracted so feedback wraps it cleanly.

        Skips the global ``ThemeManager.apply()`` reflow when neither the
        widget style nor the colour scheme actually changed. ``apply()``
        re-applies the QSS across every widget, which clobbers per-widget
        font/style overrides — most visibly, the request tab bar's
        ``small_labels`` font. When the theme really does change, force a
        ``settings_changed`` emit on the tab settings so the tab bar
        re-applies its own font/spacing after the global reflow.
        """
        style_data = self._style_combo.currentData()
        scheme_data = self._scheme_combo.currentData()
        new_style = style_data if isinstance(style_data, str) else STYLE_FUSION
        new_scheme = scheme_data if isinstance(scheme_data, str) else SCHEME_AUTO

        theme_changed = False
        if self._tm is not None and (self._tm.style != new_style or self._tm.scheme != new_scheme):
            self._tm.style = new_style
            self._tm.scheme = new_scheme
            self._tm.apply()
            theme_changed = True

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

        # ``ThemeManager.apply()`` reloads the global QSS and resets per-widget
        # font/style overrides that the request tab bar applies (``small_labels``
        # in particular). Re-emit ``settings_changed`` so the tab bar re-runs
        # its ``_apply_settings`` pass on top of the fresh stylesheet.
        if theme_changed:
            self._tab_settings.settings_changed.emit()

        # Scripting
        from ui.styling.theme_manager import _APP, _ORG

        settings = QSettings(_ORG, _APP)
        settings.setValue("scripting/enabled", self._enable_scripts_check.isChecked())
        RuntimeSettings.set_lsp_enabled(self._lsp_enabled_check.isChecked())
        RuntimeSettings.set_enable_npm_type_resolution(self._npm_type_resolution_check.isChecked())
        RuntimeSettings.set_format_on_save(self._format_on_save_check.isChecked())
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

        # Private packages: persist registry list, default-npm, PyPI.
        # B6 fix: drop invalid rows (empty scope/URL or non-https URL)
        # explicitly on Apply rather than letting ``get_registries()``
        # silently filter them at read time — the latter looked like data
        # loss because the row vanished on next open. Tokens for dropped
        # rows are deleted from the secret store so the keychain stays
        # tidy. Pull pending edits from both per-kind tables before the
        # validity check; otherwise an in-flight scope rename would be lost.
        for table_kind in ("npm", "jsr"):
            self._sync_table_into_registries(cast(Literal["npm", "jsr"], table_kind))
        kept, dropped = self._partition_valid_registries(self._registries)
        if dropped:
            from services.scripting.secret_store import get_default_store

            store = get_default_store()
            for reg_entry in dropped:
                ref = reg_entry.get("auth_ref", "")
                if ref:
                    with contextlib.suppress(Exception):
                        store.delete(ref)
            self._announce_dropped_registries(len(dropped))
            # Rebuild the table from the cleaned list so the UI matches
            # what got persisted (otherwise reopening would still show the
            # dropped row pre-strip on the next open).
            self._registries = list(kept)
            self._reload_registries_table()
        RuntimeSettings.set_registries(self._registries)
        _default_npm_text = self._default_npm_edit.text().strip()
        RuntimeSettings.set_default_npm_registry(
            _default_npm_text,
            self._default_npm_auth_ref if _default_npm_text else "",
            self._default_npm_auth_kind if _default_npm_text else "",
        )
        # PyPI: pull pending URL edits, drop empty rows, persist the list.
        # Empty-row dropouts also nuke their stored secrets so the keychain
        # stays in sync with what got saved.
        self._sync_pypi_table_into_indexes()
        kept_pypi: list[PyPIIndex] = []
        dropped_pypi: list[PyPIIndex] = []
        for pypi_row in self._pypi_indexes:
            url = pypi_row.get("url", "").strip()
            if url and url not in ("https://", "http://"):
                kept_pypi.append(pypi_row)
            else:
                dropped_pypi.append(pypi_row)
        if dropped_pypi:
            from services.scripting.secret_store import get_default_store

            store = get_default_store()
            for drop_row in dropped_pypi:
                ref = drop_row.get("auth_ref", "")
                if ref:
                    with contextlib.suppress(Exception):
                        store.delete(ref)
            self._pypi_indexes = list(kept_pypi)
            # Rebuild the table so the user sees the drop instead of finding
            # rows missing on next open.
            self._pypi_table.blockSignals(True)
            try:
                self._pypi_table.setRowCount(0)
                for idx_row in self._pypi_indexes:
                    self._append_pypi_row_widget(self._pypi_table, idx_row)
            finally:
                self._pypi_table.blockSignals(False)
            self._refresh_pypi_priority_labels()
        RuntimeSettings.set_pypi_indexes(self._pypi_indexes)

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
