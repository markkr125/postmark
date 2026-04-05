"""Tests for the CodeEditorWidget minimap feature."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor import CodeEditorWidget


class TestMinimapVisibility:
    """Tests for minimap show/hide toggling."""

    def test_minimap_hidden_by_default(self, qapp: QApplication, qtbot) -> None:
        """The minimap is hidden by default."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        assert editor._minimap.isHidden()

    def test_set_minimap_visible_shows(self, qapp: QApplication, qtbot) -> None:
        """Calling set_minimap_visible(True) shows the minimap."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_minimap_visible(True)
        assert not editor._minimap.isHidden()

    def test_set_minimap_visible_hides(self, qapp: QApplication, qtbot) -> None:
        """Calling set_minimap_visible(False) hides the minimap."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_minimap_visible(True)
        editor.set_minimap_visible(False)
        assert editor._minimap.isHidden()

    def test_minimap_width(self, qapp: QApplication, qtbot) -> None:
        """The minimap has the expected fixed width."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        assert editor._minimap.width() == 60


class TestMinimapInteraction:
    """Tests for minimap paint and scroll interaction."""

    def test_minimap_paint_empty_document(self, qapp: QApplication, qtbot) -> None:
        """Painting the minimap on an empty document does not error."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.set_minimap_visible(True)
        editor.show()
        editor._minimap.repaint()

    def test_minimap_paint_with_content(self, qapp: QApplication, qtbot) -> None:
        """Painting the minimap with content does not error."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("\n".join(f"line {i}" for i in range(100)))
        editor.set_minimap_visible(True)
        editor.show()
        editor._minimap.repaint()

    def test_minimap_scroll_to(self, qapp: QApplication, qtbot) -> None:
        """The minimap _scroll_to method adjusts the scrollbar."""
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        editor.setPlainText("\n".join(f"line {i}" for i in range(200)))
        editor.set_minimap_visible(True)
        editor.show()
        editor.resize(400, 200)
        # Scroll to bottom half via minimap
        editor._minimap._scroll_to(editor._minimap.height())
        assert editor.verticalScrollBar().value() > 0
