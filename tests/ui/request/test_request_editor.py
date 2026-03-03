"""Tests for the RequestEditorWidget."""

from __future__ import annotations

import json

from PySide6.QtWidgets import QApplication

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


class TestRequestEditorAuth:
    """Tests for the auth tab in the request editor."""

    def test_auth_tab_exists(self, qapp: QApplication, qtbot) -> None:
        """The Auth tab is present in the editor."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        tab_titles = [editor._tabs.tabText(i) for i in range(editor._tabs.count())]
        assert "Auth" in tab_titles

    def test_auth_type_combo_has_options(self, qapp: QApplication, qtbot) -> None:
        """Auth type dropdown contains all expected types."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        items = [
            editor._auth_type_combo.itemText(i) for i in range(editor._auth_type_combo.count())
        ]
        assert "No Auth" in items
        assert "Bearer Token" in items
        assert "Basic Auth" in items
        assert "API Key" in items

    def test_load_bearer_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading a request with bearer auth populates the token field."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "auth": {
                    "type": "bearer",
                    "bearer": [{"key": "token", "value": "mytoken123"}],
                },
            }
        )

        assert editor._auth_type_combo.currentText() == "Bearer Token"
        assert editor._bearer_token_input.text() == "mytoken123"

    def test_load_basic_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading a request with basic auth populates username/password."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "auth": {
                    "type": "basic",
                    "basic": [
                        {"key": "username", "value": "user"},
                        {"key": "password", "value": "pass"},
                    ],
                },
            }
        )

        assert editor._auth_type_combo.currentText() == "Basic Auth"
        assert editor._basic_username_input.text() == "user"
        assert editor._basic_password_input.text() == "pass"

    def test_get_auth_data_bearer(self, qapp: QApplication, qtbot) -> None:
        """get_request_data includes bearer auth configuration."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        editor._auth_type_combo.setCurrentText("Bearer Token")
        editor._bearer_token_input.setText("abc")

        data = editor.get_request_data()
        assert data["auth"]["type"] == "bearer"
        assert data["auth"]["bearer"][0]["value"] == "abc"

    def test_get_auth_data_no_auth(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns noauth when No Auth is selected."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        data = editor.get_request_data()
        assert data["auth"]["type"] == "noauth"

    def test_clear_resets_auth(self, qapp: QApplication, qtbot) -> None:
        """clear_request resets auth fields."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "auth": {
                    "type": "bearer",
                    "bearer": [{"key": "token", "value": "mytoken"}],
                },
            }
        )
        editor.clear_request()
        assert editor._auth_type_combo.currentText() == "No Auth"
        assert editor._bearer_token_input.text() == ""


class TestApplyAuth:
    """Tests for HttpSendWorker._apply_auth static method."""

    def test_bearer_auth_adds_header(self) -> None:
        """Bearer auth injects Authorization header."""
        from ui.request.http_worker import HttpSendWorker

        auth_data = {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "secret123"}],
        }
        url, headers = HttpSendWorker._apply_auth(auth_data, "http://x", None, {})
        assert headers is not None
        assert "Authorization: Bearer secret123" in headers

    def test_basic_auth_adds_header(self) -> None:
        """Basic auth injects base64-encoded Authorization header."""
        import base64

        from ui.request.http_worker import HttpSendWorker

        auth_data = {
            "type": "basic",
            "basic": [
                {"key": "username", "value": "user"},
                {"key": "password", "value": "pass"},
            ],
        }
        url, headers = HttpSendWorker._apply_auth(auth_data, "http://x", None, {})
        expected = base64.b64encode(b"user:pass").decode()
        assert headers is not None
        assert f"Authorization: Basic {expected}" in headers

    def test_apikey_header(self) -> None:
        """API key auth in header adds a custom header."""
        from ui.request.http_worker import HttpSendWorker

        auth_data = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "X-API-Key"},
                {"key": "value", "value": "mykey"},
                {"key": "in", "value": "header"},
            ],
        }
        url, headers = HttpSendWorker._apply_auth(auth_data, "http://x", None, {})
        assert headers is not None
        assert "X-API-Key: mykey" in headers

    def test_apikey_query(self) -> None:
        """API key auth in query appends to URL."""
        from ui.request.http_worker import HttpSendWorker

        auth_data = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "api_key"},
                {"key": "value", "value": "abc"},
                {"key": "in", "value": "query"},
            ],
        }
        url, headers = HttpSendWorker._apply_auth(auth_data, "http://x", None, {})
        assert "api_key=abc" in url

    def test_noauth_no_modification(self) -> None:
        """No auth leaves headers and URL unchanged."""
        from ui.request.http_worker import HttpSendWorker

        url, headers = HttpSendWorker._apply_auth({"type": "noauth"}, "http://x", "H: v", {})
        assert url == "http://x"
        assert headers == "H: v"


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


class TestRequestEditorGraphQL:
    """Tests for the GraphQL split-pane body editor."""

    def test_graphql_mode_shows_split_pane(self, qapp: QApplication, qtbot) -> None:
        """Selecting graphql mode activates the split-pane stack page."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["graphql"].setChecked(True)

        assert editor._body_stack.currentIndex() == 4

    def test_graphql_editors_exist(self, qapp: QApplication, qtbot) -> None:
        """GraphQL query and variables editors are present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert hasattr(editor, "_gql_query_editor")
        assert hasattr(editor, "_gql_variables_editor")

    def test_graphql_query_editor_language(self, qapp: QApplication, qtbot) -> None:
        """The query editor uses graphql syntax highlighting."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert editor._gql_query_editor.language == "graphql"

    def test_graphql_variables_editor_language(self, qapp: QApplication, qtbot) -> None:
        """The variables editor uses json syntax highlighting."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert editor._gql_variables_editor.language == "json"

    def test_get_request_data_graphql_wraps_json(self, qapp: QApplication, qtbot) -> None:
        """get_request_data produces JSON body with query and variables."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["graphql"].setChecked(True)
        editor._gql_query_editor.setPlainText("{ users { id name } }")
        editor._gql_variables_editor.setPlainText('{"limit": 10}')

        data = editor.get_request_data()
        assert data["body_mode"] == "graphql"
        body = json.loads(data["body"])
        assert body["query"] == "{ users { id name } }"
        assert body["variables"] == {"limit": 10}

    def test_get_request_data_graphql_empty_variables(self, qapp: QApplication, qtbot) -> None:
        """Empty variables field produces empty dict in JSON body."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["graphql"].setChecked(True)
        editor._gql_query_editor.setPlainText("{ me { id } }")

        data = editor.get_request_data()
        body = json.loads(data["body"])
        assert body["query"] == "{ me { id } }"
        assert body["variables"] == {}

    def test_get_request_data_graphql_invalid_variables(self, qapp: QApplication, qtbot) -> None:
        """Invalid JSON in variables is stored as raw string."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["graphql"].setChecked(True)
        editor._gql_query_editor.setPlainText("query Q { x }")
        editor._gql_variables_editor.setPlainText("{not valid json")

        data = editor.get_request_data()
        body = json.loads(data["body"])
        assert body["query"] == "query Q { x }"
        assert body["variables"] == "{not valid json"

    def test_load_request_graphql_body(self, qapp: QApplication, qtbot) -> None:
        """Loading a graphql request populates both editors."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        stored_body = json.dumps({"query": "{ users { id } }", "variables": {"page": 1}})
        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": stored_body,
            }
        )

        assert editor._body_mode_buttons["graphql"].isChecked()
        assert editor._gql_query_editor.toPlainText() == "{ users { id } }"
        vars_text = editor._gql_variables_editor.toPlainText()
        assert json.loads(vars_text) == {"page": 1}

    def test_load_request_graphql_plain_text_fallback(self, qapp: QApplication, qtbot) -> None:
        """Loading graphql with non-JSON body treats it as query text."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": "{ legacyQuery { name } }",
            }
        )

        assert editor._gql_query_editor.toPlainText() == "{ legacyQuery { name } }"
        assert editor._gql_variables_editor.toPlainText() == ""

    def test_load_request_graphql_empty_body(self, qapp: QApplication, qtbot) -> None:
        """Loading graphql with empty body leaves editors empty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": "",
            }
        )

        assert editor._gql_query_editor.toPlainText() == ""
        assert editor._gql_variables_editor.toPlainText() == ""

    def test_clear_resets_graphql_editors(self, qapp: QApplication, qtbot) -> None:
        """clear_request empties both GraphQL editors."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        stored_body = json.dumps({"query": "{ x }", "variables": {"v": 1}})
        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": stored_body,
            }
        )
        editor.clear_request()

        assert editor._gql_query_editor.toPlainText() == ""
        assert editor._gql_variables_editor.toPlainText() == ""

    def test_graphql_roundtrip(self, qapp: QApplication, qtbot) -> None:
        """Data survives a load -> get_request_data roundtrip."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        original_query = "query GetUser($id: ID!) { user(id: $id) { name email } }"
        original_vars = {"id": "42"}
        stored_body = json.dumps({"query": original_query, "variables": original_vars})

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": stored_body,
            }
        )

        data = editor.get_request_data()
        body = json.loads(data["body"])
        assert body["query"] == original_query
        assert body["variables"] == original_vars

    def test_graphql_dirty_on_query_change(self, qapp: QApplication, qtbot) -> None:
        """Editing the GraphQL query marks the editor as dirty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": json.dumps({"query": "{ x }", "variables": {}}),
            }
        )
        assert not editor.is_dirty
        editor._gql_query_editor.setPlainText("{ y }")
        assert editor.is_dirty

    def test_graphql_dirty_on_variables_change(self, qapp: QApplication, qtbot) -> None:
        """Editing the GraphQL variables marks the editor as dirty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": json.dumps({"query": "{ x }", "variables": {}}),
            }
        )
        assert not editor.is_dirty
        editor._gql_variables_editor.setPlainText('{"a": 1}')
        assert editor.is_dirty
