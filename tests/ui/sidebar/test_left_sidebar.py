"""Tests for :class:`ui.sidebar.left_sidebar.LeftSidebar`."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSplitter, QStackedWidget, QToolButton, QWidget

from ui.sidebar.left_sidebar import LeftSidebar


def test_close_panel_matches_programmatic_zero_width(
    qapp: QApplication,
    qtbot,
) -> None:
    """Collapse via ``close_panel`` matches splitter sizes dragged to zero width."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    filler = QWidget()
    filler.setMinimumWidth(320)
    filler.setMinimumHeight(120)

    rail = LeftSidebar()
    inner = QWidget()
    rail.set_content(inner)
    rail.install_in_splitter(splitter)
    splitter.addWidget(filler)
    splitter.resize(900, 400)
    qtbot.addWidget(splitter)
    splitter.setSizes([50, 300, 550])
    splitter.show()
    qapp.processEvents()

    rail.open_panel("collections")
    qapp.processEvents()
    assert rail.is_open
    assert rail.flyout_width > 0

    flyout_idx = 1
    sizes = list(splitter.sizes())
    freed = sizes[flyout_idx]
    sizes[2] += freed
    sizes[flyout_idx] = 0
    splitter.setSizes(sizes)
    qapp.processEvents()

    assert not rail.is_open
    assert rail.flyout_width == 0
    flyout_w = splitter.findChild(QWidget, "leftSidebarFlyout")
    assert flyout_w is not None
    assert "border: none" in flyout_w.styleSheet().lower()

    rail.open_panel("collections")
    qapp.processEvents()
    assert rail.is_open
    rail.close_panel()
    qapp.processEvents()
    assert not rail.is_open
    assert rail.flyout_width == 0


def test_rail_flyout_splitter_handle_has_zero_width(qapp: QApplication, qtbot) -> None:
    """The QSplitter seam between the rail and flyout must not use the default wide handle."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    filler = QWidget()
    rail = LeftSidebar()
    rail.set_content(QWidget())
    rail.install_in_splitter(splitter)
    splitter.addWidget(filler)
    splitter.resize(600, 200)
    qtbot.addWidget(splitter)
    splitter.show()
    qapp.processEvents()

    h = splitter.handle(1)
    assert h is not None
    assert h.width() == 0


def test_rail_toggle_collapses_like_close_panel(qapp: QApplication, qtbot) -> None:
    """Re-clicking the active rail icon collapses the flyout to zero width."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    filler = QWidget()
    filler.setMinimumWidth(320)
    rail = LeftSidebar()
    rail.set_content(QWidget())
    rail.install_in_splitter(splitter)
    splitter.addWidget(filler)
    splitter.resize(900, 400)
    qtbot.addWidget(splitter)
    splitter.setSizes([50, 300, 550])
    splitter.show()
    qapp.processEvents()

    rail.open_panel("collections")
    qapp.processEvents()
    assert rail.is_open

    btn = next(
        b
        for b in rail.findChildren(QToolButton)
        if b.objectName() == "leftSidebarRailButton" and b.property("rail_icon_name") == "files"
    )
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert not rail.is_open
    assert rail.flyout_width == 0
    assert rail.isVisible()


def test_local_scripts_rail_switches_flyout_stack(qapp: QApplication, qtbot) -> None:
    """The **code** rail icon swaps the flyout ``QStackedWidget`` to the scripts page."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    filler = QWidget()
    filler.setMinimumWidth(320)
    rail = LeftSidebar()
    coll = QWidget()
    coll.setObjectName("testCollPage")
    scripts = QWidget()
    scripts.setObjectName("testScriptsPage")
    rail.set_content(coll)
    rail.set_local_scripts_panel(scripts)
    rail.install_in_splitter(splitter)
    splitter.addWidget(filler)
    splitter.resize(900, 400)
    qtbot.addWidget(splitter)
    splitter.show()
    qapp.processEvents()

    flyout = splitter.findChild(QWidget, "leftSidebarFlyout")
    assert flyout is not None
    stack = flyout.findChild(QStackedWidget)
    assert stack is not None

    rail.open_panel("collections")
    qapp.processEvents()
    assert stack.currentWidget() is coll

    scripts_btn = next(
        b
        for b in rail.findChildren(QToolButton)
        if b.objectName() == "leftSidebarRailButton" and b.property("rail_icon_name") == "code"
    )
    qtbot.mouseClick(scripts_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert stack.currentWidget() is scripts

    coll_btn = next(
        b
        for b in rail.findChildren(QToolButton)
        if b.objectName() == "leftSidebarRailButton" and b.property("rail_icon_name") == "files"
    )
    qtbot.mouseClick(coll_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert stack.currentWidget() is coll
