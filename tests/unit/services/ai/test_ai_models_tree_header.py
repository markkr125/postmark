"""AI models tree column width persistence."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QHeaderView, QTreeWidget

from ui.dialogs.settings.ai_page_actions import (
    _ENABLED_COLUMN_WIDTH,
    _HEADER_SETTINGS_KEY,
    configure_ai_models_tree_header,
    save_ai_models_tree_header,
)
from ui.styling.theme_manager import _APP, _ORG


def test_header_state_roundtrip(qapp: QApplication) -> None:
    """Saved header state restores column widths on a new tree."""
    settings = QSettings(_ORG, _APP)
    settings.remove(_HEADER_SETTINGS_KEY)

    tree_a = QTreeWidget()
    tree_a.setColumnCount(6)
    tree_a.setHeaderLabels(["", "Name", "Model", "Context", "Cost", "Capabilities"])
    configure_ai_models_tree_header(tree_a)
    header_a = tree_a.header()
    header_a.resizeSection(2, 400)
    save_ai_models_tree_header(header_a)

    tree_b = QTreeWidget()
    tree_b.setColumnCount(6)
    tree_b.setHeaderLabels(["", "Name", "Model", "Context", "Cost", "Capabilities"])
    configure_ai_models_tree_header(tree_b)
    assert tree_b.header().sectionSize(2) == 400

    settings.remove(_HEADER_SETTINGS_KEY)


def test_enabled_column_stays_narrow(qapp: QApplication) -> None:
    """Enable column has no header label and stays a fixed narrow width."""
    settings = QSettings(_ORG, _APP)
    settings.remove(_HEADER_SETTINGS_KEY)

    tree = QTreeWidget()
    tree.setColumnCount(6)
    tree.setHeaderLabels(["", "Name", "Model", "Context", "Cost", "Capabilities"])
    configure_ai_models_tree_header(tree)
    header = tree.header()
    assert tree.headerItem().text(0) == ""
    assert header.sectionSize(0) == _ENABLED_COLUMN_WIDTH
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed

    settings.remove(_HEADER_SETTINGS_KEY)


def test_header_data_columns_are_independently_resizable(qapp: QApplication) -> None:
    """Resizing a data column must not be absorbed by a stretched Name column."""
    settings = QSettings(_ORG, _APP)
    settings.remove(_HEADER_SETTINGS_KEY)

    tree = QTreeWidget()
    tree.setColumnCount(6)
    tree.setHeaderLabels(["", "Name", "Model", "Context", "Cost", "Capabilities"])
    configure_ai_models_tree_header(tree)
    header = tree.header()

    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
    for col in range(1, 5):
        assert header.sectionResizeMode(col) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(5) == QHeaderView.ResizeMode.Stretch

    settings.remove(_HEADER_SETTINGS_KEY)
