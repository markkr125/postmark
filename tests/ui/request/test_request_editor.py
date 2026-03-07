"""Tests for the RequestEditorWidget — core behaviour."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.environment_service import VariableDetail
from ui.request.request_editor import RequestEditorWidget


class TestRequestEditorWidget:
    """Tests for the request editor pane."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Widget can be instantiated without errors."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert editor is not None

    def test_starts_in_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Editor starts with the empty-state label visible."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        # Widget is not shown, so use isHidden() which checks local state
        assert not editor._empty_label.isHidden()
        assert editor._tabs.isHidden()

    def test_load_request_shows_content(self, qapp: QApplication, qtbot) -> None:
        """Loading a request hides the empty state and shows content."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Get Users",
                "method": "GET",
                "url": "https://api.example.com/users",
                "body": "",
                "request_parameters": "page=1",
                "headers": "Accept: application/json",
            }
        )

        assert editor._empty_label.isHidden()
        assert not editor._tabs.isHidden()
        assert editor._url_input.text() == "https://api.example.com/users"
        assert editor._method_combo.currentText() == "GET"
        # Params and headers are now key-value tables
        params_data = editor._params_table.get_data()
        assert len(params_data) == 1
        assert params_data[0]["key"] == "page"
        assert params_data[0]["value"] == "1"
        headers_data = editor._headers_table.get_data()
        assert len(headers_data) == 1
        assert headers_data[0]["key"] == "Accept"
        assert headers_data[0]["value"] == "application/json"

    def test_clear_request_restores_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Clearing resets to the empty state."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor.clear_request()

        assert not editor._empty_label.isHidden()
        assert editor._tabs.isHidden()
        assert editor._url_input.text() == ""

    def test_load_request_with_scripts_dict(self, qapp: QApplication, qtbot) -> None:
        """Scripts dict is displayed as formatted JSON."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "scripts": {"pre": "console.log('hi')"},
            }
        )

        text = editor._scripts_edit.toPlainText()
        assert "console.log" in text


class TestRequestEditorDirtyTracking:
    """Tests for dirty state tracking in the request editor."""

    def test_not_dirty_after_load(self, qapp: QApplication, qtbot) -> None:
        """Editor is not dirty immediately after loading a request."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        assert not editor.is_dirty

    def test_dirty_after_url_change(self, qapp: QApplication, qtbot) -> None:
        """Editing the URL marks the editor as dirty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        editor._url_input.setText("http://changed")
        assert editor.is_dirty

    def test_dirty_after_body_change(self, qapp: QApplication, qtbot) -> None:
        """Editing the body marks the editor as dirty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._body_code_editor.setPlainText("new body")
        assert editor.is_dirty

    def test_dirty_indicator_in_title(self, qapp: QApplication, qtbot) -> None:
        """Dirty state is tracked via the is_dirty flag."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "My Request", "method": "GET", "url": "http://x"})
        editor._url_input.setText("http://changed")
        assert editor.is_dirty

    def test_set_dirty_false_removes_indicator(self, qapp: QApplication, qtbot) -> None:
        """Clearing dirty state resets the flag."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "My Request", "method": "GET", "url": "http://x"})
        editor._url_input.setText("http://changed")
        editor._set_dirty(False)
        assert not editor.is_dirty

    def test_request_id_stored(self, qapp: QApplication, qtbot) -> None:
        """load_request stores the request_id."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"}, request_id=42)
        assert editor.request_id == 42

    def test_clear_resets_dirty(self, qapp: QApplication, qtbot) -> None:
        """clear_request resets the dirty flag."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        editor._url_input.setText("http://changed")
        editor.clear_request()
        assert not editor.is_dirty
        assert editor.request_id is None


class TestRequestEditorBodyMode:
    """Tests for body mode selector in the request editor."""

    def test_body_modes_exist(self, qapp: QApplication, qtbot) -> None:
        """All body mode radio buttons are present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert "none" in editor._body_mode_buttons
        assert "raw" in editor._body_mode_buttons
        assert "form-data" in editor._body_mode_buttons

    def test_none_mode_default(self, qapp: QApplication, qtbot) -> None:
        """Default body mode is 'none'."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert editor._body_mode_buttons["none"].isChecked()

    def test_raw_format_visible_when_raw(self, qapp: QApplication, qtbot) -> None:
        """Raw format dropdown is visible when 'raw' mode is selected."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["raw"].setChecked(True)
        assert not editor._raw_format_combo.isHidden()

    def test_raw_format_hidden_when_not_raw(self, qapp: QApplication, qtbot) -> None:
        """Raw format dropdown is hidden when mode is not 'raw'."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["form-data"].setChecked(True)
        assert editor._raw_format_combo.isHidden()

    def test_load_request_with_body_mode(self, qapp: QApplication, qtbot) -> None:
        """Loading a request with body_mode sets the correct radio."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "POST",
                "url": "http://x",
                "body_mode": "raw",
                "body_options": {"raw": {"language": "json"}},
            }
        )

        assert editor._body_mode_buttons["raw"].isChecked()
        assert editor._raw_format_combo.currentText() == "JSON"

    def test_get_request_data_includes_body_mode(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns the current body mode."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("JSON")

        data = editor.get_request_data()
        assert data["body_mode"] == "raw"
        assert data["body_options"] == {"raw": {"language": "json"}}


class TestRequestEditorDescription:
    """Tests for the request description field."""

    def test_description_tab_exists(self, qapp: QApplication, qtbot) -> None:
        """The editor has a Description tab."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        tab_titles = [editor._tabs.tabText(i) for i in range(editor._tabs.count())]
        assert "Description" in tab_titles

    def test_load_with_description(self, qapp: QApplication, qtbot) -> None:
        """Loading a request with a description populates the field."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "GET",
                "url": "http://x",
                "description": "A test request",
            }
        )
        assert editor._description_edit.toPlainText() == "A test request"

    def test_get_request_data_includes_description(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns the description."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "GET",
                "url": "http://x",
                "description": "Some notes",
            }
        )
        data = editor.get_request_data()
        assert data["description"] == "Some notes"

    def test_clear_resets_description(self, qapp: QApplication, qtbot) -> None:
        """Clearing the editor resets the description field."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "GET",
                "url": "http://x",
                "description": "Notes",
            }
        )
        editor.clear_request()
        assert editor._description_edit.toPlainText() == ""


class TestRequestEditorDirtyChanged:
    """Tests for dirty_changed signal on the request editor."""

    def test_dirty_changed_signal_emitted(self, qapp: QApplication, qtbot) -> None:
        """dirty_changed signal fires when dirty state transitions."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})

        signals: list[bool] = []
        editor.dirty_changed.connect(signals.append)

        editor._url_input.setText("http://changed")
        assert signals == [True]

        editor._set_dirty(False)
        assert signals == [True, False]

    def test_dirty_changed_not_emitted_on_same_value(self, qapp: QApplication, qtbot) -> None:
        """dirty_changed does not fire when dirty stays the same."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})

        signals: list[bool] = []
        editor.dirty_changed.connect(signals.append)

        # Already False -> False: no emission
        editor._set_dirty(False)
        assert signals == []

        # True -> True: only first transition emits
        editor._url_input.setText("http://changed")
        editor._url_input.setText("http://changed2")
        assert signals == [True]


class TestRequestEditorTabIndicators:
    """Tests for content-dot indicators on section tabs."""

    def test_tabs_clean_after_empty_load(self, qapp: QApplication, qtbot) -> None:
        """All tabs show plain names after loading an empty request."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        for i, name in enumerate(("Params", "Headers", "Body", "Auth", "Description", "Scripts")):
            assert editor._tabs.tabText(i) == name

    def test_params_dot_shown(self, qapp: QApplication, qtbot) -> None:
        """Params tab gets a dot when parameters are present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "request_parameters": [{"key": "q", "value": "1", "enabled": True}],
            }
        )
        assert editor._tabs.tabText(0).endswith(" \u2022")

    def test_headers_dot_shown(self, qapp: QApplication, qtbot) -> None:
        """Headers tab gets a dot when headers are present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "headers": [{"key": "Accept", "value": "application/json", "enabled": True}],
            }
        )
        assert editor._tabs.tabText(1).endswith(" \u2022")

    def test_body_dot_shown_when_not_none(self, qapp: QApplication, qtbot) -> None:
        """Body tab gets a dot when body mode is not 'none'."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "POST",
                "url": "http://x",
                "body_mode": "raw",
                "body": '{"a": 1}',
            }
        )
        assert editor._tabs.tabText(2).endswith(" \u2022")

    def test_auth_dot_shown(self, qapp: QApplication, qtbot) -> None:
        """Auth tab gets a dot when auth is configured."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "abc"}]},
            }
        )
        assert editor._tabs.tabText(3).endswith(" \u2022")

    def test_description_dot_shown(self, qapp: QApplication, qtbot) -> None:
        """Description tab gets a dot when description is non-empty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "description": "Some notes",
            }
        )
        assert editor._tabs.tabText(4).endswith(" \u2022")

    def test_scripts_dot_shown(self, qapp: QApplication, qtbot) -> None:
        """Scripts tab gets a dot when scripts are present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "scripts": {"pre": "console.log('hi')"},
            }
        )
        assert editor._tabs.tabText(5).endswith(" \u2022")

    def test_dot_removed_when_content_cleared(self, qapp: QApplication, qtbot) -> None:
        """Dot disappears when tab content is emptied."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "description": "Notes",
            }
        )
        assert editor._tabs.tabText(4).endswith(" \u2022")
        editor._description_edit.setPlainText("")
        assert editor._tabs.tabText(4) == "Description"


class TestRequestEditorMethodComboColors:
    """Tests for colored items in the HTTP method dropdown."""

    def test_delegate_sets_method_color(self, qapp: QApplication, qtbot) -> None:
        """The custom delegate injects the correct method colour for each item."""
        from typing import cast

        from PySide6.QtCore import QModelIndex
        from PySide6.QtGui import QColor, QPalette
        from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

        from ui.styling.theme import method_color

        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        delegate = cast(QStyledItemDelegate, editor._method_combo.itemDelegate())
        model = editor._method_combo.model()
        for i in range(editor._method_combo.count()):
            index: QModelIndex = model.index(i, 0)
            option = QStyleOptionViewItem()
            delegate.initStyleOption(option, index)
            expected = QColor(method_color(editor._method_combo.itemText(i)))
            assert option.palette.color(QPalette.ColorRole.Text) == expected
            assert option.font.bold()

    def test_selected_method_color_in_stylesheet(self, qapp: QApplication, qtbot) -> None:
        """The combo box stylesheet updates to reflect the selected method colour."""
        from ui.styling.theme import method_color

        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        for method in ("POST", "DELETE", "GET"):
            editor._method_combo.setCurrentText(method)
            color = method_color(method)
            assert color in editor._method_combo.styleSheet()


class TestRequestEditorVariableMap:
    """Tests for set_variable_map distribution to child widgets."""

    def test_set_variable_map_propagates_to_url(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map pushes the map to the URL input."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        m: dict[str, VariableDetail] = {
            "host": {"value": "example.com", "source": "collection", "source_id": 1}
        }
        editor.set_variable_map(m)
        assert editor._url_input._variable_map is m

    def test_set_variable_map_propagates_to_auth_fields(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map pushes the map to all auth inputs."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        m: dict[str, VariableDetail] = {
            "token": {"value": "abc123", "source": "environment", "source_id": 10}
        }
        editor.set_variable_map(m)
        assert editor._bearer_token_input._variable_map is m
        assert editor._basic_username_input._variable_map is m
        assert editor._basic_password_input._variable_map is m
        assert editor._apikey_key_input._variable_map is m
        assert editor._apikey_value_input._variable_map is m

    def test_set_variable_map_propagates_to_tables(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map pushes the map to key-value tables."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        m: dict[str, VariableDetail] = {
            "key": {"value": "value", "source": "collection", "source_id": 1}
        }
        editor.set_variable_map(m)
        assert editor._params_table._highlight_delegate._variable_map is m
        assert editor._headers_table._highlight_delegate._variable_map is m
        assert editor._body_form_table._highlight_delegate._variable_map is m

    def test_set_variable_map_propagates_to_code_editors(self, qapp: QApplication, qtbot) -> None:
        """set_variable_map pushes the map to code editors."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        m: dict[str, VariableDetail] = {
            "url": {"value": "https://api.test", "source": "environment", "source_id": 10}
        }
        editor.set_variable_map(m)
        assert editor._body_code_editor._variable_map is m
        assert editor._gql_query_editor._variable_map is m
        assert editor._gql_variables_editor._variable_map is m

    def test_url_input_is_variable_line_edit(self, qapp: QApplication, qtbot) -> None:
        """The URL input uses VariableLineEdit for variable highlighting."""
        from ui.widgets.variable_line_edit import VariableLineEdit

        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert isinstance(editor._url_input, VariableLineEdit)

    def test_auth_fields_are_variable_line_edit(self, qapp: QApplication, qtbot) -> None:
        """Auth inputs use VariableLineEdit for variable highlighting."""
        from ui.widgets.variable_line_edit import VariableLineEdit

        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert isinstance(editor._bearer_token_input, VariableLineEdit)
        assert isinstance(editor._basic_username_input, VariableLineEdit)
        assert isinstance(editor._basic_password_input, VariableLineEdit)
        assert isinstance(editor._apikey_key_input, VariableLineEdit)
        assert isinstance(editor._apikey_value_input, VariableLineEdit)
