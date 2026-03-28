"""Tests for the CompletionPopup widget.

Exercises popup construction, item population, keyboard navigation,
accept/dismiss signals, and the doc label display.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.widgets.code_editor.completion.engine import CompletionItem
from ui.widgets.code_editor.completion.popup import CompletionPopup


def _make_items(count: int = 3) -> list[CompletionItem]:
    """Create *count* simple completion items for testing."""
    return [
        CompletionItem(
            label=f"item_{i}",
            kind="method" if i % 2 == 0 else "property",
            type_str="void" if i % 2 == 0 else "string",
            doc=f"Description for item {i}",
            signature=f"(arg{i})" if i % 2 == 0 else "",
            insert_text=f"item_{i}",
        )
        for i in range(count)
    ]


# -- Construction ------------------------------------------------------


class TestCompletionPopupConstruction:
    """Basic popup construction and properties."""

    def test_creates_without_error(self, qapp: QApplication, qtbot) -> None:
        """CompletionPopup can be constructed."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        assert popup.objectName() == "completionPopup"

    def test_initially_hidden(self, qapp: QApplication, qtbot) -> None:
        """Popup is not visible after construction."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        assert not popup.is_active()

    def test_has_list_widget(self, qapp: QApplication, qtbot) -> None:
        """Popup contains a QListWidget."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        assert popup._list is not None

    def test_has_doc_label(self, qapp: QApplication, qtbot) -> None:
        """Popup contains a doc label initially hidden."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        assert popup._doc_label is not None
        assert popup._doc_label.isHidden()


# -- Item population --------------------------------------------------


class TestCompletionPopupItems:
    """Tests for set_items() and list population."""

    def test_set_items_populates_list(self, qapp: QApplication, qtbot) -> None:
        """set_items adds rows to the internal list."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        items = _make_items(5)
        popup.set_items(items)
        assert popup._list.count() == 5

    def test_set_items_selects_first(self, qapp: QApplication, qtbot) -> None:
        """First item is selected after set_items."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        assert popup._list.currentRow() == 0

    def test_set_items_clears_previous(self, qapp: QApplication, qtbot) -> None:
        """set_items replaces any previous items."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(5))
        popup.set_items(_make_items(2))
        assert popup._list.count() == 2

    def test_set_items_stores_data_roles(self, qapp: QApplication, qtbot) -> None:
        """Items carry insert_text, kind, and type_str in data roles."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        items = _make_items(1)
        popup.set_items(items)
        li = popup._list.item(0)
        assert li.data(Qt.ItemDataRole.UserRole) == "item_0"
        assert li.data(Qt.ItemDataRole.UserRole + 1) == "method"
        assert li.data(Qt.ItemDataRole.UserRole + 2) == "void"

    def test_empty_items_clears_list(self, qapp: QApplication, qtbot) -> None:
        """Setting empty items clears the list."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        popup.set_items([])
        assert popup._list.count() == 0


# -- Navigation --------------------------------------------------------


class TestCompletionPopupNavigation:
    """Tests for select_next() and select_previous()."""

    def test_select_next_moves_down(self, qapp: QApplication, qtbot) -> None:
        """select_next advances the selection by one row."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        assert popup._list.currentRow() == 0
        popup.select_next()
        assert popup._list.currentRow() == 1

    def test_select_next_clamps_at_end(self, qapp: QApplication, qtbot) -> None:
        """select_next does not go past the last item."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(2))
        popup.select_next()
        popup.select_next()
        popup.select_next()
        assert popup._list.currentRow() == 1

    def test_select_previous_moves_up(self, qapp: QApplication, qtbot) -> None:
        """select_previous moves the selection up by one row."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        popup.select_next()
        popup.select_next()
        assert popup._list.currentRow() == 2
        popup.select_previous()
        assert popup._list.currentRow() == 1

    def test_select_previous_clamps_at_top(self, qapp: QApplication, qtbot) -> None:
        """select_previous does not go below row 0."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        popup.select_previous()
        assert popup._list.currentRow() == 0


# -- Accept and dismiss signals ----------------------------------------


class TestCompletionPopupSignals:
    """Tests for item_selected and dismissed signals."""

    def test_accept_current_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """accept_current emits item_selected with insert_text and kind."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))

        with qtbot.waitSignal(popup.item_selected, timeout=1000) as blocker:
            popup.accept_current()

        insert_text, kind = blocker.args
        assert insert_text == "item_0"
        assert kind == "method"

    def test_accept_second_item(self, qapp: QApplication, qtbot) -> None:
        """Accepting after navigating emits the correct item."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        popup.select_next()

        with qtbot.waitSignal(popup.item_selected, timeout=1000) as blocker:
            popup.accept_current()

        insert_text, kind = blocker.args
        assert insert_text == "item_1"
        assert kind == "property"

    def test_dismiss_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """dismiss() emits the dismissed signal."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(1))
        popup.show()

        with qtbot.waitSignal(popup.dismissed, timeout=1000):
            popup.dismiss()

    def test_dismiss_hides_popup(self, qapp: QApplication, qtbot) -> None:
        """dismiss() hides the popup widget."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(1))
        popup.show()
        assert popup.is_active()
        popup.dismiss()
        assert not popup.is_active()

    def test_accept_empty_list_dismisses(self, qapp: QApplication, qtbot) -> None:
        """accept_current on empty list dismisses instead."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items([])

        with qtbot.waitSignal(popup.dismissed, timeout=1000):
            popup.accept_current()


# -- Doc label ---------------------------------------------------------


class TestCompletionPopupDocLabel:
    """Tests for the doc label above the completion list."""

    def test_doc_label_shows_on_selection(self, qapp: QApplication, qtbot) -> None:
        """Doc label appears when an item with a doc is selected."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        # First item (method) has a signature, so doc should not be hidden.
        assert not popup._doc_label.isHidden()

    def test_doc_label_contains_description(self, qapp: QApplication, qtbot) -> None:
        """Doc label text includes the item's doc string."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        text = popup._doc_label.text()
        assert "Description for item 0" in text

    def test_doc_label_contains_signature(self, qapp: QApplication, qtbot) -> None:
        """Doc label includes method signature when present."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        text = popup._doc_label.text()
        assert "(arg0)" in text

    def test_doc_label_updates_on_navigation(self, qapp: QApplication, qtbot) -> None:
        """Doc label updates when selection changes."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(3))
        popup.select_next()
        text = popup._doc_label.text()
        assert "Description for item 1" in text

    def test_doc_label_hides_when_no_doc(self, qapp: QApplication, qtbot) -> None:
        """Doc label hides for items without doc or signature."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        items = [
            CompletionItem(
                label="bare",
                kind="property",
                type_str="",
                doc="",
                signature="",
                insert_text="bare",
            )
        ]
        popup.set_items(items)
        assert popup._doc_label.isHidden()


# -- is_active ---------------------------------------------------------


class TestCompletionPopupActive:
    """Tests for the is_active() helper."""

    def test_not_active_when_hidden(self, qapp: QApplication, qtbot) -> None:
        """is_active returns False when hidden."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        assert not popup.is_active()

    def test_active_when_shown(self, qapp: QApplication, qtbot) -> None:
        """is_active returns True when visible."""
        popup = CompletionPopup()
        qtbot.addWidget(popup)
        popup.set_items(_make_items(1))
        popup.show()
        assert popup.is_active()
        popup.hide()
