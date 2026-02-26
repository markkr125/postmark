"""Smoke tests for the ImportDialog widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QTabWidget

from ui.import_dialog import ImportDialog


class TestImportDialog:
    """Tests for the import dialog lifecycle and structure."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """ImportDialog can be instantiated without errors."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Import"

    def test_has_tabs(self, qapp: QApplication, qtbot) -> None:
        """ImportDialog contains a QTabWidget with two tabs."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)

        tab_widget = dialog.findChild(QTabWidget)
        assert tab_widget is not None
        assert tab_widget.count() == 2
        assert tab_widget.tabText(0) == "Postmark Import"
        assert tab_widget.tabText(1) == "Other Sources"

    def test_has_paste_input(self, qapp: QApplication, qtbot) -> None:
        """The dialog has a paste input field."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        assert dialog._paste_input is not None
        assert dialog._paste_input.placeholderText() == "Paste cURL, Raw text or URL..."

    def test_has_dismiss_button(self, qapp: QApplication, qtbot) -> None:
        """The dialog has a dismiss button."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        assert dialog._dismiss_btn is not None
        assert dialog._dismiss_btn.text() == "Dismiss"

    def test_import_completed_signal_exists(self, qapp: QApplication, qtbot) -> None:
        """The dialog declares an import_completed signal."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        # Signal should be connectable
        signal_calls: list[bool] = []
        dialog.import_completed.connect(lambda: signal_calls.append(True))
        # Not emitted yet
        assert not signal_calls

    def test_minimum_size(self, qapp: QApplication, qtbot) -> None:
        """The dialog has a reasonable minimum size."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        assert dialog.minimumWidth() >= 600
        assert dialog.minimumHeight() >= 500

    def test_has_drop_zone(self, qapp: QApplication, qtbot) -> None:
        """The import tab contains a drop zone widget."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        assert dialog._drop_zone is not None
        assert dialog._drop_zone.acceptDrops()

    def test_has_progress_bar(self, qapp: QApplication, qtbot) -> None:
        """The dialog contains a progress bar."""
        dialog = ImportDialog()
        qtbot.addWidget(dialog)
        assert dialog._progress_bar is not None
