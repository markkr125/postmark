"""Tests for draft request tab lifecycle (open, save, upgrade)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.main_window import MainWindow


class TestOpenDraftRequest:
    """Tests for ``_open_draft_request`` — creating an unsaved tab."""

    def test_draft_tab_created(self, qapp: QApplication, qtbot) -> None:
        """Opening a draft creates a new tab in the tab bar."""
        window = MainWindow()
        qtbot.addWidget(window)

        assert window._tab_bar.count() == 0
        window._open_draft_request()
        assert window._tab_bar.count() == 1

    def test_draft_tab_name(self, qapp: QApplication, qtbot) -> None:
        """Draft tab is labelled 'Untitled Request'."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        assert window._tab_bar.tabToolTip(0) == "Untitled Request"

    def test_draft_tab_has_no_request_id(self, qapp: QApplication, qtbot) -> None:
        """Draft tab context has ``request_id=None``."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.request_id is None

    def test_draft_editor_is_dirty(self, qapp: QApplication, qtbot) -> None:
        """Draft editor starts dirty so the Save button is enabled."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.editor is not None
        assert ctx.editor.is_dirty

    def test_draft_save_btn_enabled(self, qapp: QApplication, qtbot) -> None:
        """Save button is enabled after opening a draft tab."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        assert window._save_btn.isEnabled()

    def test_multiple_drafts(self, qapp: QApplication, qtbot) -> None:
        """Multiple draft tabs can be opened."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        window._open_draft_request()
        assert window._tab_bar.count() == 2

    def test_draft_editor_empty_url(self, qapp: QApplication, qtbot) -> None:
        """Draft editor has an empty URL field."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.editor is not None
        assert ctx.editor._url_input.text() == ""

    def test_draft_editor_get_method(self, qapp: QApplication, qtbot) -> None:
        """Draft editor defaults to GET method."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.editor is not None
        assert ctx.editor._method_combo.currentText() == "GET"

    def test_draft_breadcrumb_shows_untitled(self, qapp: QApplication, qtbot) -> None:
        """Opening a draft shows 'Untitled Request' in the breadcrumb bar."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        seg = window._breadcrumb_bar.last_segment_info
        assert seg is not None
        assert seg["name"] == "Untitled Request"

    def test_draft_context_has_draft_name(self, qapp: QApplication, qtbot) -> None:
        """Draft tab context stores the draft_name."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.draft_name == "Untitled Request"

    def test_draft_breadcrumb_rename_updates_tab(self, qapp: QApplication, qtbot) -> None:
        """Renaming via breadcrumb updates the tab label and context."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]

        # Simulate breadcrumb rename
        window._on_breadcrumb_rename("My Custom Request")

        assert ctx.draft_name == "My Custom Request"
        assert window._tab_bar.tabToolTip(0) == "My Custom Request"


class TestSaveDraftRequest:
    """Tests for ``_save_draft_request`` — persisting a draft to a collection."""

    def test_save_draft_creates_request_in_db(self, qapp: QApplication, qtbot) -> None:
        """Saving a draft creates a new request in the database."""
        coll = CollectionService.create_collection("TestColl")
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.editor is not None
        ctx.editor._url_input.setText("http://draft.test")
        ctx.editor._method_combo.setCurrentText("POST")

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = mock_dialog.DialogCode.Accepted
        mock_dialog.request_name.return_value = "My Draft"
        mock_dialog.selected_collection_id.return_value = coll.id

        with patch(
            "ui.dialogs.save_request_dialog.SaveRequestDialog",
            return_value=mock_dialog,
        ):
            window._on_save_request()

        # Tab should now have a real request_id
        assert ctx.request_id is not None

        # Verify in DB
        saved = CollectionService.get_request(ctx.request_id)
        assert saved is not None
        assert saved.url == "http://draft.test"
        assert saved.method == "POST"

    def test_save_draft_clears_dirty(self, qapp: QApplication, qtbot) -> None:
        """After saving a draft, the editor is no longer dirty."""
        coll = CollectionService.create_collection("TestColl")
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]
        assert ctx.editor is not None
        assert ctx.editor.is_dirty

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = mock_dialog.DialogCode.Accepted
        mock_dialog.request_name.return_value = "Saved"
        mock_dialog.selected_collection_id.return_value = coll.id

        with patch(
            "ui.dialogs.save_request_dialog.SaveRequestDialog",
            return_value=mock_dialog,
        ):
            window._on_save_request()

        assert not ctx.editor.is_dirty

    def test_save_draft_cancelled_keeps_draft(self, qapp: QApplication, qtbot) -> None:
        """Cancelling the save dialog keeps the tab as a draft."""
        window = MainWindow()
        qtbot.addWidget(window)

        window._open_draft_request()
        ctx = window._tabs[0]

        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = mock_dialog.DialogCode.Rejected

        with patch(
            "ui.dialogs.save_request_dialog.SaveRequestDialog",
            return_value=mock_dialog,
        ):
            window._on_save_request()

        assert ctx.request_id is None

    def test_save_noop_without_tab(self, qapp: QApplication, qtbot) -> None:
        """Save does nothing when no tab is open and editor has no request_id."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget._url_input.setText("http://whatever")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_not_called()
