"""Tests for the FolderEditorWidget."""

from __future__ import annotations

from unittest.mock import patch

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


class TestFolderEditorRunsTab:
    """Tests for the Runs tab and Run button."""

    def test_runs_tab_exists(self, qapp: QApplication, qtbot) -> None:
        """The editor has a Runs tab."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        tab_labels = [editor._tabs.tabText(i) for i in range(editor._tabs.count())]
        assert "Runs" in tab_labels

    def test_run_button_exists(self, qapp: QApplication, qtbot) -> None:
        """The editor has a Run button."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._run_btn is not None
        assert editor._run_btn.text() == "Run"

    def test_run_button_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking Run emits run_requested with the collection ID."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_collection({"name": "Test"}, collection_id=42)

        with qtbot.waitSignal(editor.run_requested) as blocker:
            editor._run_btn.click()

        assert blocker.args == [42]

    def test_run_button_no_signal_without_collection(self, qapp: QApplication, qtbot) -> None:
        """Run button does not emit when no collection is loaded."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        signals: list[int] = []
        editor.run_requested.connect(signals.append)
        editor._run_btn.click()
        assert signals == []

    def test_load_runs_populates_table(self, qapp: QApplication, qtbot) -> None:
        """load_runs fills the runs table with history data."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        runs = [
            {
                "started_at": "2024-01-15 10:30:00",
                "source": "manual",
                "duration_ms": 2500,
                "total_tests": 10,
                "passed": 8,
                "failed": 2,
                "avg_response_ms": 120.5,
                "status": "completed",
            },
        ]
        editor.load_runs(runs)
        assert editor._runs_table.rowCount() == 1

    def test_load_runs_empty(self, qapp: QApplication, qtbot) -> None:
        """load_runs with empty list clears the table."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_runs([])
        assert editor._runs_table.rowCount() == 0

    def test_runs_table_has_skipped_column(self, qapp: QApplication, qtbot) -> None:
        """Runs table headers include a Skipped column."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        headers = []
        for i in range(editor._runs_table.columnCount()):
            item = editor._runs_table.horizontalHeaderItem(i)
            if item:
                headers.append(item.text())
        assert "Skipped" in headers

    def test_load_runs_skipped_value(self, qapp: QApplication, qtbot) -> None:
        """load_runs displays the skipped count."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        runs = [
            {
                "started_at": "2024-01-15 10:30:00",
                "source": "manual",
                "duration_ms": 1000,
                "total_tests": 5,
                "passed": 3,
                "failed": 1,
                "skipped": 1,
                "avg_response_ms": 50.0,
                "status": "completed",
            },
        ]
        editor.load_runs(runs)
        # Skipped is column index 6
        skipped_item = editor._runs_table.item(0, 6)
        assert skipped_item is not None
        assert skipped_item.text() == "1"


class TestFolderEditorScriptHistory:
    """Tests for the script version history button and version capture."""

    def test_history_button_exists(self, qapp: QApplication, qtbot) -> None:
        """The Scripts tab has a History button."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._history_btn is not None
        assert editor._history_btn.text() == "History"

    def test_version_capture_timer_created(self, qapp: QApplication, qtbot) -> None:
        """A version capture timer is created during init."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        assert editor._version_capture_timer.isSingleShot()

    @patch("ui.request.folder_editor.ScriptVersionService.capture")
    def test_version_capture_fires_on_edit(self, mock_capture, qapp: QApplication, qtbot) -> None:
        """Editing a script captures a version after the debounce."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)
        editor.load_collection({"name": "Coll"}, collection_id=7)

        editor._pre_request_edit.setPlainText("console.log('hi');")
        # Fire the timer immediately
        editor._version_capture_timer.stop()
        editor._capture_script_versions()

        mock_capture.assert_called()
        call_kwargs = mock_capture.call_args
        assert call_kwargs[1]["collection_id"] == 7
        assert call_kwargs[1]["request_id"] is None
        assert call_kwargs[1]["script_type"] == "pre_request"

    @patch("ui.request.folder_editor.ScriptVersionService.capture")
    def test_no_capture_without_collection(self, mock_capture, qapp: QApplication, qtbot) -> None:
        """Version capture does nothing without a loaded collection."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor._pre_request_edit.setPlainText("x")
        editor._capture_script_versions()

        mock_capture.assert_not_called()

    @patch("ui.request.folder_editor.ScriptVersionService.capture")
    def test_no_capture_during_load(self, mock_capture, qapp: QApplication, qtbot) -> None:
        """Loading data does not trigger version capture."""
        editor = FolderEditorWidget()
        qtbot.addWidget(editor)

        editor.load_collection(
            {"name": "Coll", "events": {"pre_request": "x"}},
            collection_id=5,
        )
        # Timer should NOT have started during load
        assert not editor._version_capture_timer.isActive()
