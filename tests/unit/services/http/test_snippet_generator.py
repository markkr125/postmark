"""Tests for the SnippetGenerator service."""

from __future__ import annotations

from services.http.snippet_generator import SnippetGenerator, SnippetOptions


class TestSnippetGenerator:
    """Verify code snippet generation for various languages."""

    def test_available_languages(self) -> None:
        """Returns all 23 supported language variants."""
        langs = SnippetGenerator.available_languages()
        assert "cURL" in langs
        assert "Python (requests)" in langs
        assert "JavaScript (fetch)" in langs
        assert "C# (RestSharp)" in langs
        assert len(langs) == 23

    def test_curl_basic_get(self) -> None:
        """CURL snippet for a simple GET with default long-form flags."""
        result = SnippetGenerator.generate("cURL", method="GET", url="https://api.example.com")
        assert "curl" in result
        assert "--request GET" in result
        assert "https://api.example.com" in result

    def test_curl_with_headers(self) -> None:
        """CURL snippet includes header flags in long form by default."""
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "--header" in result
        assert "Content-Type: application/json" in result

    def test_curl_with_body(self) -> None:
        """CURL snippet includes -d flag for body."""
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "-d" in result

    def test_python_requests_get(self) -> None:
        """Python snippet includes requests import and method call."""
        result = SnippetGenerator.generate(
            "Python (requests)", method="GET", url="https://api.example.com"
        )
        assert "import requests" in result
        assert "requests.get" in result
        assert "https://api.example.com" in result

    def test_python_requests_with_json_body(self) -> None:
        """Python snippet uses json parameter for JSON bodies."""
        result = SnippetGenerator.generate(
            "Python (requests)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "json=payload" in result

    def test_javascript_fetch_basic(self) -> None:
        """JavaScript fetch snippet includes URL and method."""
        result = SnippetGenerator.generate(
            "JavaScript (fetch)", method="GET", url="https://api.example.com"
        )
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
        result = SnippetGenerator.generate("COBOL", method="GET", url="https://example.com")
        assert "Unsupported" in result

    def test_curl_with_bearer_auth(self) -> None:
        """CURL snippet includes Authorization header for bearer auth."""
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": "abc123"}]}
        result = SnippetGenerator.generate(
            "cURL",
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
        result = SnippetGenerator.generate(
            "Python (requests)",
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
        result = SnippetGenerator.generate(
            "cURL",
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
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        assert "api_key=secret" in result


class TestSnippetOptions:
    """Verify that SnippetOptions affect generated output."""

    def test_indent_count_affects_output(self) -> None:
        """Custom indent count changes indentation in output."""
        opts: SnippetOptions = {"indent_count": 4, "indent_type": "space"}
        result = SnippetGenerator.generate(
            "JavaScript (fetch)",
            method="GET",
            url="https://example.com",
            options=opts,
        )
        assert "    method" in result

    def test_tab_indent(self) -> None:
        """Tab indent type uses tab characters."""
        opts: SnippetOptions = {"indent_count": 1, "indent_type": "tab"}
        result = SnippetGenerator.generate(
            "JavaScript (fetch)",
            method="GET",
            url="https://example.com",
            options=opts,
        )
        assert "\tmethod" in result

    def test_trim_body(self) -> None:
        """Trim body strips whitespace from request body."""
        opts: SnippetOptions = {"trim_body": True}
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://example.com",
            body="  hello  ",
            options=opts,
        )
        assert "hello" in result
        assert "  hello  " not in result

    def test_follow_redirect_curl(self) -> None:
        """Follow redirect adds --location flag to cURL (long form default)."""
        result_on = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": True},
        )
        assert "--location" in result_on

        result_off = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "--location" not in result_off
        assert "-L" not in result_off

    def test_request_timeout_python(self) -> None:
        """Request timeout adds timeout parameter to Python requests."""
        opts: SnippetOptions = {"request_timeout": 30}
        result = SnippetGenerator.generate(
            "Python (requests)",
            method="GET",
            url="https://example.com",
            options=opts,
        )
        assert "timeout=30" in result

    def test_follow_redirect_python_requests(self) -> None:
        """Follow redirect=False adds allow_redirects=False."""
        result = SnippetGenerator.generate(
            "Python (requests)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "allow_redirects=False" in result

    def test_follow_redirect_default_python_requests(self) -> None:
        """Default follow_redirect does not add allow_redirects."""
        result = SnippetGenerator.generate(
            "Python (requests)",
            method="GET",
            url="https://example.com",
        )
        assert "allow_redirects" not in result

    def test_follow_redirect_javascript_fetch(self) -> None:
        """Disabled redirects add redirect: manual to fetch options."""
        result = SnippetGenerator.generate(
            "JavaScript (fetch)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert '"manual"' in result

    def test_get_language_info(self) -> None:
        """get_language_info returns correct metadata."""
        info = SnippetGenerator.get_language_info("cURL")
        assert info is not None
        assert info.lexer == "bash"
        assert info.display_name == "cURL"

    def test_get_language_info_unknown(self) -> None:
        """get_language_info returns None for unknown language."""
        assert SnippetGenerator.get_language_info("COBOL") is None

    def test_new_option_defaults(self) -> None:
        """New options have correct defaults in resolve_options."""
        from services.http.snippet_generator.generator import resolve_options

        opts = resolve_options(None)
        assert opts["include_boilerplate"] is True
        assert opts["async_await"] is False
        assert opts["es6_features"] is False

    def test_per_language_options_curl(self) -> None:
        """Verify cURL has follow_redirect and request_timeout in options."""
        info = SnippetGenerator.get_language_info("cURL")
        assert info is not None
        assert "follow_redirect" in info.applicable_options
        assert "request_timeout" in info.applicable_options

    def test_per_language_options_httpie(self) -> None:
        """HTTPie has no indent options but has timeout and redirect."""
        info = SnippetGenerator.get_language_info("Shell (HTTPie)")
        assert info is not None
        assert "indent_count" not in info.applicable_options
        assert "request_timeout" in info.applicable_options
        assert "follow_redirect" in info.applicable_options

    def test_per_language_options_powershell(self) -> None:
        """PowerShell has no indent options but has timeout and redirect."""
        info = SnippetGenerator.get_language_info("PowerShell (RestMethod)")
        assert info is not None
        assert "indent_count" not in info.applicable_options
        assert "request_timeout" in info.applicable_options
        assert "follow_redirect" in info.applicable_options

    def test_new_curl_option_defaults(self) -> None:
        """New cURL-specific options have correct defaults."""
        from services.http.snippet_generator.generator import resolve_options

        opts = resolve_options(None)
        assert opts["multiline"] is True
        assert opts["long_form"] is True
        assert opts["line_continuation"] == "\\\\"
        assert opts["quote_type"] == "single"
        assert opts["follow_original_method"] is False
        assert opts["silent_mode"] is False

    def test_async_await_javascript_fetch(self) -> None:
        """Async/await option wraps fetch in async function with await."""
        result = SnippetGenerator.generate(
            "JavaScript (fetch)",
            method="GET",
            url="https://example.com",
            options={"async_await": True},
        )
        assert "async " in result
        assert "await fetch" in result

    def test_async_await_default_fetch(self) -> None:
        """Default fetch uses .then() chain, not async/await."""
        result = SnippetGenerator.generate(
            "JavaScript (fetch)",
            method="GET",
            url="https://example.com",
        )
        assert ".then(" in result
        assert "async " not in result

    def test_xhr_no_follow_redirect_option(self) -> None:
        """XHR does not include follow_redirect in applicable options."""
        info = SnippetGenerator.get_language_info("JavaScript (XHR)")
        assert info is not None
        assert "follow_redirect" not in info.applicable_options

    def test_fetch_has_async_await_option(self) -> None:
        """JavaScript Fetch includes async_await in applicable options."""
        info = SnippetGenerator.get_language_info("JavaScript (fetch)")
        assert info is not None
        assert "async_await" in info.applicable_options

    def test_dart_has_include_boilerplate_option(self) -> None:
        """Dart http includes include_boilerplate in applicable options."""
        info = SnippetGenerator.get_language_info("Dart (http)")
        assert info is not None
        assert "include_boilerplate" in info.applicable_options

    def test_java_has_include_boilerplate_option(self) -> None:
        """Java OkHttp includes include_boilerplate in applicable options."""
        info = SnippetGenerator.get_language_info("Java (OkHttp)")
        assert info is not None
        assert "include_boilerplate" in info.applicable_options

    def test_kotlin_has_include_boilerplate_option(self) -> None:
        """Kotlin OkHttp includes include_boilerplate in applicable options."""
        info = SnippetGenerator.get_language_info("Kotlin (OkHttp)")
        assert info is not None
        assert "include_boilerplate" in info.applicable_options

    def test_csharp_restsharp_has_include_boilerplate(self) -> None:
        """C# RestSharp includes include_boilerplate in applicable options."""
        info = SnippetGenerator.get_language_info("C# (RestSharp)")
        assert info is not None
        assert "include_boilerplate" in info.applicable_options

    def test_per_language_options_http_raw(self) -> None:
        """HTTP raw only has trim_body."""
        info = SnippetGenerator.get_language_info("HTTP")
        assert info is not None
        assert info.applicable_options == ("trim_body",)

    def test_per_language_options_axios_has_async(self) -> None:
        """NodeJS Axios has async_await in its options."""
        info = SnippetGenerator.get_language_info("NodeJS (Axios)")
        assert info is not None
        assert "async_await" in info.applicable_options

    def test_per_language_options_nodejs_native_has_es6(self) -> None:
        """NodeJS Native has es6_features in its options."""
        info = SnippetGenerator.get_language_info("NodeJS (Native)")
        assert info is not None
        assert "es6_features" in info.applicable_options

    def test_per_language_options_c_has_boilerplate(self) -> None:
        """C (libcurl) has include_boilerplate in its options."""
        info = SnippetGenerator.get_language_info("C (libcurl)")
        assert info is not None
        assert "include_boilerplate" in info.applicable_options

    def test_per_language_options_swift_has_boilerplate(self) -> None:
        """Swift (URLSession) has include_boilerplate but not follow_redirect."""
        info = SnippetGenerator.get_language_info("Swift (URLSession)")
        assert info is not None
        assert "include_boilerplate" in info.applicable_options
        assert "follow_redirect" not in info.applicable_options

    def test_per_language_options_python_http_client_no_redirect(self) -> None:
        """Python http.client does not have follow_redirect."""
        info = SnippetGenerator.get_language_info("Python (http.client)")
        assert info is not None
        assert "follow_redirect" not in info.applicable_options
