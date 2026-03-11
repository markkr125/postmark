"""Snippet generators for compiled / statically-typed languages.

Generators for Go, Rust, C (libcurl), Swift, Java, Kotlin, and C#.
"""

from __future__ import annotations

import json

from services.http.snippet_generator.generator import (LanguageEntry,
                                                       SnippetOptions,
                                                       indent_str)

# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


def go_native(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Go ``net/http`` snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)

    lines = ["package main", "", "import ("]
    imports = ['"fmt"', '"io"', '"net/http"']
    if body:
        imports.append('"strings"')
    if timeout:
        imports.append('"time"')
    for imp in sorted(imports):
        lines.append(f"{ind}{imp}")
    lines.append(")")
    lines.append("")
    lines.append("func main() {")

    if body:
        lines.append(f"{ind}body := strings.NewReader(`{body}`)")
        lines.append(f'{ind}req, err := http.NewRequest("{method.upper()}", "{url}", body)')
    else:
        lines.append(f'{ind}req, err := http.NewRequest("{method.upper()}", "{url}", nil)')
    lines.append(f"{ind}if err != nil {{")
    lines.append(f"{ind}{ind}panic(err)")
    lines.append(f"{ind}}}")

    for key, value in headers.items():
        lines.append(f'{ind}req.Header.Set("{key}", "{value}")')

    lines.append("")
    no_redirect = not options.get("follow_redirect", True)
    if timeout and no_redirect:
        lines.append(f"{ind}client := &http.Client{{")
        lines.append(f"{ind}{ind}Timeout: {timeout} * time.Second,")
        lines.append(
            f"{ind}{ind}CheckRedirect: func(req *http.Request, via []*http.Request) error {{"
        )
        lines.append(f"{ind}{ind}{ind}return http.ErrUseLastResponse")
        lines.append(f"{ind}{ind}}},")
        lines.append(f"{ind}}}")
    elif timeout:
        lines.append(f"{ind}client := &http.Client{{Timeout: {timeout} * time.Second}}")
    elif no_redirect:
        lines.append(f"{ind}client := &http.Client{{")
        lines.append(
            f"{ind}{ind}CheckRedirect: func(req *http.Request, via []*http.Request) error {{"
        )
        lines.append(f"{ind}{ind}{ind}return http.ErrUseLastResponse")
        lines.append(f"{ind}{ind}}},")
        lines.append(f"{ind}}}")
    else:
        lines.append(f"{ind}client := &http.Client{{}}")
    lines.append(f"{ind}resp, err := client.Do(req)")
    lines.append(f"{ind}if err != nil {{")
    lines.append(f"{ind}{ind}panic(err)")
    lines.append(f"{ind}}}")
    lines.append(f"{ind}defer resp.Body.Close()")
    lines.append("")
    lines.append(f"{ind}respBody, _ := io.ReadAll(resp.Body)")
    lines.append(f"{ind}fmt.Println(string(respBody))")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------


def rust_reqwest(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Rust ``reqwest`` snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)

    lines = ["use reqwest;", ""]
    lines.append("#[tokio::main]")
    lines.append("async fn main() -> Result<(), reqwest::Error> {")

    no_redirect = not options.get("follow_redirect", True)
    if timeout or no_redirect:
        lines.append(f"{ind}let client = reqwest::Client::builder()")
        if timeout:
            lines.append(f"{ind}{ind}.timeout(std::time::Duration::from_secs({timeout}))")
        if no_redirect:
            lines.append(f"{ind}{ind}.redirect(reqwest::redirect::Policy::none())")
        lines.append(f"{ind}{ind}.build()?;")
    else:
        lines.append(f"{ind}let client = reqwest::Client::new();")
    lines.append("")

    method_lower = method.lower()
    lines.append(f'{ind}let response = client.{method_lower}("{url}")')
    for key, value in headers.items():
        lines.append(f'{ind}{ind}.header("{key}", "{value}")')
    if body:
        lines.append(f"{ind}{ind}.body({json.dumps(body)})")
    lines.append(f"{ind}{ind}.send()")
    lines.append(f"{ind}{ind}.await?;")
    lines.append("")
    lines.append(f"{ind}let body = response.text().await?;")
    lines.append(f'{ind}println!("{{}}", body);')
    lines.append(f"{ind}Ok(())")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# C (libcurl)
# ---------------------------------------------------------------------------


def c_libcurl(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a C libcurl snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    boilerplate = options.get("include_boilerplate", True)

    lines: list[str] = []
    if boilerplate:
        lines.extend(["#include <stdio.h>", "#include <curl/curl.h>", ""])
        lines.append("int main(void) {")
        lines.append(f"{ind}CURL *curl = curl_easy_init();")
        lines.append(f"{ind}if (curl) {{")
        ind2 = ind * 2
    else:
        lines.append("CURL *curl = curl_easy_init();")
        lines.append("if (curl) {")
        ind2 = ind

    lines.append(f'{ind2}curl_easy_setopt(curl, CURLOPT_URL, "{url}");')
    lines.append(f'{ind2}curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "{method.upper()}");')
    if options.get("follow_redirect", True):
        lines.append(f"{ind2}curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);")
    if timeout:
        lines.append(f"{ind2}curl_easy_setopt(curl, CURLOPT_TIMEOUT, {timeout}L);")

    if headers:
        lines.append("")
        lines.append(f"{ind2}struct curl_slist *headers = NULL;")
        for key, value in headers.items():
            lines.append(f'{ind2}headers = curl_slist_append(headers, "{key}: {value}");')
        lines.append(f"{ind2}curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);")

    if body:
        escaped = body.replace('"', '\\"')
        lines.append(f'{ind2}curl_easy_setopt(curl, CURLOPT_POSTFIELDS, "{escaped}");')

    lines.append("")
    lines.append(f"{ind2}CURLcode res = curl_easy_perform(curl);")
    if headers:
        lines.append(f"{ind2}curl_slist_free_all(headers);")
    lines.append(f"{ind2}curl_easy_cleanup(curl);")

    if boilerplate:
        lines.append(f"{ind}}}")
        lines.append(f"{ind}return 0;")
        lines.append("}")
    else:
        lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Swift
# ---------------------------------------------------------------------------


def swift_urlsession(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Swift ``URLSession`` snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    boilerplate = options.get("include_boilerplate", True)

    lines: list[str] = []
    if boilerplate:
        lines.extend(["import Foundation", ""])
    lines.append(f'let url = URL(string: "{url}")!')
    lines.append("var request = URLRequest(url: url)")
    lines.append(f'request.httpMethod = "{method.upper()}"')
    if timeout:
        lines.append(f"request.timeoutInterval = {timeout}")
    for key, value in headers.items():
        lines.append(f'request.setValue("{value}", forHTTPHeaderField: "{key}")')
    if body:
        escaped = body.replace('"', '\\"')
        lines.append(f'request.httpBody = "{escaped}".data(using: .utf8)')
    lines.append("")
    lines.append("let task = URLSession.shared.dataTask(with: request) { data, response, error in")
    lines.append(f"{ind}if let data = data {{")
    lines.append(f'{ind}{ind}print(String(data: data, encoding: .utf8) ?? "")')
    lines.append(f"{ind}}}")
    lines.append("}")
    lines.append("task.resume()")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


def java_okhttp(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Java OkHttp snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    boilerplate = options.get("include_boilerplate", True)

    lines: list[str] = []
    if boilerplate:
        lines.extend(
            [
                "import okhttp3.*;",
                "",
                "public class Main {",
                f"{ind}public static void main(String[] args) throws Exception {{",
            ]
        )
        ind2 = ind * 2
    else:
        ind2 = ind

    if timeout:
        lines.append(f"{ind2}OkHttpClient client = new OkHttpClient.Builder()")
        lines.append(
            f"{ind2}{ind}.connectTimeout({timeout}, java.util.concurrent.TimeUnit.SECONDS)"
        )
        lines.append(f"{ind2}{ind}.readTimeout({timeout}, java.util.concurrent.TimeUnit.SECONDS)")
        if not options.get("follow_redirect", True):
            lines.append(f"{ind2}{ind}.followRedirects(false)")
        lines.append(f"{ind2}{ind}.build();")
    elif not options.get("follow_redirect", True):
        lines.append(f"{ind2}OkHttpClient client = new OkHttpClient.Builder()")
        lines.append(f"{ind2}{ind}.followRedirects(false)")
        lines.append(f"{ind2}{ind}.build();")
    else:
        lines.append(f"{ind2}OkHttpClient client = new OkHttpClient();")
    lines.append("")

    method_upper = method.upper()
    needs_body = method_upper in ("POST", "PUT", "PATCH")
    if needs_body and body:
        ct = headers.get("Content-Type", "application/json")
        escaped = body.replace('"', '\\"')
        lines.append(
            f'{ind2}RequestBody body = RequestBody.create("{escaped}", MediaType.parse("{ct}"));'
        )
    elif needs_body:
        lines.append(
            f'{ind2}RequestBody body = RequestBody.create("", MediaType.parse("application/json"));'
        )

    lines.append(f"{ind2}Request request = new Request.Builder()")
    lines.append(f'{ind2}{ind}.url("{url}")')
    for key, value in headers.items():
        lines.append(f'{ind2}{ind}.addHeader("{key}", "{value}")')
    if needs_body:
        lines.append(f"{ind2}{ind}.{method_lower_name(method_upper)}(body)")
    else:
        lines.append(f"{ind2}{ind}.{method_lower_name(method_upper)}()")
    lines.append(f"{ind2}{ind}.build();")
    lines.append("")
    lines.append(f"{ind2}Response response = client.newCall(request).execute();")
    lines.append(f"{ind2}System.out.println(response.body().string());")
    if boilerplate:
        lines.append(f"{ind}}}")
        lines.append("}")
    return "\n".join(lines)


def method_lower_name(method: str) -> str:
    """Map HTTP method to OkHttp builder method name."""
    mapping = {
        "GET": "get",
        "POST": "post",
        "PUT": "put",
        "PATCH": "patch",
        "DELETE": "delete",
        "HEAD": "head",
    }
    return mapping.get(method, "get")


# ---------------------------------------------------------------------------
# Kotlin
# ---------------------------------------------------------------------------


def kotlin_okhttp(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Kotlin OkHttp snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    boilerplate = options.get("include_boilerplate", True)

    lines: list[str] = []
    if boilerplate:
        lines.extend(
            [
                "import okhttp3.*",
                "import okhttp3.MediaType.Companion.toMediaType",
                "import okhttp3.RequestBody.Companion.toRequestBody",
                "",
                "fun main() {",
            ]
        )

    if timeout:
        lines.append(f"{ind}val client = OkHttpClient.Builder()")
        lines.append(f"{ind}{ind}.connectTimeout({timeout}, java.util.concurrent.TimeUnit.SECONDS)")
        lines.append(f"{ind}{ind}.readTimeout({timeout}, java.util.concurrent.TimeUnit.SECONDS)")
        if not options.get("follow_redirect", True):
            lines.append(f"{ind}{ind}.followRedirects(false)")
        lines.append(f"{ind}{ind}.build()")
    elif not options.get("follow_redirect", True):
        lines.append(f"{ind}val client = OkHttpClient.Builder()")
        lines.append(f"{ind}{ind}.followRedirects(false)")
        lines.append(f"{ind}{ind}.build()")
    else:
        lines.append(f"{ind}val client = OkHttpClient()")
    lines.append("")

    method_upper = method.upper()
    needs_body = method_upper in ("POST", "PUT", "PATCH")
    if needs_body and body:
        ct = headers.get("Content-Type", "application/json")
        escaped = body.replace('"', '\\"')
        lines.append(f'{ind}val body = "{escaped}".toRequestBody("{ct}".toMediaType())')
    elif needs_body:
        lines.append(f'{ind}val body = "".toRequestBody("application/json".toMediaType())')

    lines.append(f"{ind}val request = Request.Builder()")
    lines.append(f'{ind}{ind}.url("{url}")')
    for key, value in headers.items():
        lines.append(f'{ind}{ind}.addHeader("{key}", "{value}")')
    if needs_body:
        lines.append(f"{ind}{ind}.{method_lower_name(method_upper)}(body)")
    else:
        lines.append(f"{ind}{ind}.{method_lower_name(method_upper)}()")
    lines.append(f"{ind}{ind}.build()")
    lines.append("")
    lines.append(f"{ind}val response = client.newCall(request).execute()")
    lines.append(f'{ind}println(response.body?.string() ?: "")')
    if boilerplate:
        lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------


def csharp_httpclient(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a C# ``HttpClient`` snippet."""
    options = options or {}
    timeout = options.get("request_timeout", 0)
    boilerplate = options.get("include_boilerplate", True)

    lines: list[str] = []
    if boilerplate:
        lines.append("using System.Net.Http;")
        lines.append("")
    no_redirect = not options.get("follow_redirect", True)
    if no_redirect:
        lines.append("var handler = new HttpClientHandler { AllowAutoRedirect = false };")
        lines.append("var client = new HttpClient(handler);")
    else:
        lines.append("var client = new HttpClient();")
    if timeout:
        lines.append(f"client.Timeout = TimeSpan.FromSeconds({timeout});")

    method_map = {
        "GET": "HttpMethod.Get",
        "POST": "HttpMethod.Post",
        "PUT": "HttpMethod.Put",
        "PATCH": "HttpMethod.Patch",
        "DELETE": "HttpMethod.Delete",
        "HEAD": "HttpMethod.Head",
        "OPTIONS": "HttpMethod.Options",
    }
    http_method = method_map.get(method.upper(), "HttpMethod.Get")

    lines.append("")
    lines.append(f'var request = new HttpRequestMessage({http_method}, "{url}");')
    for key, value in headers.items():
        if key.lower() == "content-type":
            continue  # Content-Type is set on content, not request headers
        lines.append(f'request.Headers.Add("{key}", "{value}");')

    if body:
        ct = headers.get("Content-Type", "application/json")
        escaped = body.replace('"', '\\"')
        lines.append(
            f'request.Content = new StringContent("{escaped}", System.Text.Encoding.UTF8, "{ct}");'
        )
    lines.append("")
    lines.append("var response = await client.SendAsync(request);")
    lines.append("var content = await response.Content.ReadAsStringAsync();")
    lines.append("Console.WriteLine(content);")
    return "\n".join(lines)


def csharp_restsharp(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a C# ``RestSharp`` snippet."""
    options = options or {}
    timeout = options.get("request_timeout", 0)
    boilerplate = options.get("include_boilerplate", True)

    method_map = {
        "GET": "Method.Get",
        "POST": "Method.Post",
        "PUT": "Method.Put",
        "PATCH": "Method.Patch",
        "DELETE": "Method.Delete",
        "HEAD": "Method.Head",
        "OPTIONS": "Method.Options",
    }
    rest_method = method_map.get(method.upper(), "Method.Get")

    lines: list[str] = []
    if boilerplate:
        lines.append("using RestSharp;")
        lines.append("")
    opts_parts: list[str] = []
    if timeout:
        opts_parts.append(f"MaxTimeout = {timeout * 1000}")
    if not options.get("follow_redirect", True):
        opts_parts.append("FollowRedirects = false")
    if opts_parts:
        opts_str = ", ".join(opts_parts)
        lines.append(
            f'var client = new RestClient(new RestClientOptions("{url}") {{ {opts_str} }});'
        )
    else:
        lines.append(f'var client = new RestClient("{url}");')

    lines.append(f'var request = new RestRequest("", {rest_method});')
    for key, value in headers.items():
        lines.append(f'request.AddHeader("{key}", "{value}");')
    if body:
        ct = headers.get("Content-Type", "application/json")
        escaped = body.replace('"', '\\"')
        lines.append(f'request.AddStringBody("{escaped}", "{ct}");')
    lines.append("")
    lines.append("var response = await client.ExecuteAsync(request);")
    lines.append("Console.WriteLine(response.Content);")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

# Per-language option tuples
_OPT_STD = ("indent_count", "indent_type", "trim_body", "request_timeout", "follow_redirect")

COMPILED_LANGUAGES: list[LanguageEntry] = [
    LanguageEntry(
        "C (libcurl)",
        "c",
        (*_OPT_STD, "include_boilerplate"),
        c_libcurl,
    ),
    LanguageEntry(
        "C# (HttpClient)",
        "csharp",
        (*_OPT_STD, "include_boilerplate"),
        csharp_httpclient,
    ),
    LanguageEntry(
        "C# (RestSharp)",
        "csharp",
        (*_OPT_STD, "include_boilerplate"),
        csharp_restsharp,
    ),
    LanguageEntry("Go (net/http)", "go", _OPT_STD, go_native),
    LanguageEntry(
        "Java (OkHttp)",
        "java",
        (*_OPT_STD, "include_boilerplate"),
        java_okhttp,
    ),
    LanguageEntry(
        "Kotlin (OkHttp)",
        "kotlin",
        (*_OPT_STD, "include_boilerplate"),
        kotlin_okhttp,
    ),
    LanguageEntry("Rust (reqwest)", "rust", _OPT_STD, rust_reqwest),
    LanguageEntry(
        "Swift (URLSession)",
        "swift",
        ("indent_count", "indent_type", "trim_body", "request_timeout", "include_boilerplate"),
        swift_urlsession,
    ),
]
