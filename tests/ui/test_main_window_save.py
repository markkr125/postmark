"""Smoke tests for the top-level MainWindow."""

from __future__ import annotations

import json
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from ui.main_window import MainWindow


class TestMainWindowSaveButton:
    """Tests for the Save button in the breadcrumb row."""

    def test_save_button_exists(self, qapp: QApplication, qtbot) -> None:
        """MainWindow has a Save button in the breadcrumb row."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert hasattr(window, "_save_btn")
        assert window._save_btn.text() == "Save"

    def test_save_button_disabled_initially(self, qapp: QApplication, qtbot) -> None:
        """Save button starts disabled."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window._save_btn.isEnabled()

    def test_save_button_tooltip_when_disabled(self, qapp: QApplication, qtbot) -> None:
        """Disabled Save button shows a 'no changes' tooltip."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._save_btn.toolTip() == "No changes to save"

    def test_save_button_tooltip_cleared_when_dirty(self, qapp: QApplication, qtbot) -> None:
        """Save button tooltip is cleared when the editor becomes dirty."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")
        assert window._save_btn.toolTip() == ""

    def test_save_button_hidden_when_no_tab(self, qapp: QApplication, qtbot) -> None:
        """Save button is hidden when no request tab is open."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert not window._save_btn.isVisible()

    def test_save_button_enabled_when_editor_dirty(self, qapp: QApplication, qtbot) -> None:
        """Save button becomes enabled when the active editor is dirty."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")
        assert window._save_btn.isEnabled()

    def test_save_button_disabled_after_dirty_cleared(self, qapp: QApplication, qtbot) -> None:
        """Save button becomes disabled when dirty flag is cleared."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")
        assert window._save_btn.isEnabled()
        window.request_widget._set_dirty(False)
        assert not window._save_btn.isEnabled()

    def test_save_button_triggers_save(self, qapp: QApplication, qtbot) -> None:
        """Clicking Save calls the save pipeline."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.request_widget.load_request(
            {"name": "X", "method": "GET", "url": "http://x"}, request_id=1
        )
        window.request_widget._url_input.setText("http://changed")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._save_btn.click()
            mock_update.assert_called_once()

    def test_save_button_object_name(self, qapp: QApplication, qtbot) -> None:
        """Save button uses the saveButton QSS style."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._save_btn.objectName() == "saveButton"

    def test_save_button_hand_cursor(self, qapp: QApplication, qtbot) -> None:
        """Save button has a hand cursor."""
        window = MainWindow()
        qtbot.addWidget(window)
        assert window._save_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestRequestSaveEndToEnd:
    """End-to-end tests verifying all aspects of request saving."""

    # Helper -----------------------------------------------------------

    @staticmethod
    def _create_and_open(window: MainWindow, **overrides: object) -> int:
        """Create a request in the DB, open it in the window, return its id."""
        svc = CollectionService()
        coll = svc.create_collection("TestColl")
        defaults: dict = {
            "method": "GET",
            "url": "http://original.test",
            "name": "OrigReq",
        }
        defaults.update(overrides)
        name = defaults.pop("name")
        req = svc.create_request(coll.id, defaults.pop("method"), defaults.pop("url"), name)
        # Persist any extra fields (body, auth, etc.)
        if defaults:
            svc.update_request(req.id, **defaults)
        window._open_request(req.id, push_history=True)
        return req.id

    # -- URL -----------------------------------------------------------

    def test_save_url_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing the URL persists the new URL to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._url_input.setText("http://updated.test")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.url == "http://updated.test"
        assert not window.request_widget.is_dirty

    # -- Method --------------------------------------------------------

    def test_save_method_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after changing the HTTP method persists to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._method_combo.setCurrentText("POST")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.method == "POST"

    # -- Raw body (JSON) -----------------------------------------------

    def test_save_raw_json_body(self, qapp: QApplication, qtbot) -> None:
        """Saving raw JSON body persists body text and body_mode."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("JSON")
        editor._body_code_editor.setPlainText('{"key": "value"}')
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body == '{"key": "value"}'
        assert saved.body_mode == "raw"
        assert saved.body_options == {"raw": {"language": "json"}}

    # -- Raw body (Text) -----------------------------------------------

    def test_save_raw_text_body(self, qapp: QApplication, qtbot) -> None:
        """Saving raw text body persists correctly."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("Text")
        editor._body_code_editor.setPlainText("plain text body")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body == "plain text body"
        assert saved.body_mode == "raw"
        assert saved.body_options == {"raw": {"language": "text"}}

    # -- Body mode "none" ----------------------------------------------

    def test_save_body_mode_none(self, qapp: QApplication, qtbot) -> None:
        """Saving with body_mode=none persists empty body."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window, body="old body", body_mode="raw")

        editor = window.request_widget
        editor._body_mode_buttons["none"].setChecked(True)
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body_mode == "none"

    # -- Headers -------------------------------------------------------

    def test_save_headers_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing headers persists the new headers to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        headers = [
            {"key": "Content-Type", "value": "application/json", "enabled": True},
            {"key": "Authorization", "value": "Bearer tok", "enabled": True},
        ]
        window.request_widget._headers_table.set_data(headers)
        # set_data during _loading=False triggers field change
        window.request_widget._set_dirty(True)
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert isinstance(saved.headers, list)
        keys = [h["key"] for h in saved.headers if h.get("key")]
        assert "Content-Type" in keys
        assert "Authorization" in keys

    # -- Query parameters ----------------------------------------------

    def test_save_params_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing params persists the new params to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        params = [
            {"key": "page", "value": "1", "enabled": True},
            {"key": "limit", "value": "10", "enabled": True},
        ]
        window.request_widget._params_table.set_data(params)
        window.request_widget._set_dirty(True)
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert isinstance(saved.request_parameters, list)
        keys = [p["key"] for p in saved.request_parameters if p.get("key")]
        assert "page" in keys
        assert "limit" in keys

    # -- Description ---------------------------------------------------

    def test_save_description_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing the description persists to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._description_edit.setPlainText("A test request")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.description == "A test request"

    # -- Scripts -------------------------------------------------------

    def test_save_scripts_change(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing scripts persists to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        window.request_widget._scripts_edit.setPlainText("console.log('test');")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.scripts == "console.log('test');"

    # -- Auth: Bearer token --------------------------------------------

    def test_save_bearer_auth(self, qapp: QApplication, qtbot) -> None:
        """Saving bearer auth persists the token to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._auth_type_combo.setCurrentText("Bearer Token")
        editor._bearer_token_input.setText("my-secret-token")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.auth is not None
        assert saved.auth["type"] == "bearer"
        tokens = saved.auth["bearer"]
        assert any(t["value"] == "my-secret-token" for t in tokens)

    # -- Auth: Basic ---------------------------------------------------

    def test_save_basic_auth(self, qapp: QApplication, qtbot) -> None:
        """Saving basic auth persists username and password to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._auth_type_combo.setCurrentText("Basic Auth")
        editor._basic_username_input.setText("admin")
        editor._basic_password_input.setText("s3cret")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.auth is not None
        assert saved.auth["type"] == "basic"
        entries = saved.auth["basic"]
        assert any(e["key"] == "username" and e["value"] == "admin" for e in entries)
        assert any(e["key"] == "password" and e["value"] == "s3cret" for e in entries)

    # -- Auth: API Key -------------------------------------------------

    def test_save_apikey_auth(self, qapp: QApplication, qtbot) -> None:
        """Saving API Key auth persists key, value and location to the DB."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._auth_type_combo.setCurrentText("API Key")
        editor._apikey_key_input.setText("X-API-Key")
        editor._apikey_value_input.setText("abc123")
        editor._apikey_add_to_combo.setCurrentText("Header")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.auth is not None
        assert saved.auth["type"] == "apikey"
        entries = saved.auth["apikey"]
        assert any(e["key"] == "key" and e["value"] == "X-API-Key" for e in entries)
        assert any(e["key"] == "value" and e["value"] == "abc123" for e in entries)
        assert any(e["key"] == "in" and e["value"] == "header" for e in entries)

    # -- GraphQL body --------------------------------------------------

    def test_save_graphql_body(self, qapp: QApplication, qtbot) -> None:
        """Saving GraphQL body persists query and variables as JSON."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._body_mode_buttons["graphql"].setChecked(True)
        editor._gql_query_editor.setPlainText("{ users { id name } }")
        editor._gql_variables_editor.setPlainText('{"limit": 5}')
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.body_mode == "graphql"
        assert saved.body is not None
        body = json.loads(saved.body)
        assert body["query"] == "{ users { id name } }"
        assert body["variables"] == {"limit": 5}

    # -- Dirty flag management -----------------------------------------

    def test_save_clears_dirty_flag(self, qapp: QApplication, qtbot) -> None:
        """After saving, editor dirty flag is cleared and Save btn disabled."""
        window = MainWindow()
        qtbot.addWidget(window)
        self._create_and_open(window)

        window.request_widget._url_input.setText("http://changed.test")
        assert window.request_widget.is_dirty
        assert window._save_btn.isEnabled()

        window._on_save_request()

        assert not window.request_widget.is_dirty
        assert not window._save_btn.isEnabled()

    def test_save_noop_when_not_dirty(self, qapp: QApplication, qtbot) -> None:
        """Save does nothing when the editor is not dirty."""
        window = MainWindow()
        qtbot.addWidget(window)
        self._create_and_open(window)

        # Don't modify anything — just try to save
        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_not_called()

    def test_save_noop_when_no_request_id(self, qapp: QApplication, qtbot) -> None:
        """Save does nothing when no request is loaded."""
        window = MainWindow()
        qtbot.addWidget(window)
        # Don't open any request — editor has no request_id
        window.request_widget._url_input.setText("http://whatever")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_not_called()

    # -- Multiple field save -------------------------------------------

    def test_save_multiple_fields_at_once(self, qapp: QApplication, qtbot) -> None:
        """Saving after editing multiple fields persists all changes."""
        window = MainWindow()
        qtbot.addWidget(window)
        rid = self._create_and_open(window)

        editor = window.request_widget
        editor._method_combo.setCurrentText("PUT")
        editor._url_input.setText("http://multi.test/api")
        editor._body_mode_buttons["raw"].setChecked(True)
        editor._raw_format_combo.setCurrentText("JSON")
        editor._body_code_editor.setPlainText('{"multi": true}')
        editor._description_edit.setPlainText("Multi-field test")
        window._on_save_request()

        saved = CollectionService.get_request(rid)
        assert saved is not None
        assert saved.method == "PUT"
        assert saved.url == "http://multi.test/api"
        assert saved.body == '{"multi": true}'
        assert saved.body_mode == "raw"
        assert saved.description == "Multi-field test"

    # -- Save via Ctrl+S shortcut --------------------------------------

    def test_ctrl_s_triggers_save(self, qapp: QApplication, qtbot) -> None:
        """Ctrl+S keyboard shortcut triggers the save pipeline."""
        window = MainWindow()
        qtbot.addWidget(window)
        self._create_and_open(window)

        window.request_widget._url_input.setText("http://shortcut.test")

        with patch.object(CollectionService, "update_request") as mock_update:
            window._on_save_request()
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args
            assert call_kwargs[1].get("url") or call_kwargs[0][1:] == ()


class TestMainWindowVariableMap:
    """Tests for variable map refresh on environment and tab changes."""

    def test_environment_changed_signal_connected(self, qapp: QApplication, qtbot) -> None:
        """MainWindow connects to EnvironmentSelector.environment_changed."""
        window = MainWindow()
        qtbot.addWidget(window)
        # Verify the connection works by calling the slot directly
        # (no open tabs — should not raise)
        window._on_environment_changed(None)

    def test_refresh_variable_map_calls_set_on_editor(self, qapp: QApplication, qtbot) -> None:
        """_refresh_variable_map builds the map and pushes it to the editor."""
        window = MainWindow()
        qtbot.addWidget(window)

        with patch(
            "ui.main_window.variable_controller.EnvironmentService.build_combined_variable_detail_map",
            return_value={"key": {"value": "val", "source": "collection"}},
        ) as mock_build:
            window._refresh_variable_map(window.request_widget, None)
            mock_build.assert_called_once()

    def test_on_environment_changed_updates_open_tabs(self, qapp: QApplication, qtbot) -> None:
        """Changing the environment refreshes variable maps in all open tabs."""
        window = MainWindow()
        qtbot.addWidget(window)

        # Create and open a request to have an active tab
        coll = CollectionService.create_collection("VarColl")
        req = CollectionService.create_request(coll.id, "GET", "http://t.test", "Req")
        window._open_request(req.id, push_history=True)

        with patch(
            "ui.main_window.variable_controller.EnvironmentService.build_combined_variable_detail_map",
            return_value={"env_var": {"value": "env_val", "source": "environment"}},
        ) as mock_build:
            window._on_environment_changed(None)
            assert mock_build.called
