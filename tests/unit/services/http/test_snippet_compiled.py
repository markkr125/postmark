"""Tests for compiled / statically-typed language snippet generators."""

from __future__ import annotations

from services.http.snippet_generator import SnippetGenerator


class TestGoNative:
    """Verify Go (net/http) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes net/http import and request construction."""
        result = SnippetGenerator.generate(
            "Go (net/http)", method="GET", url="https://api.example.com"
        )
        assert "net/http" in result
        assert "http.NewRequest" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet sets headers via req.Header.Set."""
        result = SnippetGenerator.generate(
            "Go (net/http)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "Header.Set" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet includes strings.NewReader body."""
        result = SnippetGenerator.generate(
            "Go (net/http)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "strings.NewReader" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets Timeout on http.Client."""
        result = SnippetGenerator.generate(
            "Go (net/http)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 10},
        )
        assert "Timeout:" in result
        assert "10" in result

    def test_no_redirect(self) -> None:
        """Disabled redirects add CheckRedirect to client."""
        result = SnippetGenerator.generate(
            "Go (net/http)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "CheckRedirect" in result
        assert "ErrUseLastResponse" in result


class TestRustReqwest:
    """Verify Rust (reqwest) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes reqwest Client and method."""
        result = SnippetGenerator.generate(
            "Rust (reqwest)", method="GET", url="https://api.example.com"
        )
        assert "reqwest" in result
        assert ".get(" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet chains .header() calls."""
        result = SnippetGenerator.generate(
            "Rust (reqwest)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert ".header(" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet chains .body() for POST."""
        result = SnippetGenerator.generate(
            "Rust (reqwest)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert ".body(" in result

    def test_timeout_option(self) -> None:
        """Timeout option chains .timeout()."""
        result = SnippetGenerator.generate(
            "Rust (reqwest)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 30},
        )
        assert ".timeout(" in result
        assert "30" in result

    def test_no_redirect(self) -> None:
        """Disabled redirects add redirect policy."""
        result = SnippetGenerator.generate(
            "Rust (reqwest)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert ".redirect(" in result
        assert "Policy::none()" in result


class TestCLibcurl:
    """Verify C (libcurl) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes curl_easy_init and URL."""
        result = SnippetGenerator.generate(
            "C (libcurl)", method="GET", url="https://api.example.com"
        )
        assert "curl_easy_init" in result
        assert "CURLOPT_URL" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet adds headers via curl_slist_append."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "curl_slist_append" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet sets CURLOPT_POSTFIELDS."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "CURLOPT_POSTFIELDS" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets CURLOPT_TIMEOUT."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 20},
        )
        assert "CURLOPT_TIMEOUT" in result

    def test_follow_redirect(self) -> None:
        """Default includes CURLOPT_FOLLOWLOCATION."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="GET",
            url="https://example.com",
        )
        assert "CURLOPT_FOLLOWLOCATION" in result

    def test_no_redirect(self) -> None:
        """Disabled redirects omit CURLOPT_FOLLOWLOCATION."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "CURLOPT_FOLLOWLOCATION" not in result

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits includes and main wrapper."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "#include" not in result
        assert "int main" not in result
        assert "curl_easy_init" in result

    def test_boilerplate_default(self) -> None:
        """Default includes #include and int main wrapper."""
        result = SnippetGenerator.generate(
            "C (libcurl)",
            method="GET",
            url="https://example.com",
        )
        assert "#include" in result
        assert "int main" in result


class TestSwiftUrlsession:
    """Verify Swift (URLSession) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes URLSession and URL construction."""
        result = SnippetGenerator.generate(
            "Swift (URLSession)", method="GET", url="https://api.example.com"
        )
        assert "URLSession" in result
        assert "URL(string:" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet sets headers via setValue forHTTPHeaderField."""
        result = SnippetGenerator.generate(
            "Swift (URLSession)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "setValue" in result or "addValue" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet sets httpBody on request."""
        result = SnippetGenerator.generate(
            "Swift (URLSession)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "httpBody" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets timeoutInterval."""
        result = SnippetGenerator.generate(
            "Swift (URLSession)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 15},
        )
        assert "timeoutInterval" in result or "timeout" in result.lower()

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits import Foundation."""
        result = SnippetGenerator.generate(
            "Swift (URLSession)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "import Foundation" not in result
        assert "URLRequest" in result

    def test_boilerplate_default(self) -> None:
        """Default includes import Foundation."""
        result = SnippetGenerator.generate(
            "Swift (URLSession)",
            method="GET",
            url="https://example.com",
        )
        assert "import Foundation" in result


class TestJavaOkhttp:
    """Verify Java (OkHttp) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes OkHttpClient and Request.Builder."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)", method="GET", url="https://api.example.com"
        )
        assert "OkHttpClient" in result
        assert "Request.Builder" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet chains .addHeader() calls."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "addHeader" in result or ".header(" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet includes RequestBody.create."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "RequestBody" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets connectTimeout or readTimeout."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 10},
        )
        timeout_keywords = ["connectTimeout", "readTimeout", "callTimeout", "timeout"]
        assert any(kw in result for kw in timeout_keywords)

    def test_no_redirect(self) -> None:
        """Disabled redirects add followRedirects(false)."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "followRedirects(false)" in result

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits imports and class wrapper."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "import " not in result
        assert "OkHttpClient" in result

    def test_boilerplate_default(self) -> None:
        """Default includes import statements."""
        result = SnippetGenerator.generate(
            "Java (OkHttp)",
            method="GET",
            url="https://example.com",
        )
        assert "import " in result


class TestKotlinOkhttp:
    """Verify Kotlin (OkHttp) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes OkHttpClient and Request.Builder."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)", method="GET", url="https://api.example.com"
        )
        assert "OkHttpClient" in result
        assert "Request.Builder" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet chains .addHeader() calls."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)",
            method="POST",
            url="https://api.example.com",
            headers="Content-Type: application/json",
        )
        assert "addHeader" in result or ".header(" in result
        assert "Content-Type" in result

    def test_with_body(self) -> None:
        """Snippet includes RequestBody or toRequestBody."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "RequestBody" in result or "toRequestBody" in result

    def test_timeout_option(self) -> None:
        """Timeout option configures OkHttp timeouts."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 10},
        )
        timeout_keywords = ["connectTimeout", "readTimeout", "callTimeout", "timeout"]
        assert any(kw in result for kw in timeout_keywords)

    def test_no_redirect(self) -> None:
        """Disabled redirects add followRedirects(false)."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "followRedirects(false)" in result

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits import statements."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "import " not in result
        assert "OkHttpClient" in result

    def test_boilerplate_default(self) -> None:
        """Default includes import statements."""
        result = SnippetGenerator.generate(
            "Kotlin (OkHttp)",
            method="GET",
            url="https://example.com",
        )
        assert "import " in result


class TestCsharpHttpclient:
    """Verify C# (HttpClient) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes HttpClient and method call."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)", method="GET", url="https://api.example.com"
        )
        assert "HttpClient" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet sets request headers."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)",
            method="POST",
            url="https://api.example.com",
            headers="Accept: application/json",
        )
        assert "Accept" in result
        assert "Headers.Add" in result

    def test_with_body(self) -> None:
        """Snippet includes StringContent for body."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "StringContent" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets client.Timeout."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 15},
        )
        assert "Timeout" in result

    def test_no_redirect(self) -> None:
        """Disabled redirects use HttpClientHandler with AllowAutoRedirect."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "AllowAutoRedirect = false" in result
        assert "HttpClientHandler" in result

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits using directive."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "using System" not in result
        assert "HttpClient" in result

    def test_boilerplate_default(self) -> None:
        """Default includes using directive."""
        result = SnippetGenerator.generate(
            "C# (HttpClient)",
            method="GET",
            url="https://example.com",
        )
        assert "using System" in result


class TestCsharpRestsharp:
    """Verify C# (RestSharp) snippet generation."""

    def test_basic_get(self) -> None:
        """Snippet includes RestClient and RestRequest."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)", method="GET", url="https://api.example.com"
        )
        assert "RestClient" in result
        assert "RestRequest" in result
        assert "https://api.example.com" in result

    def test_with_headers(self) -> None:
        """Snippet adds headers via AddHeader."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)",
            method="POST",
            url="https://api.example.com",
            headers="Accept: application/json",
        )
        assert "AddHeader" in result
        assert "Accept" in result

    def test_with_body(self) -> None:
        """Snippet includes AddStringBody for request body."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)",
            method="POST",
            url="https://api.example.com",
            body='{"key": "value"}',
        )
        assert "AddStringBody" in result

    def test_timeout_option(self) -> None:
        """Timeout option sets MaxTimeout."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)",
            method="GET",
            url="https://example.com",
            options={"request_timeout": 10},
        )
        assert "MaxTimeout" in result
        assert "10000" in result

    def test_no_redirect(self) -> None:
        """Disabled redirects set FollowRedirects = false."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)",
            method="GET",
            url="https://example.com",
            options={"follow_redirect": False},
        )
        assert "FollowRedirects = false" in result

    def test_no_boilerplate(self) -> None:
        """Boilerplate disabled omits using directive."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)",
            method="GET",
            url="https://example.com",
            options={"include_boilerplate": False},
        )
        assert "using RestSharp" not in result
        assert "RestClient" in result

    def test_boilerplate_default(self) -> None:
        """Default includes using RestSharp directive."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)",
            method="GET",
            url="https://example.com",
        )
        assert "using RestSharp" in result

    def test_method_mapping(self) -> None:
        """HTTP methods map to RestSharp Method enum values."""
        for method, expected in [("POST", "Method.Post"), ("PUT", "Method.Put")]:
            result = SnippetGenerator.generate(
                "C# (RestSharp)", method=method, url="https://example.com"
            )
            assert expected in result

    def test_execute_async(self) -> None:
        """Snippet uses ExecuteAsync for the request call."""
        result = SnippetGenerator.generate(
            "C# (RestSharp)", method="GET", url="https://example.com"
        )
        assert "ExecuteAsync" in result
