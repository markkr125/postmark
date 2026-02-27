"""Settings dialog — user preferences for appearance and behaviour.

Provides a category-list + detail-panel layout.  Currently only the
**Appearance** category exists (style and colour scheme), but the
layout is designed for future extensibility.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.theme_manager import (
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
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the settings dialog."""
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 340)
        self.resize(560, 380)
        self.setModal(True)

        self._tm = theme_manager

        root = QVBoxLayout(self)

        # -- Splitter: category list | detail stack --------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Category list
        self._cat_list = QListWidget()
        self._cat_list.addItem("Appearance")
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

        # -- Button row ------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("primaryButton")
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("outlineButton")
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
        idx = list(STYLES).index(self._tm.style) if self._tm.style in STYLES else 0
        self._style_combo.setCurrentIndex(idx)
        layout.addWidget(self._style_combo)

        # Colour scheme selector
        scheme_label = QLabel("Colour Scheme")
        scheme_label.setObjectName("sectionLabel")
        layout.addWidget(scheme_label)

        self._scheme_combo = QComboBox()
        scheme_labels = {SCHEME_AUTO: "Auto-detect", SCHEME_LIGHT: "Light", SCHEME_DARK: "Dark"}
        for s in SCHEMES:
            self._scheme_combo.addItem(scheme_labels.get(s, s), userData=s)
        idx = list(SCHEMES).index(self._tm.scheme) if self._tm.scheme in SCHEMES else 0
        self._scheme_combo.setCurrentIndex(idx)
        layout.addWidget(self._scheme_combo)

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

        self._tm.style = style_data if isinstance(style_data, str) else STYLE_FUSION
        self._tm.scheme = scheme_data if isinstance(scheme_data, str) else SCHEME_AUTO
        self._tm.apply()
