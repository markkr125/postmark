"""Tests for the RequestEditorWidget."""

from __future__ import annotations

import json

from PySide6.QtGui import QKeySequence
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

    def test_graphql_splitter_has_handle_width(self, qapp: QApplication, qtbot) -> None:
        """The GraphQL splitter has a visible handle width for spacing."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        # Access the gql splitter from the stack page (page index 4).
        from PySide6.QtWidgets import QSplitter

        gql_page = editor._body_stack.widget(4)
        assert gql_page is not None
        splitter = gql_page.findChild(QSplitter)
        assert splitter is not None
        assert splitter.handleWidth() >= 6

    def test_graphql_query_with_operation_name(self, qapp: QApplication, qtbot) -> None:
        """Queries with named operations round-trip correctly."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        query = "mutation CreateUser($input: UserInput!) { createUser(input: $input) { id } }"
        variables = {"input": {"name": "Alice", "email": "a@b.com"}}
        stored = json.dumps({"query": query, "variables": variables})

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": stored,
            }
        )

        data = editor.get_request_data()
        body = json.loads(data["body"])
        assert body["query"] == query
        assert body["variables"] == variables

    def test_graphql_multiline_query(self, qapp: QApplication, qtbot) -> None:
        """Multiline queries are preserved through load/save cycle."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        query = "query {\n  users {\n    id\n    name\n  }\n}"
        stored = json.dumps({"query": query, "variables": {}})

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": stored,
            }
        )

        assert editor._gql_query_editor.toPlainText() == query
        data = editor.get_request_data()
        body = json.loads(data["body"])
        assert body["query"] == query

    def test_graphql_nested_variables(self, qapp: QApplication, qtbot) -> None:
        """Complex nested JSON variables survive the round-trip."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        variables = {"filter": {"status": "active", "tags": ["a", "b"]}, "limit": 50}
        stored = json.dumps({"query": "{ items }", "variables": variables})

        editor.load_request(
            {
                "name": "GQL",
                "method": "POST",
                "url": "http://gql",
                "body_mode": "graphql",
                "body": stored,
            }
        )

        data = editor.get_request_data()
        body = json.loads(data["body"])
        assert body["variables"] == variables

    def test_graphql_body_structure_for_http(self, qapp: QApplication, qtbot) -> None:
        """GraphQL body is valid JSON with 'query' and 'variables' keys."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["graphql"].setChecked(True)
        editor._gql_query_editor.setPlainText("{ me { id } }")
        editor._gql_variables_editor.setPlainText('{"page": 1}')

        data = editor.get_request_data()
        body = json.loads(data["body"])
        # The body must be a dict with exactly query + variables
        assert set(body.keys()) == {"query", "variables"}
        assert isinstance(body["query"], str)
        assert isinstance(body["variables"], dict)


class TestRequestEditorGraphQLSchema:
    """Tests for the GraphQL schema introspection UI controls."""

    def test_schema_label_exists(self, qapp: QApplication, qtbot) -> None:
        """The schema status label is present on the editor."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert hasattr(editor, "_gql_schema_label")
        assert editor._gql_schema_label.text() == "No schema"

    def test_fetch_button_exists(self, qapp: QApplication, qtbot) -> None:
        """The schema fetch button is present on the editor."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert hasattr(editor, "_gql_fetch_schema_btn")

    def test_no_schema_initially(self, qapp: QApplication, qtbot) -> None:
        """The stored schema is None by default."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert editor._gql_schema is None

    def test_fetch_without_url_shows_no_url(self, qapp: QApplication, qtbot) -> None:
        """Clicking fetch with an empty URL shows 'No URL' in the label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": ""})
        editor._on_fetch_schema()

        assert editor._gql_schema_label.text() == "No URL"

    def test_on_schema_fetched_updates_label(self, qapp: QApplication, qtbot) -> None:
        """A successful schema fetch updates the label with type count."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        mock_result = {
            "query_type": "Query",
            "mutation_type": "Mutation",
            "subscription_type": "",
            "types": [
                {"name": "Query", "kind": "OBJECT", "description": ""},
                {"name": "User", "kind": "OBJECT", "description": ""},
                {"name": "Role", "kind": "ENUM", "description": ""},
            ],
            "raw": {},
        }
        editor._on_schema_fetched(mock_result)

        assert editor._gql_schema_label.text() == "Schema (3 types)"
        assert editor._gql_schema == mock_result
        assert editor._gql_fetch_schema_btn.isEnabled()

    def test_on_schema_error_updates_label(self, qapp: QApplication, qtbot) -> None:
        """A schema fetch error shows 'Schema error' in the label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor._on_schema_error("Connection refused")

        assert editor._gql_schema_label.text() == "Schema error"
        assert editor._gql_schema is None
        assert "Connection refused" in editor._gql_schema_label.toolTip()
        assert editor._gql_fetch_schema_btn.isEnabled()

    def test_clear_resets_schema_state(self, qapp: QApplication, qtbot) -> None:
        """clear_request resets schema label and stored data."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://gql"})
        editor._on_schema_fetched(
            {
                "query_type": "Query",
                "mutation_type": "",
                "subscription_type": "",
                "types": [{"name": "Query", "kind": "OBJECT", "description": ""}],
                "raw": {},
            }
        )
        assert editor._gql_schema is not None

        editor.clear_request()

        assert editor._gql_schema is None
        assert editor._gql_schema_label.text() == "No schema"
        assert editor._gql_schema_label.toolTip() == ""

    def test_schema_label_tooltip_has_summary(self, qapp: QApplication, qtbot) -> None:
        """After fetching, the schema label tooltip contains the summary."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        mock_result = {
            "query_type": "Query",
            "mutation_type": "",
            "subscription_type": "",
            "types": [
                {"name": "Query", "kind": "OBJECT", "description": ""},
                {"name": "User", "kind": "OBJECT", "description": ""},
            ],
            "raw": {},
        }
        editor._on_schema_fetched(mock_result)

        tooltip = editor._gql_schema_label.toolTip()
        assert "Query: Query" in tooltip
        assert "OBJECT" in tooltip

    def test_schema_label_click_without_schema_triggers_fetch(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Clicking the schema label with no schema calls _on_fetch_schema."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        # No URL set, so fetch will show "No URL"
        editor.load_request({"name": "X", "method": "POST", "url": ""})
        editor._on_schema_label_clicked()

        assert editor._gql_schema_label.text() == "No URL"

    def test_fetch_disables_button_while_running(self, qapp: QApplication, qtbot) -> None:
        """The fetch button is disabled while a fetch is in progress."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://example.com/graphql"})

        # Simulate in-flight state by calling the start logic path
        # We can't actually run a full network fetch in tests, so we
        # test the label change that happens before the thread starts.
        # The _on_fetch_schema sets label to "Fetching..." and disables btn.
        # We need to prevent the actual thread from running. Patch SchemaFetchWorker.
        from unittest.mock import patch

        with patch("ui.request.request_editor.SchemaFetchWorker") as mock_worker_cls:
            mock_worker = mock_worker_cls.return_value
            mock_worker.set_endpoint = lambda **kw: None
            mock_worker.finished = editor.send_requested  # dummy signal
            mock_worker.error = editor.send_requested  # dummy signal

            with patch("ui.request.request_editor.QThread") as mock_thread_cls:
                mock_thread = mock_thread_cls.return_value
                mock_thread.started = editor.send_requested  # dummy signal
                mock_thread.isRunning.return_value = False
                mock_thread.start = lambda: None

                editor._on_fetch_schema()

                assert editor._gql_schema_label.text() == "Fetching\u2026"
                assert not editor._gql_fetch_schema_btn.isEnabled()


class TestRequestEditorBinary:
    """Tests for the binary file upload body mode."""

    def test_binary_mode_shows_file_picker(self, qapp: QApplication, qtbot) -> None:
        """Selecting binary mode activates the file picker stack page."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["binary"].setChecked(True)

        assert editor._body_stack.currentIndex() == 3

    def test_binary_button_exists(self, qapp: QApplication, qtbot) -> None:
        """The binary file select button is present."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert hasattr(editor, "_binary_file_btn")
        assert editor._binary_file_btn.text() == "Select File"

    def test_binary_label_default(self, qapp: QApplication, qtbot) -> None:
        """The binary file label starts with 'No file selected.'."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert editor._binary_file_label.text() == "No file selected."

    def test_load_request_binary_body(self, qapp: QApplication, qtbot) -> None:
        """Loading a binary request shows the file path in the label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "/path/to/file.png",
            }
        )

        assert editor._body_mode_buttons["binary"].isChecked()
        assert editor._binary_file_label.text() == "/path/to/file.png"

    def test_load_request_binary_empty_body(self, qapp: QApplication, qtbot) -> None:
        """Loading a binary request with empty body shows default label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "",
            }
        )

        assert editor._binary_file_label.text() == "No file selected."

    def test_get_request_data_binary_with_file(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns the file path for binary mode."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "/path/to/data.bin",
            }
        )

        data = editor.get_request_data()
        assert data["body_mode"] == "binary"
        assert data["body"] == "/path/to/data.bin"

    def test_get_request_data_binary_no_file(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns empty body when no file is selected."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "POST", "url": "http://x"})
        editor._body_mode_buttons["binary"].setChecked(True)

        data = editor.get_request_data()
        assert data["body_mode"] == "binary"
        assert data["body"] == ""

    def test_clear_resets_binary_label(self, qapp: QApplication, qtbot) -> None:
        """clear_request resets the binary file label."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "/path/to/file.png",
            }
        )
        editor.clear_request()

        assert editor._binary_file_label.text() == "No file selected."

    def test_binary_dirty_on_file_select(self, qapp: QApplication, qtbot) -> None:
        """Programmatically setting the file label marks dirty."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": "",
            }
        )
        assert not editor.is_dirty

        # Simulate what _on_select_binary_file does
        editor._binary_file_label.setText("/new/file.bin")
        editor._on_field_changed()
        assert editor.is_dirty

    def test_binary_roundtrip(self, qapp: QApplication, qtbot) -> None:
        """Binary file path survives a load -> get_request_data roundtrip."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        path = "/home/user/documents/payload.json"
        editor.load_request(
            {
                "name": "Upload",
                "method": "POST",
                "url": "http://upload",
                "body_mode": "binary",
                "body": path,
            }
        )

        data = editor.get_request_data()
        assert data["body_mode"] == "binary"
        assert data["body"] == path

    def test_binary_mode_radio_in_group(self, qapp: QApplication, qtbot) -> None:
        """The binary radio button is in the body mode group."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        assert "binary" in editor._body_mode_buttons
        btn = editor._body_mode_buttons["binary"]
        assert editor._body_mode_group.id(btn) != -1

    def test_switching_from_binary_to_raw(self, qapp: QApplication, qtbot) -> None:
        """Switching from binary to raw changes the stack page."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "POST",
                "url": "http://x",
                "body_mode": "binary",
                "body": "/file.bin",
            }
        )
        assert editor._body_stack.currentIndex() == 3

        editor._body_mode_buttons["raw"].setChecked(True)
        assert editor._body_stack.currentIndex() == 1


class TestRequestEditorBodySearch:
    """Tests for the body search bar (Ctrl+F / Cmd+F)."""

    def _make_editor_with_raw_body(
        self, qtbot, body: str, *, fmt: str = "JSON"
    ) -> RequestEditorWidget:
        """Return an editor pre-loaded with a raw body."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "POST",
                "url": "http://example.com",
                "body_mode": "raw",
                "raw_type": fmt,
                "body": body,
            }
        )
        return editor

    def test_search_bar_hidden_by_default(self, qapp: QApplication, qtbot) -> None:
        """Body search bar starts hidden."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert editor._body_search_bar.isHidden()

    def test_toggle_shows_and_hides_bar(self, qapp: QApplication, qtbot) -> None:
        """Toggling the body search opens and closes the bar."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        assert not editor._body_search_bar.isHidden()
        editor._toggle_body_search()
        assert editor._body_search_bar.isHidden()

    def test_search_finds_matches(self, qapp: QApplication, qtbot) -> None:
        """Typing in the search input highlights matches."""
        editor = self._make_editor_with_raw_body(qtbot, '{"hello": "world", "hello2": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("hello")
        assert len(editor._body_search_matches) == 2
        assert "1 of 2" in editor._body_search_count_label.text()

    def test_search_no_results(self, qapp: QApplication, qtbot) -> None:
        """Searching for nonexistent text shows 'No results'."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("zzz_not_found")
        assert len(editor._body_search_matches) == 0
        assert "No results" in editor._body_search_count_label.text()

    def test_search_next_wraps_around(self, qapp: QApplication, qtbot) -> None:
        """Next match wraps from the last back to the first."""
        editor = self._make_editor_with_raw_body(qtbot, "aaa")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("a")
        assert len(editor._body_search_matches) == 3
        assert editor._body_search_index == 0
        editor._body_search_next()
        assert editor._body_search_index == 1
        editor._body_search_next()
        assert editor._body_search_index == 2
        editor._body_search_next()
        assert editor._body_search_index == 0

    def test_search_prev_wraps_around(self, qapp: QApplication, qtbot) -> None:
        """Previous match wraps from the first back to the last."""
        editor = self._make_editor_with_raw_body(qtbot, "aaa")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("a")
        assert editor._body_search_index == 0
        editor._body_search_prev()
        assert editor._body_search_index == 2

    def test_close_clears_highlights(self, qapp: QApplication, qtbot) -> None:
        """Closing the search bar clears highlights and resets state."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("a")
        assert len(editor._body_search_matches) > 0
        editor._close_body_search()
        assert editor._body_search_bar.isHidden()
        assert editor._body_search_matches == []
        assert editor._body_search_index == -1

    def test_clear_request_closes_search(self, qapp: QApplication, qtbot) -> None:
        """Clearing the request closes the body search bar."""
        editor = self._make_editor_with_raw_body(qtbot, '{"a": 1}')
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        assert not editor._body_search_bar.isHidden()
        editor.clear_request()
        assert editor._body_search_bar.isHidden()

    def test_find_shortcut_uses_standard_key(self, qapp: QApplication, qtbot) -> None:
        """The find shortcut uses the platform-native Find key sequence."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        expected = QKeySequence(QKeySequence.StandardKey.Find)
        assert editor._body_find_shortcut.key() == expected

    def test_toggle_does_nothing_on_none_mode(self, qapp: QApplication, qtbot) -> None:
        """Toggling body search when body mode is 'none' does nothing."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request({"name": "T", "method": "GET", "url": "http://x", "body": ""})
        editor._toggle_body_search()
        assert editor._body_search_bar.isHidden()


class TestRequestEditorReplace:
    """Tests for the find-and-replace feature in the request body."""

    def _make_editor_with_raw_body(
        self, qtbot, body: str, *, fmt: str = "JSON"
    ) -> RequestEditorWidget:
        """Return an editor pre-loaded with a raw body."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        editor.load_request(
            {
                "name": "Test",
                "method": "POST",
                "url": "http://example.com",
                "body_mode": "raw",
                "raw_type": fmt,
                "body": body,
            }
        )
        return editor

    def test_replace_row_hidden_by_default(self, qapp: QApplication, qtbot) -> None:
        """Replace row starts hidden even when search bar is open."""
        editor = self._make_editor_with_raw_body(qtbot, "abc")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        assert not editor._body_search_bar.isHidden()
        assert editor._replace_row.isHidden()

    def test_toggle_replace_shows_row(self, qapp: QApplication, qtbot) -> None:
        """Clicking the chevron toggles the replace row visibility."""
        editor = self._make_editor_with_raw_body(qtbot, "abc")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._toggle_replace_row()
        assert not editor._replace_row.isHidden()
        assert editor._replace_toggle_btn.isChecked()
        editor._toggle_replace_row()
        assert editor._replace_row.isHidden()
        assert not editor._replace_toggle_btn.isChecked()

    def test_ctrl_r_opens_replace(self, qapp: QApplication, qtbot) -> None:
        """The replace shortcut is Ctrl+R."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        expected = QKeySequence("Ctrl+R")
        assert editor._body_replace_shortcut.key() == expected

    def test_toggle_body_replace_shows_both_rows(self, qapp: QApplication, qtbot) -> None:
        """_toggle_body_replace opens the search bar with the replace row."""
        editor = self._make_editor_with_raw_body(qtbot, "abc")
        editor._body_code_editor.setFocus()
        editor._toggle_body_replace()
        assert not editor._body_search_bar.isHidden()
        assert not editor._replace_row.isHidden()

    def test_replace_one_replaces_current_match(self, qapp: QApplication, qtbot) -> None:
        """Replace-one replaces the current match and re-searches."""
        editor = self._make_editor_with_raw_body(qtbot, "aXbXc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("X")
        assert len(editor._body_search_matches) == 2
        editor._replace_input.setText("Y")
        editor._replace_one()
        text = editor._body_code_editor.toPlainText()
        assert text == "aYbXc"
        # One match left after first replacement
        assert len(editor._body_search_matches) == 1

    def test_replace_all_replaces_every_match(self, qapp: QApplication, qtbot) -> None:
        """Replace-all replaces every occurrence at once."""
        editor = self._make_editor_with_raw_body(qtbot, "aXbXcX", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("X")
        assert len(editor._body_search_matches) == 3
        editor._replace_input.setText("Z")
        editor._replace_all()
        text = editor._body_code_editor.toPlainText()
        assert text == "aZbZcZ"
        assert len(editor._body_search_matches) == 0

    def test_replace_all_with_empty_string(self, qapp: QApplication, qtbot) -> None:
        """Replace-all with empty replacement removes all matches."""
        editor = self._make_editor_with_raw_body(qtbot, "aXbXc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("X")
        editor._replace_input.setText("")
        editor._replace_all()
        assert editor._body_code_editor.toPlainText() == "abc"

    def test_replace_one_no_matches_is_noop(self, qapp: QApplication, qtbot) -> None:
        """Replace-one with no matches does nothing."""
        editor = self._make_editor_with_raw_body(qtbot, "abc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._body_search_input.setText("ZZZ")
        assert len(editor._body_search_matches) == 0
        editor._replace_input.setText("Y")
        editor._replace_one()
        assert editor._body_code_editor.toPlainText() == "abc"

    def test_close_resets_replace_row(self, qapp: QApplication, qtbot) -> None:
        """Closing the search bar hides and clears the replace row."""
        editor = self._make_editor_with_raw_body(qtbot, "abc", fmt="Text")
        editor._body_code_editor.setFocus()
        editor._toggle_body_search()
        editor._toggle_replace_row()
        editor._replace_input.setText("xyz")
        assert not editor._replace_row.isHidden()
        editor._close_body_search()
        assert editor._replace_row.isHidden()
        assert editor._replace_input.text() == ""
        assert not editor._replace_toggle_btn.isChecked()


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

        from ui.theme import method_color

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
        from ui.theme import method_color

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
        from ui.variable_line_edit import VariableLineEdit

        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert isinstance(editor._url_input, VariableLineEdit)

    def test_auth_fields_are_variable_line_edit(self, qapp: QApplication, qtbot) -> None:
        """Auth inputs use VariableLineEdit for variable highlighting."""
        from ui.variable_line_edit import VariableLineEdit

        editor = RequestEditorWidget()
        qtbot.addWidget(editor)
        assert isinstance(editor._bearer_token_input, VariableLineEdit)
        assert isinstance(editor._basic_username_input, VariableLineEdit)
        assert isinstance(editor._basic_password_input, VariableLineEdit)
        assert isinstance(editor._apikey_key_input, VariableLineEdit)
        assert isinstance(editor._apikey_value_input, VariableLineEdit)
