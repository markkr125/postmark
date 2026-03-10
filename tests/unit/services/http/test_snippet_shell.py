"""Tests for shell and CLI snippet generators."""

from __future__ import annotations

from services.http.snippet_generator import SnippetGenerator


class TestCurlOptions:
    """Verify new cURL-specific options."""

    def test_short_form_flags(self) -> None:
        """Long form disabled uses -X, -H, -d, -L short flags."""
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://example.com",
            headers="Accept: application/json",
            body='{"k": "v"}',
            options={"long_form": False, "follow_redirect": True},
        )
        assert "-X POST" in result
        assert "-H " in result
        assert "-d " in result
        assert "-L" in result
        assert "--request" not in result
        assert "--header" not in result

    def test_long_form_flags(self) -> None:
        """Default long form uses --request, --header, --data, --location."""
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://example.com",
            headers="Accept: application/json",
            body='{"k": "v"}',
            options={"long_form": True, "follow_redirect": True},
        )
        assert "--request POST" in result
        assert "--header " in result
        assert "--data " in result
        assert "--location" in result

    def test_multiline_false_single_line(self) -> None:
        """Multiline disabled produces a single-line command."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            headers="Accept: text/html",
            options={"multiline": False},
        )
        assert "\n" not in result
        assert "curl " in result

    def test_multiline_true_uses_continuation(self) -> None:
        """Multiline default splits across lines with continuation char."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            headers="Accept: text/html",
            options={"multiline": True},
        )
        assert "\\\n" in result

    def test_line_continuation_caret(self) -> None:
        """Caret continuation character for Windows CMD."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            headers="Accept: text/html",
            options={"multiline": True, "line_continuation": "^"},
        )
        assert "^\n" in result
        assert "\\\n" not in result

    def test_line_continuation_backtick(self) -> None:
        """Backtick continuation character for PowerShell."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            headers="Accept: text/html",
            options={"multiline": True, "line_continuation": "`"},
        )
        assert "`\n" in result

    def test_quote_type_double(self) -> None:
        """Double quote type wraps URL in double quotes."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"quote_type": "double"},
        )
        assert '"https://example.com"' in result

    def test_quote_type_single(self) -> None:
        """Single quote type wraps URL in single quotes."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"quote_type": "single"},
        )
        assert "'https://example.com'" in result

    def test_follow_original_method(self) -> None:
        """Follow original method adds --post301/302/303 flags."""
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://example.com",
            options={"follow_original_method": True},
        )
        assert "--post301" in result
        assert "--post302" in result
        assert "--post303" in result

    def test_follow_original_method_off(self) -> None:
        """Follow original method disabled omits --post30x flags."""
        result = SnippetGenerator.generate(
            "cURL",
            method="POST",
            url="https://example.com",
            options={"follow_original_method": False},
        )
        assert "--post301" not in result

    def test_silent_mode_long_form(self) -> None:
        """Silent mode adds --silent when long form enabled."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"silent_mode": True, "long_form": True},
        )
        assert "--silent" in result

    def test_silent_mode_short_form(self) -> None:
        """Silent mode adds -s when long form disabled."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"silent_mode": True, "long_form": False},
        )
        assert "-s" in result
        assert "--silent" not in result

    def test_silent_mode_off(self) -> None:
        """Silent mode disabled omits silent flag."""
        result = SnippetGenerator.generate(
            "cURL",
            method="GET",
            url="https://example.com",
            options={"silent_mode": False},
        )
        assert "--silent" not in result
        assert "-s " not in result

    def test_curl_applicable_options(self) -> None:
        """Verify cURL has the 6 new options plus trim_body, timeout, redirect."""
        info = SnippetGenerator.get_language_info("cURL")
        assert info is not None
        for opt in (
            "multiline",
            "long_form",
            "line_continuation",
            "quote_type",
            "follow_original_method",
            "silent_mode",
            "trim_body",
            "request_timeout",
            "follow_redirect",
        ):
            assert opt in info.applicable_options
        # cURL does NOT have indent options
        assert "indent_count" not in info.applicable_options
        assert "indent_type" not in info.applicable_options


class TestHttpRaw:
    """Verify raw HTTP snippet generation."""

    def test_basic_get(self) -> None:
        """Raw HTTP snippet contains method, path, and host."""
        result = SnippetGenerator.generate(
            "HTTP", method="GET", url="https://api.example.com/users"
        )
        assert "GET /users HTTP/1.1" in result
        assert "Host: api.example.com" in result

    def test_with_headers(self) -> None:
        """Raw HTTP snippet includes request headers."""
        result = SnippetGenerator.generate(
            "HTTP",
            method="POST",
            url="https://api.example.com/data",
            headers="Content-Type: application/json",
        )
        assert "Content-Type: application/json" in result

    def test_with_body(self) -> None:
        """Raw HTTP snippet includes body after blank line."""
        result = SnippetGenerator.generate(
            "HTTP",
            method="POST",
            url="https://api.example.com/data",
            body='{"key": "value"}',
        )
        assert '{"key": "value"}' in result
        assert "Content-Length:" in result

    def test_with_query_string(self) -> None:
        """Raw HTTP snippet preserves query string in path."""
        result = SnippetGenerator.generate(
            "HTTP", method="GET", url="https://api.example.com/search?q=test"
        )
        assert "GET /search?q=test HTTP/1.1" in result


class TestShellWget:
    """Verify wget snippet generation."""

    def test_basic_get(self) -> None:
        """Wget snippet includes method and URL."""
        result = SnippetGenerator.generate(
            "Shell (wget)", method="GET", url="https://api.example.com"
        )
        assert "wget" in result
        assert "--method=GET" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Wget snippet includes --header flags."""
        result = SnippetGenerator.generate(
            "Shell (wget)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "--header=" in result
        assert "Content-Type: application/json" in result

    def test_with_body(self) -> None:
        """Wget snippet includes --body-data flag."""
        result = SnippetGenerator.generate(
            "Shell (wget)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "--body-data=" in result

    def test_no_redirect(self) -> None:
        """Wget snippet includes --max-redirect=0 when redirects disabled."""
        result = SnippetGenerator.generate(
            "Shell (wget)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "--max-redirect=0" in result

    def test_timeout_option(self) -> None:
        """Timeout option adds --timeout flag."""
        result = SnippetGenerator.generate(
            "Shell (wget)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 30},
        )
        assert "--timeout=30" in result


class TestShellHttpie:
    """Verify HTTPie snippet generation."""

    def test_basic_get(self) -> None:
        """HTTPie snippet includes http, method, and URL."""
        result = SnippetGenerator.generate(
            "Shell (HTTPie)", method="GET", url="https://api.example.com"
        )
        assert "http" in result
        assert "GET" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """HTTPie snippet includes header key:value pairs."""
        result = SnippetGenerator.generate(
            "Shell (HTTPie)",
            method="POST",
            url="https://api.example.com",
            headers="Accept: application/json",
        )
        assert "Accept" in result

    def test_no_redirect(self) -> None:
        """HTTPie snippet includes --follow=false when redirects disabled."""
        result = SnippetGenerator.generate(
            "Shell (HTTPie)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "--follow=false" in result

    def test_timeout_option(self) -> None:
        """Timeout option adds --timeout flag."""
        result = SnippetGenerator.generate(
            "Shell (HTTPie)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 15},
        )
        assert "--timeout=15" in result


class TestPowershellRestmethod:
    """Verify PowerShell Invoke-RestMethod snippet generation."""

    def test_basic_get(self) -> None:
        """PowerShell snippet includes Invoke-RestMethod and URL."""
        result = SnippetGenerator.generate(
            "PowerShell (RestMethod)", method="GET", url="https://api.example.com"
        )
        assert "Invoke-RestMethod" in result
        assert "https://api.example.com" in result
        assert "-Method GET" in result

    def test_with_headers(self) -> None:
        """PowerShell snippet includes $headers hashtable."""
        result = SnippetGenerator.generate(
            "PowerShell (RestMethod)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "$headers" in result
        assert "-Headers $headers" in result

    def test_with_body(self) -> None:
        """PowerShell snippet includes $body variable."""
        result = SnippetGenerator.generate(
            "PowerShell (RestMethod)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "$body" in result
        assert "-Body $body" in result

    def test_with_auth(self) -> None:
        """PowerShell snippet includes auth header."""
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": "tok"}]}
        result = SnippetGenerator.generate(
            "PowerShell (RestMethod)",
            method="GET",
            url="https://api.example.com",
            auth=auth,
        )
        assert "Authorization" in result
        assert "Bearer tok" in result

    def test_timeout_option(self) -> None:
        """Timeout option adds -TimeoutSec parameter."""
        result = SnippetGenerator.generate(
            "PowerShell (RestMethod)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 20},
        )
        assert "-TimeoutSec 20" in result

    def test_no_redirect(self) -> None:
        """Redirects disabled adds -MaximumRedirection 0."""
        result = SnippetGenerator.generate(
            "PowerShell (RestMethod)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "-MaximumRedirection 0" in result
