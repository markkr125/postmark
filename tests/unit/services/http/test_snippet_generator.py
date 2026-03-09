"""Tests for the SnippetGenerator service."""

from __future__ import annotations

from services.http.snippet_generator import SnippetGenerator


class TestSnippetGenerator:
    """Verify code snippet generation for various languages."""

    def test_available_languages(self) -> None:
        """Returns at least cURL, Python, and JavaScript."""
        langs = SnippetGenerator.available_languages()
        assert "cURL" in langs
        assert "Python (requests)" in langs
        assert "JavaScript (fetch)" in langs

    def test_curl_basic_get(self) -> None:
        """CURL snippet for a simple GET."""
        result = SnippetGenerator.curl(method="GET", url="https://api.example.com")
        assert "curl" in result
        assert "-X" in result
        assert "GET" in result
        assert "https://api.example.com" in result

    def test_curl_with_headers(self) -> None:
        """CURL snippet includes header flags."""
        result = SnippetGenerator.curl(
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "-H" in result
        assert "Content-Type: application/json" in result

    def test_curl_with_body(self) -> None:
        """CURL snippet includes -d flag for body."""
        result = SnippetGenerator.curl(
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "-d" in result

    def test_python_requests_get(self) -> None:
        """Python snippet includes requests import and method call."""
        result = SnippetGenerator.python_requests(method="GET", url="https://api.example.com")
        assert "import requests" in result
        assert "requests.get" in result
        assert "https://api.example.com" in result

    def test_python_requests_with_json_body(self) -> None:
        """Python snippet uses json parameter for JSON bodies."""
        result = SnippetGenerator.python_requests(
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "json=payload" in result

    def test_javascript_fetch_basic(self) -> None:
        """JavaScript fetch snippet includes URL and method."""
        result = SnippetGenerator.javascript_fetch(method="GET", url="https://api.example.com")
        assert "fetch(" in result
        assert "https://api.example.com" in result
        assert '"GET"' in result

    def test_generate_dispatches_correctly(self) -> None:
        """generate() dispatches to the right language method."""
        curl = SnippetGenerator.generate("cURL", method="GET", url="https://example.com")
        assert "curl" in curl

        python = SnippetGenerator.generate(
            "Python (requests)", method="GET", url="https://example.com"
        )
        assert "import requests" in python

        js = SnippetGenerator.generate(
            "JavaScript (fetch)", method="GET", url="https://example.com"
        )
        assert "fetch(" in js

    def test_generate_unknown_language(self) -> None:
        """Unknown language returns an unsupported message."""
        result = SnippetGenerator.generate("Ruby", method="GET", url="https://example.com")
        assert "Unsupported" in result

    def test_curl_with_bearer_auth(self) -> None:
        """CURL snippet includes Authorization header for bearer auth."""
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": "abc123"}]}
        result = SnippetGenerator.curl(
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        assert "Authorization: Bearer abc123" in result

    def test_python_with_basic_auth(self) -> None:
        """Python snippet includes Authorization header for basic auth."""
        auth = {
            "type": "basic",
            "basic": [
                {"key": "username", "value": "user"},
                {"key": "password", "value": "pass"},
            ],
        }
        result = SnippetGenerator.python_requests(
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        assert "Authorization" in result
        assert "Basic" in result

    def test_curl_with_apikey_header(self) -> None:
        """CURL snippet includes custom API key header."""
        auth = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "X-API-Key"},
                {"key": "value", "value": "secret"},
                {"key": "in", "value": "header"},
            ],
        }
        result = SnippetGenerator.curl(
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        assert "X-API-Key: secret" in result

    def test_curl_with_apikey_query(self) -> None:
        """CURL snippet appends API key to URL for query param auth."""
        auth = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "api_key"},
                {"key": "value", "value": "secret"},
                {"key": "in", "value": "query"},
            ],
        }
        result = SnippetGenerator.curl(
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        assert "api_key=secret" in result
