"""Tests for the FolderEditorWidget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.folder_editor import FolderEditorWidget, _normalize_events


class TestFolderEditorConstruction:
    """Tests for basic construction and initial state."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Widget can be instantiated without errors."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor is not None

    def test_starts_in_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Editor starts with the empty-state label visible."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert not editor._empty_label.isHidden()
        assert editor._tabs.isHidden()

    def test_collection_id_initially_none(self, qapp: QApplication, qtbot) -> None:
        """The collection_id property is None before loading."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor.collection_id is None


class TestFolderEditorLoad:
    """Tests for loading collection data into the editor."""

    def _sample_data(self) -> dict:
        """Return a sample collection data dict."""
        return {
            "name": "My Folder",
            "description": "Folder description",
            "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "abc"}]},
            "events": {
                "pre_request": "console.log('pre');",
                "test": "console.log('test');",
            },
            "variables": [
                {"key": "host", "value": "localhost", "description": "Server host"},
            ],
        }

    def test_load_shows_content(self, qapp: QApplication, qtbot) -> None:
        """Loading a collection hides the empty state and shows content."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=42, request_count=5)

        assert editor._empty_label.isHidden()
        assert not editor._tabs.isHidden()
        assert editor._title_label.text() == "My Folder"
        assert editor.collection_id == 42

    def test_load_description(self, qapp: QApplication, qtbot) -> None:
        """Loading populates the description field."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=1)
        assert editor._description_edit.toPlainText() == "Folder description"

    def test_load_request_count(self, qapp: QApplication, qtbot) -> None:
        """Loading displays the request count label."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=1, request_count=5)
        assert "5 requests" in editor._request_count_label.text()

    def test_load_request_count_singular(self, qapp: QApplication, qtbot) -> None:
        """Single request count uses singular form."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=1, request_count=1)
        assert "1 request" in editor._request_count_label.text()
        assert "requests" not in editor._request_count_label.text()

    def test_load_bearer_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading bearer auth sets the combo and token field."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=1)
        assert editor._auth_type_combo.currentText() == "Bearer Token"
        assert editor._bearer_token_input.text() == "abc"

    def test_load_basic_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading basic auth sets the username and password fields."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        data = {
            "name": "Coll",
            "auth": {
                "type": "basic",
                "basic": [
                    {"key": "username", "value": "user1"},
                    {"key": "password", "value": "pass1"},
                ],
            },
        }
        editor.load_collection(data, collection_id=1)
        assert editor._auth_type_combo.currentText() == "Basic Auth"
        assert editor._basic_username_input.text() == "user1"
        assert editor._basic_password_input.text() == "pass1"

    def test_load_apikey_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading API key auth sets key, value, and add-to fields."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        data = {
            "name": "Coll",
            "auth": {
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": "X-API-Key"},
                    {"key": "value", "value": "secret"},
                    {"key": "in", "value": "header"},
                ],
            },
        }
        editor.load_collection(data, collection_id=1)
        assert editor._auth_type_combo.currentText() == "API Key"
        assert editor._apikey_key_input.text() == "X-API-Key"
        assert editor._apikey_value_input.text() == "secret"
        assert editor._apikey_add_to_combo.currentText() == "Header"

    def test_load_no_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading with no auth defaults to Inherit auth from parent."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll"}, collection_id=1)
        assert editor._auth_type_combo.currentText() == "Inherit auth from parent"

    def test_load_explicit_noauth(self, qapp: QApplication, qtbot) -> None:
        """Loading with explicit noauth selects No Auth."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll", "auth": {"type": "noauth"}}, collection_id=1)
        assert editor._auth_type_combo.currentText() == "No Auth"

    def test_get_inherit_auth_returns_none(self, qapp: QApplication, qtbot) -> None:
        """get_collection_data returns auth=None for inherit."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll"}, collection_id=1)
        result = editor.get_collection_data()
        assert result["auth"] is None

    def test_load_scripts(self, qapp: QApplication, qtbot) -> None:
        """Loading populates the pre-request and test script fields."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=1)
        assert editor._pre_request_edit.toPlainText() == "console.log('pre');"
        assert editor._test_script_edit.toPlainText() == "console.log('test');"

    def test_load_variables(self, qapp: QApplication, qtbot) -> None:
        """Loading populates the variables table."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(self._sample_data(), collection_id=1)
        rows = editor._variables_table.get_data()
        assert len(rows) == 1
        assert rows[0]["key"] == "host"
        assert rows[0]["value"] == "localhost"


class TestFolderEditorGetData:
    """Tests for retrieving data from the editor."""

    def test_get_collection_data_roundtrip(self, qapp: QApplication, qtbot) -> None:
        """Data loaded into the editor can be retrieved with get_collection_data."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        data = {
            "name": "Folder",
            "description": "Some desc",
            "auth": {"type": "noauth"},
            "events": {"pre_request": "// pre", "test": "// test"},
            "variables": [{"key": "k", "value": "v", "description": "d"}],
        }
        editor.load_collection(data, collection_id=1)

        result = editor.get_collection_data()
        assert result["description"] == "Some desc"
        assert result["auth"]["type"] == "noauth"
        assert result["events"]["pre_request"] == "// pre"
        assert result["events"]["test"] == "// test"
        assert result["variables"][0]["key"] == "k"

    def test_get_data_empty_description_returns_none(self, qapp: QApplication, qtbot) -> None:
        """An empty description field returns None."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll", "description": ""}, collection_id=1)
        result = editor.get_collection_data()
        assert result["description"] is None

    def test_get_bearer_auth_data(self, qapp: QApplication, qtbot) -> None:
        """Bearer auth data is correctly serialised."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        data = {
            "name": "Coll",
            "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "xyz"}]},
        }
        editor.load_collection(data, collection_id=1)
        result = editor.get_collection_data()
        assert result["auth"]["type"] == "bearer"
        token_entry = result["auth"]["bearer"][0]
        assert token_entry["key"] == "token"
        assert token_entry["value"] == "xyz"


class TestFolderEditorClear:
    """Tests for clearing the editor state."""

    def test_clear_restores_empty_state(self, qapp: QApplication, qtbot) -> None:
        """Clearing resets to the empty state."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Folder"}, collection_id=1)
        editor.clear()

        assert not editor._empty_label.isHidden()
        assert editor._tabs.isHidden()
        assert editor.collection_id is None

    def test_clear_resets_fields(self, qapp: QApplication, qtbot) -> None:
        """Clearing resets all input fields."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {
                "name": "Folder",
                "description": "desc",
                "events": {"pre_request": "x", "test": "y"},
            },
            collection_id=1,
        )
        editor.clear()

        assert editor._description_edit.toPlainText() == ""
        assert editor._pre_request_edit.toPlainText() == ""
        assert editor._test_script_edit.toPlainText() == ""
        assert editor._auth_type_combo.currentText() == "Inherit auth from parent"


class TestFolderEditorSignal:
    """Tests for the debounced collection_changed signal."""

    def test_load_does_not_emit(self, qapp: QApplication, qtbot) -> None:
        """Loading data does not trigger the collection_changed signal."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        emitted = []
        editor.collection_changed.connect(lambda d: emitted.append(d))

        editor.load_collection({"name": "Coll", "description": "x"}, collection_id=1)
        # Wait a bit longer than debounce
        qtbot.wait(1000)
        assert len(emitted) == 0

    def test_field_change_emits_after_debounce(self, qapp: QApplication, qtbot) -> None:
        """Changing a field emits collection_changed after the debounce period."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll"}, collection_id=1)

        with qtbot.waitSignal(editor.collection_changed, timeout=2000):
            editor._description_edit.setPlainText("Updated desc")


class TestNormalizeEvents:
    """Tests for the ``_normalize_events`` helper."""

    def test_none_returns_empty(self) -> None:
        """None input returns an empty dict."""
        assert _normalize_events(None) == {}

    def test_empty_list_returns_empty(self) -> None:
        """Empty list returns an empty dict."""
        assert _normalize_events([]) == {}

    def test_dict_passthrough(self) -> None:
        """A dict-format events value is returned as-is."""
        events = {"pre_request": "console.log('x');", "test": "pm.test('y');"}
        assert _normalize_events(events) == events

    def test_postman_list_format(self) -> None:
        """Postman list format is converted to our dict format."""
        postman_events = [
            {
                "listen": "prerequest",
                "script": {"exec": ["console.log('pre');", "// line 2"]},
            },
            {
                "listen": "test",
                "script": {"exec": ["pm.test('ok');"]},
            },
        ]
        result = _normalize_events(postman_events)
        assert result["pre_request"] == "console.log('pre');\n// line 2"
        assert result["test"] == "pm.test('ok');"

    def test_postman_list_unknown_listen_ignored(self) -> None:
        """Unknown listen types are ignored."""
        events = [{"listen": "unknown", "script": {"exec": ["x"]}}]
        assert _normalize_events(events) == {}

    def test_postman_list_missing_script(self) -> None:
        """Entries without a script dict are skipped."""
        events = [{"listen": "prerequest"}]
        result = _normalize_events(events)
        # script defaults to {} which has no exec, yielding empty string
        assert result == {"pre_request": ""}

    def test_non_dict_non_list_returns_empty(self) -> None:
        """An unexpected type returns an empty dict."""
        assert _normalize_events("bad") == {}


class TestFolderEditorMetadata:
    """Tests for metadata display in the overview tab."""

    def test_load_created_at(self, qapp: QApplication, qtbot) -> None:
        """Created-at timestamp is displayed."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {"name": "Coll"},
            collection_id=1,
            created_at="2024-01-15 10:30",
        )
        assert "2024-01-15 10:30" in editor._created_label.text()

    def test_load_updated_at(self, qapp: QApplication, qtbot) -> None:
        """Updated-at timestamp is displayed."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {"name": "Coll"},
            collection_id=1,
            updated_at="2024-06-01 14:00",
        )
        assert "2024-06-01 14:00" in editor._updated_label.text()

    def test_load_no_timestamps(self, qapp: QApplication, qtbot) -> None:
        """Missing timestamps result in empty labels."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll"}, collection_id=1)
        assert editor._created_label.text() == ""
        assert editor._updated_label.text() == ""

    def test_load_recent_requests(self, qapp: QApplication, qtbot) -> None:
        """Recent requests list is displayed."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        recent = [
            {"name": "Get Users", "method": "GET", "updated_at": "2024-01-01"},
            {"name": "Create User", "method": "POST"},
        ]
        editor.load_collection(
            {"name": "Coll"},
            collection_id=1,
            recent_requests=recent,
        )
        text = editor._recent_requests_label.text()
        assert "Get Users" in text
        assert "Create User" in text
        assert "GET" in text
        assert "POST" in text

    def test_load_empty_recent_requests(self, qapp: QApplication, qtbot) -> None:
        """Empty recent requests list shows placeholder text."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {"name": "Coll"},
            collection_id=1,
            recent_requests=[],
        )
        assert "No recent activity" in editor._recent_requests_label.text()

    def test_clear_resets_metadata(self, qapp: QApplication, qtbot) -> None:
        """Clearing resets metadata labels."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {"name": "Coll"},
            collection_id=1,
            created_at="2024-01-01 00:00",
            updated_at="2024-06-01 00:00",
            recent_requests=[{"name": "R", "method": "GET"}],
        )
        editor.clear()

        assert editor._created_label.text() == ""
        assert editor._updated_label.text() == ""
        assert editor._recent_requests_label.text() == ""


class TestFolderEditorPostmanEvents:
    """Tests for loading Postman list-format events."""

    def test_load_postman_events_populates_scripts(self, qapp: QApplication, qtbot) -> None:
        """Postman format events are loaded into script fields."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        data = {
            "name": "Coll",
            "events": [
                {
                    "listen": "prerequest",
                    "script": {"exec": ["console.log('pre');"]},
                },
                {
                    "listen": "test",
                    "script": {"exec": ["pm.test('ok');"]},
                },
            ],
        }
        editor.load_collection(data, collection_id=1)
        assert editor._pre_request_edit.toPlainText() == "console.log('pre');"
        assert editor._test_script_edit.toPlainText() == "pm.test('ok');"

    def test_load_none_events_no_crash(self, qapp: QApplication, qtbot) -> None:
        """None events value does not crash."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection({"name": "Coll", "events": None}, collection_id=1)
        assert editor._pre_request_edit.toPlainText() == ""
        assert editor._test_script_edit.toPlainText() == ""
