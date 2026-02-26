"""Tests for the HTTP request service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from services.http_service import HttpService, _build_headers


class TestBuildHeaders:
    """Tests for the header parsing helper."""

    def test_empty_string(self) -> None:
        assert _build_headers("") == {}

    def test_none_input(self) -> None:
        assert _build_headers(None) == {}

    def test_single_header(self) -> None:
        result = _build_headers("Content-Type: application/json")
        assert result == {"Content-Type": "application/json"}

    def test_multiple_headers(self) -> None:
        raw = "Accept: text/html\nAuthorization: Bearer abc123"
        result = _build_headers(raw)
        assert result == {"Accept": "text/html", "Authorization": "Bearer abc123"}

    def test_malformed_line_skipped(self) -> None:
        raw = "Good: value\nbadline\nAlso-Good: ok"
        result = _build_headers(raw)
        assert result == {"Good": "value", "Also-Good": "ok"}

    def test_value_with_colon(self) -> None:
        raw = "Authorization: Bearer token:with:colons"
        result = _build_headers(raw)
        assert result == {"Authorization": "Bearer token:with:colons"}


class TestHttpServiceSendRequest:
    """Tests for HttpService.send_request with mocked httpx."""

    @patch("services.http_service.httpx.Client")
    def test_successful_get(self, mock_client_cls: MagicMock) -> None:
        """A successful GET returns status, body, headers, timing, and size."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_response.headers.multi_items.return_value = [
            ("content-type", "application/json"),
        ]
        mock_response.text = '{"ok": true}'
        mock_response.content = b'{"ok": true}'

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(method="GET", url="http://example.com")

        assert result.get("status_code") == 200
        assert result.get("status_text") == "OK"
        assert result.get("body") == '{"ok": true}'
        assert result.get("size_bytes") == 12
        assert "elapsed_ms" in result
        assert "error" not in result
        assert result.get("headers") == [{"key": "content-type", "value": "application/json"}]

    @patch("services.http_service.httpx.Client")
    def test_post_with_body_and_headers(self, mock_client_cls: MagicMock) -> None:
        """POST passes body content and parsed headers to httpx."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.reason_phrase = "Created"
        mock_response.headers.multi_items.return_value = []
        mock_response.text = ""
        mock_response.content = b""

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(
            method="POST",
            url="http://example.com/api",
            headers="Content-Type: application/json",
            body='{"name": "test"}',
        )

        assert result.get("status_code") == 201
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["content"] == b'{"name": "test"}'
        assert call_kwargs.kwargs["headers"] == {"Content-Type": "application/json"}

    @patch("services.http_service.httpx.Client")
    def test_connection_error(self, mock_client_cls: MagicMock) -> None:
        """Connection refused returns an error dict."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.ConnectError("Connection refused")
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(method="GET", url="http://localhost:9999")

        assert "error" in result
        assert "Connection refused" in result["error"]
        assert "elapsed_ms" in result

    @patch("services.http_service.httpx.Client")
    def test_timeout_error(self, mock_client_cls: MagicMock) -> None:
        """Timeout returns an error dict."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.ReadTimeout("timed out")
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(method="GET", url="http://slow.example.com")

        assert "error" in result
        assert "timed out" in result["error"]

    @patch("services.http_service.httpx.Client")
    def test_too_many_redirects(self, mock_client_cls: MagicMock) -> None:
        """Too many redirects returns an error dict."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.TooManyRedirects(
            "Exceeded max redirects", request=MagicMock()
        )
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(method="GET", url="http://loop.example.com")

        assert "error" in result
        assert "redirect" in result["error"].lower()

    @patch("services.http_service.httpx.Client")
    def test_generic_exception(self, mock_client_cls: MagicMock) -> None:
        """Unexpected errors return an error dict without crashing."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = RuntimeError("something broke")
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(method="GET", url="http://example.com")

        assert "error" in result
        assert "something broke" in result["error"]

    @patch("services.http_service.httpx.Client")
    def test_4xx_response(self, mock_client_cls: MagicMock) -> None:
        """A 404 is returned normally (not as an error)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"
        mock_response.headers.multi_items.return_value = []
        mock_response.text = "Not Found"
        mock_response.content = b"Not Found"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = HttpService.send_request(method="GET", url="http://example.com/missing")

        assert result.get("status_code") == 404
        assert "error" not in result
