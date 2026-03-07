"""Tests for the HTTP request service."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import httpx

from services.http.http_service import HttpService, _build_headers, _phase_ms


class TestBuildHeaders:
    """Tests for the header parsing helper."""

    def test_empty_string(self) -> None:
        """Empty string yields an empty dict."""
        assert _build_headers("") == {}

    def test_none_input(self) -> None:
        """None input yields an empty dict."""
        assert _build_headers(None) == {}

    def test_single_header(self) -> None:
        """Single well-formed header is parsed correctly."""
        result = _build_headers("Content-Type: application/json")
        assert result == {"Content-Type": "application/json"}

    def test_multiple_headers(self) -> None:
        """Multiple newline-separated headers are all parsed."""
        raw = "Accept: text/html\nAuthorization: Bearer abc123"
        result = _build_headers(raw)
        assert result == {"Accept": "text/html", "Authorization": "Bearer abc123"}

    def test_malformed_line_skipped(self) -> None:
        """Lines without a colon are silently skipped."""
        raw = "Good: value\nbadline\nAlso-Good: ok"
        result = _build_headers(raw)
        assert result == {"Good": "value", "Also-Good": "ok"}

    def test_value_with_colon(self) -> None:
        """Only the first colon splits key from value."""
        raw = "Authorization: Bearer token:with:colons"
        result = _build_headers(raw)
        assert result == {"Authorization": "Bearer token:with:colons"}


class TestPhaseMs:
    """Tests for the _phase_ms trace-timing helper."""

    def test_matching_pair(self) -> None:
        """Returns duration when start/complete pair exists."""
        times = {"a.started": 1.0, "a.complete": 1.05}
        assert abs(_phase_ms(times, "a") - 50.0) < 0.01

    def test_no_matching_pair(self) -> None:
        """Returns 0 when no matching start/complete pair is found."""
        assert _phase_ms({}, "a") == 0.0

    def test_multiple_prefixes_first_wins(self) -> None:
        """The first prefix with a matching pair is used."""
        times = {"b.started": 2.0, "b.complete": 2.1}
        result = _phase_ms(times, "a", "b")
        assert abs(result - 100.0) < 0.01

    def test_negative_clamped_to_zero(self) -> None:
        """Negative durations are clamped to 0.0."""
        times = {"a.started": 5.0, "a.complete": 4.0}
        assert _phase_ms(times, "a") == 0.0


class TestResolveDns:
    """Tests for HttpService._resolve_dns."""

    @patch("services.http.http_service.socket.getaddrinfo")
    def test_successful_resolve(self, mock_gai: MagicMock) -> None:
        """Successful DNS resolution returns positive ms and IP."""
        mock_gai.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
        ]
        dns_ms, ip = HttpService._resolve_dns("example.com", 80)
        assert dns_ms >= 0.0
        assert ip == "93.184.216.34"

    @patch("services.http.http_service.socket.getaddrinfo")
    def test_resolution_failure(self, mock_gai: MagicMock) -> None:
        """DNS failure returns (0.0, '') so httpx can try its own."""
        mock_gai.side_effect = socket.gaierror("Name or service not known")
        dns_ms, ip = HttpService._resolve_dns("nonexistent.invalid", 80)
        assert dns_ms == 0.0
        assert ip == ""


class TestExtractCertField:
    """Tests for HttpService._extract_cert_field."""

    def test_subject_common_name(self) -> None:
        """Extracts commonName from the subject tuple-of-tuples."""
        cert = {"subject": ((("commonName", "example.com"),),)}
        assert HttpService._extract_cert_field(cert, "subject") == "example.com"

    def test_missing_field(self) -> None:
        """Returns None when the field key is absent."""
        assert HttpService._extract_cert_field({}, "subject") is None

    def test_no_common_name_in_rdn(self) -> None:
        """Returns None when commonName is not among the RDN entries."""
        cert = {"subject": ((("organizationName", "Acme"),),)}
        assert HttpService._extract_cert_field(cert, "subject") is None


def _mock_response(
    status_code: int = 200,
    reason_phrase: str = "OK",
    headers_list: list[tuple[str, str]] | None = None,
    text: str = '{"ok": true}',
    content: bytes = b'{"ok": true}',
    http_version: str = "HTTP/1.1",
    content_encoding: str = "",
) -> MagicMock:
    """Build a mock httpx.Response with the given attributes."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason_phrase = reason_phrase
    resp.headers.multi_items.return_value = headers_list or [
        ("content-type", "application/json"),
    ]
    # raw headers for size computation
    resp.headers.raw = [
        (k.encode(), v.encode())
        for k, v in (headers_list or [("content-type", "application/json")])
    ]
    resp.headers.get.side_effect = (
        lambda key, default="": content_encoding if key == "content-encoding" else default
    )
    resp.text = text
    resp.content = content
    resp.http_version = http_version
    return resp


def _mock_client(response: MagicMock) -> MagicMock:
    """Wrap a mock response in a context-manager mock client."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.request.return_value = response
    return client


class TestHttpServiceSendRequest:
    """Tests for HttpService.send_request with mocked httpx and DNS."""

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(1.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_successful_get(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """A successful GET returns status, body, headers, timing, and size."""
        resp = _mock_response()
        mock_client_cls.return_value = _mock_client(resp)

        result = HttpService.send_request(method="GET", url="http://example.com")

        assert result.get("status_code") == 200
        assert result.get("status_text") == "OK"
        assert result.get("body") == '{"ok": true}'
        assert result.get("size_bytes") == 12
        assert "elapsed_ms" in result
        assert "error" not in result
        assert result.get("headers") == [{"key": "content-type", "value": "application/json"}]

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(0.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_response_has_timing(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """Successful response includes a timing breakdown dict."""
        mock_client_cls.return_value = _mock_client(_mock_response())

        result = HttpService.send_request(method="GET", url="http://example.com")

        timing = result.get("timing")
        assert timing is not None
        assert "dns_ms" in timing
        assert "tcp_ms" in timing
        assert "tls_ms" in timing
        assert "ttfb_ms" in timing
        assert "download_ms" in timing
        assert "process_ms" in timing

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(0.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_response_has_size_breakdown(
        self, mock_client_cls: MagicMock, _mock_dns: MagicMock
    ) -> None:
        """Successful response includes request/response size breakdown."""
        mock_client_cls.return_value = _mock_client(_mock_response())

        result = HttpService.send_request(
            method="POST",
            url="http://example.com",
            headers="Content-Type: application/json",
            body='{"a": 1}',
        )

        assert "request_headers_size" in result
        assert "request_body_size" in result
        assert result["request_body_size"] == len(b'{"a": 1}')
        assert "response_headers_size" in result

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(0.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_response_has_network_metadata(
        self, mock_client_cls: MagicMock, _mock_dns: MagicMock
    ) -> None:
        """Successful response includes network metadata dict."""
        mock_client_cls.return_value = _mock_client(_mock_response())

        result = HttpService.send_request(method="GET", url="http://example.com")

        network = result.get("network")
        assert network is not None
        assert "http_version" in network
        assert "remote_address" in network

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(0.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_post_with_body_and_headers(
        self, mock_client_cls: MagicMock, _mock_dns: MagicMock
    ) -> None:
        """POST passes body content and parsed headers to httpx."""
        resp = _mock_response(
            status_code=201, reason_phrase="Created", headers_list=[], text="", content=b""
        )
        mock_client_cls.return_value = _mock_client(resp)

        result = HttpService.send_request(
            method="POST",
            url="http://example.com/api",
            headers="Content-Type: application/json",
            body='{"name": "test"}',
        )

        assert result.get("status_code") == 201
        client = mock_client_cls.return_value
        client.request.assert_called_once()
        call_kwargs = client.request.call_args
        assert call_kwargs.kwargs["content"] == b'{"name": "test"}'
        assert call_kwargs.kwargs["headers"] == {"Content-Type": "application/json"}

    @patch("services.http.http_service.HttpService._resolve_dns", return_value=(0.0, ""))
    @patch("services.http.http_service.httpx.Client")
    def test_connection_error(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """Connection refused returns an error dict."""
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.request.side_effect = httpx.ConnectError("Connection refused")
        mock_client_cls.return_value = client

        result = HttpService.send_request(method="GET", url="http://localhost:9999")

        assert "error" in result
        assert "Connection refused" in result["error"]
        assert "elapsed_ms" in result

    @patch("services.http.http_service.HttpService._resolve_dns", return_value=(0.0, ""))
    @patch("services.http.http_service.httpx.Client")
    def test_timeout_error(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """Timeout returns an error dict."""
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.request.side_effect = httpx.ReadTimeout("timed out")
        mock_client_cls.return_value = client

        result = HttpService.send_request(method="GET", url="http://slow.example.com")

        assert "error" in result
        assert "timed out" in result["error"]

    @patch("services.http.http_service.HttpService._resolve_dns", return_value=(0.0, ""))
    @patch("services.http.http_service.httpx.Client")
    def test_too_many_redirects(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """Too many redirects returns an error dict."""
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.request.side_effect = httpx.TooManyRedirects(
            "Exceeded max redirects", request=MagicMock()
        )
        mock_client_cls.return_value = client

        result = HttpService.send_request(method="GET", url="http://loop.example.com")

        assert "error" in result
        assert "redirect" in result["error"].lower()

    @patch("services.http.http_service.HttpService._resolve_dns", return_value=(0.0, ""))
    @patch("services.http.http_service.httpx.Client")
    def test_generic_exception(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """Unexpected errors return an error dict without crashing."""
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.request.side_effect = RuntimeError("something broke")
        mock_client_cls.return_value = client

        result = HttpService.send_request(method="GET", url="http://example.com")

        assert "error" in result
        assert "something broke" in result["error"]

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(0.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_4xx_response(self, mock_client_cls: MagicMock, _mock_dns: MagicMock) -> None:
        """A 404 is returned normally (not as an error)."""
        resp = _mock_response(
            status_code=404,
            reason_phrase="Not Found",
            headers_list=[],
            text="Not Found",
            content=b"Not Found",
        )
        mock_client_cls.return_value = _mock_client(resp)

        result = HttpService.send_request(method="GET", url="http://example.com/missing")

        assert result.get("status_code") == 404
        assert "error" not in result

    @patch(
        "services.http.http_service.HttpService._resolve_dns", return_value=(0.5, "93.184.216.34")
    )
    @patch("services.http.http_service.httpx.Client")
    def test_compressed_response_has_uncompressed_size(
        self, mock_client_cls: MagicMock, _mock_dns: MagicMock
    ) -> None:
        """Gzip responses include response_uncompressed_size."""
        resp = _mock_response(content_encoding="gzip")
        mock_client_cls.return_value = _mock_client(resp)

        result = HttpService.send_request(method="GET", url="http://example.com")

        assert "response_uncompressed_size" in result
