"""Tests for RequestEditorWidget — GraphQL editing and schema introspection."""

from __future__ import annotations

import json

from PySide6.QtWidgets import QApplication

from ui.request.request_editor import RequestEditorWidget


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

        with patch("ui.request.request_editor.graphql.SchemaFetchWorker") as mock_worker_cls:
            mock_worker = mock_worker_cls.return_value
            mock_worker.set_endpoint = lambda **kw: None
            mock_worker.finished = editor.send_requested  # dummy signal
            mock_worker.error = editor.send_requested  # dummy signal

            with patch("ui.request.request_editor.graphql.QThread") as mock_thread_cls:
                mock_thread = mock_thread_cls.return_value
                mock_thread.started = editor.send_requested  # dummy signal
                mock_thread.isRunning.return_value = False
                mock_thread.start = lambda: None

                editor._on_fetch_schema()

                assert editor._gql_schema_label.text() == "Fetching\u2026"
                assert not editor._gql_fetch_schema_btn.isEnabled()
