"""Tests for dynamic / interpreted language snippet generators."""

from __future__ import annotations

from services.http.snippet_generator import SnippetGenerator


class TestPythonHttpClient:
    """Verify Python http.client snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes http.client import and connection."""
        result = SnippetGenerator.generate(
            "Python (http.client)", method="GET", url="https://api.example.com/users"
        )
        assert "import http.client" in result
        assert "HTTPSConnection" in result
        assert "api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet includes headers dict."""
        result = SnippetGenerator.generate(
            "Python (http.client)",
            method="POST",
            url="https://api.example.com/data",
            headers="Content-Type: application/json",
        )
        assert "Content-Type" in result
        assert "headers" in result

    def test_with_body(self) -> None:
        """Snippet passes body to conn.request."""
        result = SnippetGenerator.generate(
            "Python (http.client)",
            method="POST",
            url="https://api.example.com/data",
            body='{"key": "value"}',
        )
        assert '{"key": "value"}' in result

    def test_timeout_option(self) -> None:
        """Timeout option adds timeout parameter."""
        result = SnippetGenerator.generate(
            "Python (http.client)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 10},
        )
        assert "timeout=10" in result


class TestNodejsAxios:
    """Verify Node.js Axios snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes axios require and method."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)", method="GET", url="https://api.example.com"
        )
        assert "axios" in result
        assert '"get"' in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet includes headers in config."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "headers" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet includes data in config."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "data:" in result

    def test_timeout_option(self) -> None:
        """Timeout option adds timeout to config."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 5},
        )
        assert "timeout: 5000" in result

    def test_no_redirect(self) -> None:
        """Redirects disabled adds maxRedirects: 0 to config."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "maxRedirects: 0" in result

    def test_async_await(self) -> None:
        """Async/await option generates async function syntax."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)",
            method="GET",
            url="https://example.com",
            options={"async_await": True},
        )
        assert "async function" in result
        assert "await axios" in result
        assert ".then(" not in result

    def test_default_uses_then(self) -> None:
        """Default mode uses .then() promise chains."""
        result = SnippetGenerator.generate(
            "NodeJS (Axios)",
            method="GET",
            url="https://example.com",
        )
        assert ".then(" in result
        assert "async function" not in result


class TestNodejsNative:
    """Verify Node.js native http/https snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes https require and request options."""
        result = SnippetGenerator.generate(
            "NodeJS (Native)", method="GET", url="https://api.example.com/users"
        )
        assert 'require("https")' in result
        assert '"GET"' in result
        assert "api.example.com" in result

    def test_http_url(self) -> None:
        """HTTP URLs use the http module."""
        result = SnippetGenerator.generate(
            "NodeJS (Native)", method="GET", url="http://localhost:3000/api"
        )
        assert 'require("http")' in result

    def test_with_body(self) -> None:
        """Snippet uses req.write for body."""
        result = SnippetGenerator.generate(
            "NodeJS (Native)",
            method="POST",
            url="https://api.example.com/data",
            body='{"key": "value"}',
        )
        assert "req.write" in result

    def test_with_headers(self) -> None:
        """Snippet includes headers in options."""
        result = SnippetGenerator.generate(
            "NodeJS (Native)",
            method="POST",
            url="https://api.example.com/data",
            headers="Content-Type: application/json",
        )
        assert "headers" in result
        assert "Content-Type" in result

    def test_es6_features(self) -> None:
        """ES6 features option uses import instead of require."""
        result = SnippetGenerator.generate(
            "NodeJS (Native)",
            method="GET",
            url="https://api.example.com",
            options={"es6_features": True},
        )
        assert "import https" in result
        assert "require(" not in result

    def test_default_uses_require(self) -> None:
        """Default mode uses require() syntax."""
        result = SnippetGenerator.generate(
            "NodeJS (Native)",
            method="GET",
            url="https://api.example.com",
        )
        assert 'require("https")' in result
        assert "import " not in result


class TestJavascriptXhr:
    """Verify JavaScript XMLHttpRequest snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes XMLHttpRequest open and send."""
        result = SnippetGenerator.generate(
            "JavaScript (XHR)", method="GET", url="https://api.example.com"
        )
        assert "XMLHttpRequest" in result
        assert "xhr.open" in result
        assert '"GET"' in result
        assert "xhr.send()" in result

    def test_with_headers(self) -> None:
        """Snippet sets request headers."""
        result = SnippetGenerator.generate(
            "JavaScript (XHR)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "setRequestHeader" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet passes body to xhr.send."""
        result = SnippetGenerator.generate(
            "JavaScript (XHR)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "xhr.send(" in result
        assert "key" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets xhr.timeout."""
        result = SnippetGenerator.generate(
            "JavaScript (XHR)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 10},
        )
        assert "xhr.timeout = 10000" in result


class TestRubyNethttp:
    """Verify Ruby Net::HTTP snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes Net::HTTP and URI.parse."""
        result = SnippetGenerator.generate(
            "Ruby (Net::HTTP)", method="GET", url="https://api.example.com"
        )
        assert "net/http" in result
        assert "URI.parse" in result
        assert "Net::HTTP::Get" in result

    def test_https(self) -> None:
        """HTTPS URLs enable SSL."""
        result = SnippetGenerator.generate(
            "Ruby (Net::HTTP)", method="GET", url="https://secure.example.com"
        )
        assert "use_ssl = true" in result

    def test_with_body(self) -> None:
        """Snippet sets request body."""
        result = SnippetGenerator.generate(
            "Ruby (Net::HTTP)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "request.body" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets read_timeout."""
        result = SnippetGenerator.generate(
            "Ruby (Net::HTTP)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 15},
        )
        assert "read_timeout = 15" in result

    def test_no_redirect(self) -> None:
        """Redirects disabled sets max_retries = 0."""
        result = SnippetGenerator.generate(
            "Ruby (Net::HTTP)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "max_retries = 0" in result


class TestPhpCurl:
    """Verify PHP cURL snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes curl_init and URL."""
        result = SnippetGenerator.generate(
            "PHP (cURL)", method="GET", url="https://api.example.com"
        )
        assert "curl_init" in result
        assert "https://api.example.com" in result
        assert "curl_exec" in result

    def test_with_headers(self) -> None:
        """Snippet includes CURLOPT_HTTPHEADER."""
        result = SnippetGenerator.generate(
            "PHP (cURL)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "CURLOPT_HTTPHEADER" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet includes CURLOPT_POSTFIELDS."""
        result = SnippetGenerator.generate(
            "PHP (cURL)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "CURLOPT_POSTFIELDS" in result

    def test_timeout_option(self) -> None:
        """Timeout option adds CURLOPT_TIMEOUT."""
        result = SnippetGenerator.generate(
            "PHP (cURL)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 30},
        )
        assert "CURLOPT_TIMEOUT" in result

    def test_follow_redirect(self) -> None:
        """Follow redirects adds CURLOPT_FOLLOWLOCATION."""
        result = SnippetGenerator.generate(
            "PHP (cURL)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": True},
        )
        assert "CURLOPT_FOLLOWLOCATION" in result

    def test_no_redirect(self) -> None:
        """Redirects disabled omits CURLOPT_FOLLOWLOCATION."""
        result = SnippetGenerator.generate(
            "PHP (cURL)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "CURLOPT_FOLLOWLOCATION" not in result


class TestPhpGuzzle:
    """Verify PHP Guzzle snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes GuzzleHttp Client."""
        result = SnippetGenerator.generate(
            "PHP (Guzzle)", method="GET", url="https://api.example.com"
        )
        assert "GuzzleHttp" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet includes headers option."""
        result = SnippetGenerator.generate(
            "PHP (Guzzle)",
            method="POST",
            url="https://api.example.com",
            headers="Accept: application/json",
        )
        assert "'headers'" in result
        assert "Accept" in result

    def test_with_json_body(self) -> None:
        """Snippet uses json option for JSON body."""
        result = SnippetGenerator.generate(
            "PHP (Guzzle)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "'json'" in result

    def test_timeout_option(self) -> None:
        """Timeout option adds timeout to request options."""
        result = SnippetGenerator.generate(
            "PHP (Guzzle)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 20},
        )
        assert "'timeout' => 20" in result

    def test_no_redirect(self) -> None:
        """Redirects disabled adds allow_redirects => false."""
        result = SnippetGenerator.generate(
            "PHP (Guzzle)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "'allow_redirects' => false" in result


class TestDartHttp:
    """Verify Dart http snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes http import and Uri.parse."""
        result = SnippetGenerator.generate(
            "Dart (http)", method="GET", url="https://api.example.com"
        )
        assert "http" in result
        assert "Uri.parse" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet includes headers map."""
        result = SnippetGenerator.generate(
            "Dart (http)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "headers" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet includes body parameter for POST."""
        result = SnippetGenerator.generate(
            "Dart (http)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "body:" in result

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits import directive."""
        result = SnippetGenerator.generate(
            "Dart (http)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "import " not in result
        assert "http.get" in result

    def test_boilerplate_default(self) -> None:
        """Default includes package:http import."""
        result = SnippetGenerator.generate(
            "Dart (http)",
            method="GET",
            url="https://example.com",
        )
        assert "import " in result
        assert "package:http" in result
