"""Settings dialog — user preferences for appearance and behaviour.

Provides a category-list + detail-panel layout.  Currently only the
**Appearance** category exists (style and colour scheme), but the
layout is designed for future extensibility.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
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


class SettingsDialog(QDialog):
    """Modal settings dialog with category list and detail panels."""

    def __init__(
        self,
        theme_manager: ThemeManager | None,
        tab_settings_manager: TabSettingsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the settings dialog."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 340)
        self.resize(560, 380)
        self.setModal(True)

        self._tm = theme_manager
        self._tab_settings = tab_settings_manager or TabSettingsManager(self)

        root = QVBoxLayout(self)

        # -- Splitter: category list | detail stack --------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Category list
        self._cat_list = QListWidget()
        self._cat_list.addItem("Appearance")
        self._cat_list.addItem("Tabs")
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
