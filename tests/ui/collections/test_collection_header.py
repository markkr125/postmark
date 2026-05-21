"""Tests for the CollectionHeader widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from ui.collections.collection_header import CollectionHeader
from ui.collections.new_item_popup import NewItemPopup
from ui.collections.new_local_script_popup import NewLocalScriptItemPopup
from ui.widgets.sidebar_section_info import (
    COLLECTIONS_INTRO,
    LOCAL_SCRIPTS_INTRO,
    SidebarSectionInfoPopup,
)


class TestCollectionHeader:
    """Tests for the header widget (buttons and search bar)."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Header can be instantiated without errors."""
        header = CollectionHeader()
        qtbot.addWidget(header)
        assert header is not None
        assert header.height() == 70

    def test_new_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the collection tile emits ``new_collection_requested(None)``."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        popup = header._popup
        assert isinstance(popup, NewItemPopup)
        with qtbot.waitSignal(header.new_collection_requested, timeout=1000) as blocker:
            popup.new_collection_clicked.emit()

        assert blocker.args == [None]

    def test_search_changed_signal(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search box emits ``search_changed``."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        with qtbot.waitSignal(header.search_changed, timeout=1000) as blocker:
            header._search.setText("hello")

        assert blocker.args == ["hello"]

    def test_new_request_emits_draft_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the request tile emits ``new_request_requested(None)`` (draft)."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        popup = header._popup
        assert isinstance(popup, NewItemPopup)
        with qtbot.waitSignal(header.new_request_requested, timeout=1000) as blocker:
            popup.new_request_clicked.emit()

        assert blocker.args == [None]

    def test_set_selected_collection_id(self, qapp: QApplication, qtbot) -> None:
        """``set_selected_collection_id`` stores the collection ID."""
        header = CollectionHeader()
        qtbot.addWidget(header)

        header.set_selected_collection_id(42)
        assert header._selected_collection_id == 42

        header.set_selected_collection_id(None)
        assert header._selected_collection_id is None

    def test_collections_header_has_info_button(self, qapp: QApplication, qtbot) -> None:
        """Collections variant shows a section info icon."""
        header = CollectionHeader(tree_kind="collections")
        qtbot.addWidget(header)

        info_btn = header.findChild(QToolButton, "sidebarSectionInfoButton")
        assert info_btn is not None

    def test_collections_info_popup_content(self, qapp: QApplication, qtbot) -> None:
        """Collections info button opens the collections explainer."""
        header = CollectionHeader(tree_kind="collections")
        qtbot.addWidget(header)
        header.show()
        qtbot.waitExposed(header)

        header._toggle_section_info()
        popup = header._info_popup
        assert popup is not None
        assert isinstance(popup, SidebarSectionInfoPopup)
        assert popup.isVisible()

        texts = [label.text() for label in popup.findChildren(QLabel)]
        assert "Collections" in texts
        assert COLLECTIONS_INTRO in texts

        close_btn = popup.findChild(QToolButton, "infoPopupCloseButton")
        assert close_btn is not None
        close_btn.click()
        assert not popup.isVisible()

    def test_local_scripts_header_has_info_button(self, qapp: QApplication, qtbot) -> None:
        """Local scripts variant shows an info icon instead of inline intro text."""
        header = CollectionHeader(tree_kind="local_scripts")
        qtbot.addWidget(header)

        assert isinstance(header._popup, NewLocalScriptItemPopup)
        info_btn = header.findChild(QToolButton, "sidebarSectionInfoButton")
        assert info_btn is not None
        assert header.findChild(QLabel, "localScriptsIntroLabel") is None

    def test_local_scripts_info_popup_content(self, qapp: QApplication, qtbot) -> None:
        """Info button opens a popup with the Local scripts explainer."""
        header = CollectionHeader(tree_kind="local_scripts")
        qtbot.addWidget(header)
        header.show()
        qtbot.waitExposed(header)

        header._toggle_section_info()
        popup = header._info_popup
        assert popup is not None
        assert isinstance(popup, SidebarSectionInfoPopup)
        assert popup.isVisible()

        texts = [label.text() for label in popup.findChildren(QLabel)]
        assert "Local scripts" in texts
        assert LOCAL_SCRIPTS_INTRO in texts
