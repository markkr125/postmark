"""Tests for the KeyValueTableWidget reusable editor."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QStyledItemDelegate

from ui.key_value_table import (
    _COL_DELETE,
    _COL_KEY,
    _COL_VALUE,
    KeyValueTableWidget,
    _VariableHighlightDelegate,
)


class TestKeyValueTable:
    """Verify the key-value table widget behaviour."""

    def test_starts_with_one_empty_row(self, qapp, qtbot):
        """A fresh table has one empty row."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        assert widget.row_count() == 1
        assert widget.get_data() == []

    def test_add_empty_row(self, qapp, qtbot):
        """Adding an empty row increases the row count."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.add_empty_row()
        # 1 inserted empty + 1 ghost = 2
        assert widget.row_count() == 2

    def test_set_data_populates_rows(self, qapp, qtbot):
        """set_data should populate the table with the given rows."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        rows = [
            {"key": "Host", "value": "example.com"},
            {"key": "Accept", "value": "application/json"},
        ]
        widget.set_data(rows)
        # 2 data rows + 1 ghost row
        assert widget.row_count() == 3
        data = widget.get_data()
        assert len(data) == 2
        assert data[0]["key"] == "Host"
        assert data[0]["value"] == "example.com"
        assert data[1]["key"] == "Accept"

    def test_get_data_skips_empty_keys(self, qapp, qtbot):
        """get_data should exclude rows where the key is empty."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        rows = [
            {"key": "Host", "value": "example.com"},
            {"key": "", "value": "ignored"},
        ]
        widget.set_data(rows)
        data = widget.get_data()
        assert len(data) == 1
        assert data[0]["key"] == "Host"

    def test_enabled_flag(self, qapp, qtbot):
        """Disabled rows should have enabled=False in get_data."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        rows = [
            {"key": "X-Active", "value": "yes", "enabled": True},
            {"key": "X-Inactive", "value": "no", "enabled": False},
        ]
        widget.set_data(rows)
        data = widget.get_data()
        assert data[0]["enabled"] is True
        assert data[1]["enabled"] is False

    def test_to_text_only_enabled_rows(self, qapp, qtbot):
        """to_text should include only enabled rows."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        rows = [
            {"key": "Host", "value": "example.com", "enabled": True},
            {"key": "X-Skip", "value": "hidden", "enabled": False},
            {"key": "Accept", "value": "text/html", "enabled": True},
        ]
        widget.set_data(rows)
        text = widget.to_text()
        assert "Host: example.com" in text
        assert "Accept: text/html" in text
        assert "X-Skip" not in text

    def test_from_text_colon_separator(self, qapp, qtbot):
        """from_text should parse 'key: value' lines."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.from_text("Content-Type: application/json\nAccept: */*")
        data = widget.get_data()
        assert len(data) == 2
        assert data[0]["key"] == "Content-Type"
        assert data[0]["value"] == "application/json"
        assert data[1]["key"] == "Accept"
        assert data[1]["value"] == "*/*"

    def test_from_text_equals_separator(self, qapp, qtbot):
        """from_text should parse 'key=value' lines."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.from_text("page=1\nlimit=20")
        data = widget.get_data()
        assert len(data) == 2
        assert data[0]["key"] == "page"
        assert data[0]["value"] == "1"

    def test_description_roundtrip(self, qapp, qtbot):
        """Description field should survive a set_data/get_data roundtrip."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        rows = [{"key": "X-Custom", "value": "val", "description": "A note"}]
        widget.set_data(rows)
        data = widget.get_data()
        assert data[0]["description"] == "A note"

    def test_set_data_empty_leaves_one_row(self, qapp, qtbot):
        """Setting empty data should leave one blank row."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.set_data([])
        assert widget.row_count() == 1
        assert widget.get_data() == []

    def test_data_changed_signal_on_set(self, qapp, qtbot):
        """data_changed should NOT fire during programmatic set_data."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        fired = []
        widget.data_changed.connect(lambda: fired.append(True))
        widget.set_data([{"key": "a", "value": "b"}])
        assert len(fired) == 0

    def test_checkbox_toggle_emits_data_changed(self, qapp, qtbot):
        """Toggling a checkbox should emit data_changed."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.set_data([{"key": "X-Key", "value": "v", "enabled": True}])

        # Find the checkbox in row 0
        container = widget._table.cellWidget(0, 0)
        cb = container.findChild(QCheckBox)
        assert cb is not None

        with qtbot.waitSignal(widget.data_changed, timeout=1000):
            cb.setChecked(False)

    def test_ghost_row_auto_appends(self, qapp, qtbot):
        """Typing a key in the ghost row should auto-append a new ghost."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        assert widget.row_count() == 1  # Only ghost

        # Simulate typing into the ghost row's key cell
        ghost_row = widget.row_count() - 1
        widget._table.item(ghost_row, _COL_KEY).setText("NewKey")

        # Ghost was promoted; a new ghost was added
        assert widget.row_count() == 2
        assert widget.get_data()[0]["key"] == "NewKey"

    def test_inline_delete_removes_row(self, qapp, qtbot):
        """Clicking the inline delete button removes the target row."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        widget.set_data(
            [
                {"key": "A", "value": "1"},
                {"key": "B", "value": "2"},
            ]
        )
        assert widget.row_count() == 3  # 2 data + 1 ghost

        # Get delete button for row 0, make it visible, and click
        btn = widget._table.cellWidget(0, _COL_DELETE)
        assert isinstance(btn, QPushButton)
        btn.show()
        btn.click()

        assert widget.row_count() == 2  # 1 data + 1 ghost
        data = widget.get_data()
        assert len(data) == 1
        assert data[0]["key"] == "B"

    def test_delete_button_hidden_on_ghost(self, qapp, qtbot):
        """The ghost row's delete button should always be hidden."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        ghost_row = widget.row_count() - 1
        btn = widget._table.cellWidget(ghost_row, _COL_DELETE)
        assert isinstance(btn, QPushButton)
        assert not btn.isVisible()


class TestVariableHighlightDelegate:
    """Tests for the ``_VariableHighlightDelegate`` on key-value tables."""

    def test_delegate_is_installed(self, qapp: QApplication, qtbot) -> None:
        """The table uses a _VariableHighlightDelegate by default."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        delegate = widget._table.itemDelegate()
        assert isinstance(delegate, _VariableHighlightDelegate)

    def test_delegate_highlights_key_and_value_columns(self, qapp: QApplication, qtbot) -> None:
        """The delegate is configured to highlight key and value columns."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        delegate = widget._highlight_delegate
        assert _COL_KEY in delegate._columns
        assert _COL_VALUE in delegate._columns

    def test_delegate_is_subclass_of_styled(self, qapp: QApplication, qtbot) -> None:
        """_VariableHighlightDelegate extends QStyledItemDelegate."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        assert isinstance(widget._highlight_delegate, QStyledItemDelegate)

    def test_set_variable_map(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map propagates to the delegate."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        m = {"host": "example.com"}
        widget.set_variable_map(m)
        assert widget._highlight_delegate._variable_map is m

    def test_delegate_variable_map_default_empty(self, qapp: QApplication, qtbot) -> None:
        """Delegate starts with an empty variable map."""
        widget = KeyValueTableWidget()
        qtbot.addWidget(widget)
        assert widget._highlight_delegate._variable_map == {}
