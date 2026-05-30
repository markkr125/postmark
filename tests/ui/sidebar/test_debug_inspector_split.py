"""Layout tests for :class:`DebugInspectorSplit`."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QSplitter

from ui.sidebar.debug_inspector_split import DebugInspectorSplit


class TestDebugInspectorSplitLayout:
    """Call stack left; watch strip + unified variables tree on the right."""

    def test_splitter_and_trees(self, qapp: QApplication, qtbot) -> None:
        inspector = DebugInspectorSplit()
        qtbot.addWidget(inspector)
        h_split = inspector.findChild(QSplitter, "debugInspectorSplitter")
        assert h_split is not None
        assert inspector.findChild(QSplitter, "debugInspectorRightSplitter") is None
        assert inspector.watches_tree.objectName() == "debugScopesTree"
        assert inspector.scopes_tree is inspector.watches_tree
        assert inspector.watches._watch_add_edit.objectName() == "debugWatchAddEdit"
        assert h_split.count() == 2
