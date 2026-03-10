"""Tests for RequestEditorWidget — auth tab and apply-auth logic."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.request_editor import RequestEditorWidget


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
        assert "Inherit auth from parent" in items
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

    def test_get_auth_data_inherit(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns None when Inherit auth is selected."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        data = editor.get_request_data()
        assert data["auth"] is None

    def test_get_auth_data_no_auth(self, qapp: QApplication, qtbot) -> None:
        """get_request_data returns noauth when No Auth is selected."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x"})
        editor._auth_type_combo.setCurrentText("No Auth")
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
        assert editor._auth_type_combo.currentText() == "Inherit auth from parent"
        assert editor._bearer_token_input.text() == ""

    def test_load_inherit_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading with auth=None selects Inherit auth from parent."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request({"name": "X", "method": "GET", "url": "http://x", "auth": None})
        assert editor._auth_type_combo.currentText() == "Inherit auth from parent"

    def test_load_noauth_selects_no_auth(self, qapp: QApplication, qtbot) -> None:
        """Loading with explicit noauth selects No Auth."""
        editor = RequestEditorWidget()
        qtbot.addWidget(editor)

        editor.load_request(
            {
                "name": "X",
                "method": "GET",
                "url": "http://x",
                "auth": {"type": "noauth"},
            }
        )
        assert editor._auth_type_combo.currentText() == "No Auth"


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
