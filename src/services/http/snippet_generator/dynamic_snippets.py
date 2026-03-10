"""Snippet generators for interpreted / dynamic languages.

Generators for Python, JavaScript, Node.js, Ruby, PHP, and Dart.
"""

from __future__ import annotations

import json

from services.http.snippet_generator.generator import (LanguageEntry,
                                                       SnippetOptions,
                                                       indent_str)

# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def python_requests(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Python ``requests`` snippet."""
    options = options or {}
    ind = indent_str(options)
    lines = ["import requests", ""]

    if headers:
        lines.append(f"headers = {json.dumps(headers, indent=len(ind))}")
        lines.append("")

    call = f'response = requests.{method.lower()}("{url}"'
    if headers:
        call += ", headers=headers"
    if body:
        try:
            json.loads(body)
            lines.append(f"payload = {body}")
            lines.append("")
            call += ", json=payload"
        except (json.JSONDecodeError, TypeError):
            call += f', data="""{body}"""'

    timeout = options.get("request_timeout", 0)
    if timeout:
        call += f", timeout={timeout}"
    if not options.get("follow_redirect", True):
        call += ", allow_redirects=False"
    call += ")"
    lines.append(call)
    lines.append("print(response.status_code)")
    lines.append("print(response.text)")
    return "\n".join(lines)


def python_http_client(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Python ``http.client`` snippet."""
    from urllib.parse import urlparse

    options = options or {}
    ind = indent_str(options)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    use_https = parsed.scheme == "https"
    module = "http.client"

    lines = [f"import {module}", ""]
    conn_class = "HTTPSConnection" if use_https else "HTTPConnection"
    timeout = options.get("request_timeout", 0)
    conn_args = f'"{host}"'
    if parsed.port:
        conn_args += f", {parsed.port}"
    if timeout:
        conn_args += f", timeout={timeout}"
    lines.append(f"conn = {module}.{conn_class}({conn_args})")
    lines.append("")

    if headers:
        lines.append(f"headers = {json.dumps(headers, indent=len(ind))}")
        lines.append("")

    body_arg = f'"{body}"' if body else "None"
    hdr_arg = "headers" if headers else "{}"
    lines.append(f'conn.request("{method.upper()}", "{path}", body={body_arg}, headers={hdr_arg})')
    lines.append("res = conn.getresponse()")
    lines.append("print(res.status, res.reason)")
    lines.append("print(res.read().decode())")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JavaScript / Browser
# ---------------------------------------------------------------------------


def javascript_fetch(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a JavaScript ``fetch`` snippet."""
    options = options or {}
    ind = indent_str(options)
    use_async = options.get("async_await", False)
    opts_lines: list[str] = [f'{ind}method: "{method.upper()}"']
    if headers:
        hdr_str = json.dumps(headers, indent=len(ind))
        hdr_lines = hdr_str.splitlines()
        indented = "\n".join(
            f"{ind}{ind}{line}" if i > 0 else f"{ind}headers: {line}"
            for i, line in enumerate(hdr_lines)
        )
        opts_lines.append(indented)
    if body:
        opts_lines.append(f"{ind}body: {json.dumps(body)}")
    if not options.get("follow_redirect", True):
        opts_lines.append(f'{ind}redirect: "manual"')
    opts_block = ",\n".join(opts_lines)
    if use_async:
        lines = [
            "async function makeRequest() {",
            f'{ind}const response = await fetch("{url}", {{',
        ]
        for line in opts_block.splitlines():
            lines.append(f"{ind}{line}")
        lines.append(f"{ind}}});")
        lines.append(f"{ind}const data = await response.json();")
        lines.append(f"{ind}console.log(data);")
        lines.append("}")
        lines.append("")
        lines.append("makeRequest();")
        return "\n".join(lines)
    return (
        f'fetch("{url}", {{\n'
        f"{opts_block}\n"
        f"}})\n"
        f"{ind}.then(response => response.json())\n"
        f"{ind}.then(data => console.log(data));"
    )


def javascript_xhr(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a JavaScript ``XMLHttpRequest`` snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    lines = ["var xhr = new XMLHttpRequest();"]
    lines.append(f'xhr.open("{method.upper()}", "{url}");')
    if timeout:
        lines.append(f"xhr.timeout = {timeout * 1000};")
    for key, value in headers.items():
        lines.append(f'xhr.setRequestHeader("{key}", "{value}");')
    lines.append("")
    lines.append("xhr.onreadystatechange = function () {")
    lines.append(f"{ind}if (xhr.readyState === 4) {{")
    lines.append(f"{ind}{ind}console.log(xhr.status);")
    lines.append(f"{ind}{ind}console.log(xhr.responseText);")
    lines.append(f"{ind}}}")
    lines.append("};")
    lines.append("")
    if body:
        lines.append(f"xhr.send({json.dumps(body)});")
    else:
        lines.append("xhr.send();")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node.js
# ---------------------------------------------------------------------------


def nodejs_axios(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Node.js ``axios`` snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    use_async = options.get("async_await", False)

    lines = ['const axios = require("axios");', ""]
    config_parts: list[str] = [
        f'{ind}method: "{method.lower()}"',
        f'{ind}url: "{url}"',
    ]
    if headers:
        hdr_str = json.dumps(headers, indent=len(ind))
        hdr_lines = hdr_str.splitlines()
        indented = "\n".join(
            f"{ind}{ind}{line}" if i > 0 else f"{ind}headers: {line}"
            for i, line in enumerate(hdr_lines)
        )
        config_parts.append(indented)
    if body:
        try:
            json.loads(body)
            config_parts.append(f"{ind}data: {body}")
        except (json.JSONDecodeError, TypeError):
            config_parts.append(f"{ind}data: {json.dumps(body)}")
    if timeout:
        config_parts.append(f"{ind}timeout: {timeout * 1000}")
    if not options.get("follow_redirect", True):
        config_parts.append(f"{ind}maxRedirects: 0")
    config_block = ",\n".join(config_parts)

    if use_async:
        lines.append("async function makeRequest() {")
        lines.append(f"{ind}const response = await axios({{")
        for line in config_block.splitlines():
            lines.append(f"{ind}{line}")
        lines.append(f"{ind}}});")
        lines.append(f"{ind}console.log(response.data);")
        lines.append("}")
        lines.append("")
        lines.append("makeRequest();")
    else:
        lines.append(f"axios({{\n{config_block}\n}})")
        lines.append(f"{ind}.then(response => console.log(response.data))")
        lines.append(f"{ind}.catch(error => console.error(error));")
    return "\n".join(lines)


def nodejs_native(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Node.js native ``http``/``https`` snippet."""
    from urllib.parse import urlparse

    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)
    use_es6 = options.get("es6_features", False)

    parsed = urlparse(url)
    use_https = parsed.scheme == "https"
    mod = "https" if use_https else "http"

    if use_es6:
        lines = [f'import {mod} from "{mod}";', ""]
    else:
        lines = [f'const {mod} = require("{mod}");', ""]

    opt_parts: list[str] = []
    if parsed.hostname:
        opt_parts.append(f'{ind}hostname: "{parsed.hostname}"')
    port = parsed.port or (443 if use_https else 80)
    opt_parts.append(f"{ind}port: {port}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    opt_parts.append(f'{ind}path: "{path}"')
    opt_parts.append(f'{ind}method: "{method.upper()}"')
    if headers:
        hdr_str = json.dumps(headers, indent=len(ind))
        hdr_lines = hdr_str.splitlines()
        indented = "\n".join(
            f"{ind}{ind}{line}" if i > 0 else f"{ind}headers: {line}"
            for i, line in enumerate(hdr_lines)
        )
        opt_parts.append(indented)
    if timeout:
        opt_parts.append(f"{ind}timeout: {timeout * 1000}")
    opts_block = ",\n".join(opt_parts)

    lines.append(f"const options = {{\n{opts_block}\n}};")
    lines.append("")
    cb = "(res) => {"
    lines.append(f"const req = {mod}.request(options, {cb}")
    lines.append(f'{ind}let data = "";')
    lines.append(f'{ind}res.on("data", (chunk) => {{ data += chunk; }});')
    lines.append(f'{ind}res.on("end", () => {{ console.log(data); }});')
    lines.append("});")
    lines.append("")
    lines.append('req.on("error", (error) => { console.error(error); });')
    if body:
        lines.append(f"req.write({json.dumps(body)});")
    lines.append("req.end();")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------


def ruby_nethttp(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Ruby ``Net::HTTP`` snippet."""
    from urllib.parse import urlparse

    options = options or {}
    timeout = options.get("request_timeout", 0)

    parsed = urlparse(url)

    lines = ['require "net/http"', 'require "uri"', ""]
    lines.append(f'uri = URI.parse("{url}")')
    lines.append("")

    method_upper = method.upper()
    method_map = {
        "GET": "Get",
        "POST": "Post",
        "PUT": "Put",
        "PATCH": "Patch",
        "DELETE": "Delete",
        "HEAD": "Head",
        "OPTIONS": "Options",
    }
    rb_method = method_map.get(method_upper, "Get")

    lines.append(f"request = Net::HTTP::{rb_method}.new(uri)")
    for key, value in headers.items():
        lines.append(f'request["{key}"] = "{value}"')
    if body:
        lines.append(f"request.body = '{body}'")
    lines.append("")

    lines.append("http = Net::HTTP.new(uri.host, uri.port)")
    if parsed.scheme == "https":
        lines.append("http.use_ssl = true")
    if timeout:
        lines.append(f"http.read_timeout = {timeout}")
        lines.append(f"http.open_timeout = {timeout}")
    if not options.get("follow_redirect", True):
        lines.append("http.max_retries = 0")
    lines.append("")
    lines.append("response = http.request(request)")
    lines.append("puts response.code")
    lines.append("puts response.body")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PHP
# ---------------------------------------------------------------------------


def php_curl(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a PHP cURL snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)

    lines = ["<?php", "", "$ch = curl_init();", ""]
    lines.append(f'curl_setopt($ch, CURLOPT_URL, "{url}");')
    lines.append("curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);")
    lines.append(f'curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "{method.upper()}");')
    if options.get("follow_redirect", True):
        lines.append("curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);")
    if timeout:
        lines.append(f"curl_setopt($ch, CURLOPT_TIMEOUT, {timeout});")

    if headers:
        hdr_lines = [f'{ind}"{k}: {v}"' for k, v in headers.items()]
        hdr_block = ",\n".join(hdr_lines)
        lines.append(f"curl_setopt($ch, CURLOPT_HTTPHEADER, [\n{hdr_block}\n]);")
    if body:
        escaped = body.replace("'", "\\'")
        lines.append(f"curl_setopt($ch, CURLOPT_POSTFIELDS, '{escaped}');")
    lines.append("")
    lines.append("$response = curl_exec($ch);")
    lines.append("curl_close($ch);")
    lines.append("")
    lines.append("echo $response;")
    return "\n".join(lines)


def php_guzzle(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a PHP Guzzle snippet."""
    options = options or {}
    ind = indent_str(options)
    timeout = options.get("request_timeout", 0)

    lines = ["<?php", "", "require 'vendor/autoload.php';", ""]
    lines.append("$client = new GuzzleHttp\\Client();")
    lines.append("")

    opts_parts: list[str] = []
    if headers:
        hdr_items = ", ".join(f"'{k}' => '{v}'" for k, v in headers.items())
        opts_parts.append(f"{ind}'headers' => [{hdr_items}]")
    if body:
        try:
            json.loads(body)
            opts_parts.append(f"{ind}'json' => json_decode('{body}', true)")
        except (json.JSONDecodeError, TypeError):
            escaped = body.replace("'", "\\'")
            opts_parts.append(f"{ind}'body' => '{escaped}'")
    if timeout:
        opts_parts.append(f"{ind}'timeout' => {timeout}")
    if not options.get("follow_redirect", True):
        opts_parts.append(f"{ind}'allow_redirects' => false")
    opts_block = ",\n".join(opts_parts)

    lines.append(f'$response = $client->request("{method.upper()}", "{url}", [')
    if opts_block:
        lines.append(opts_block)
    lines.append("]);")
    lines.append("")
    lines.append("echo $response->getBody();")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dart
# ---------------------------------------------------------------------------


def dart_http(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a Dart ``http`` package snippet."""
    options = options or {}
    ind = indent_str(options)
    boilerplate = options.get("include_boilerplate", True)

    lines: list[str] = []
    if boilerplate:
        lines.append("import 'package:http/http.dart' as http;")
        lines.append("")
    lines.append("void main() async {")

    url_line = f"{ind}var url = Uri.parse('{url}');"
    lines.append(url_line)

    if headers:
        hdr_items = ", ".join(f"'{k}': '{v}'" for k, v in headers.items())
        lines.append(f"{ind}var headers = {{{hdr_items}}};")

    method_lower = method.lower()
    method_map = {"get", "post", "put", "patch", "delete", "head"}
    fn = method_lower if method_lower in method_map else "get"

    call = f"{ind}var response = await http.{fn}(url"
    if headers:
        call += ", headers: headers"
    if body and fn in ("post", "put", "patch"):
        call += f", body: '{body}'"
    call += ");"
    lines.append(call)

    lines.append(f"{ind}print(response.statusCode);")
    lines.append(f"{ind}print(response.body);")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

# Per-language option tuples
_OPT_STD = ("indent_count", "indent_type", "trim_body", "request_timeout", "follow_redirect")

DYNAMIC_LANGUAGES: list[LanguageEntry] = [
    LanguageEntry(
        "Dart (http)",
        "dart",
        (*_OPT_STD, "include_boilerplate"),
        dart_http,
    ),
    LanguageEntry(
        "JavaScript (fetch)",
        "javascript",
        (*_OPT_STD, "async_await"),
        javascript_fetch,
    ),
    LanguageEntry(
        "JavaScript (XHR)",
        "javascript",
        ("indent_count", "indent_type", "trim_body", "request_timeout"),
        javascript_xhr,
    ),
    LanguageEntry(
        "NodeJS (Axios)",
        "javascript",
        (*_OPT_STD, "async_await"),
        nodejs_axios,
    ),
    LanguageEntry(
        "NodeJS (Native)",
        "javascript",
        (*_OPT_STD, "es6_features"),
        nodejs_native,
    ),
    LanguageEntry("PHP (cURL)", "php", _OPT_STD, php_curl),
    LanguageEntry("PHP (Guzzle)", "php", _OPT_STD, php_guzzle),
    LanguageEntry(
        "Python (http.client)",
        "python",
        ("indent_count", "indent_type", "trim_body", "request_timeout"),
        python_http_client,
    ),
    LanguageEntry("Python (requests)", "python", _OPT_STD, python_requests),
    LanguageEntry("Ruby (Net::HTTP)", "ruby", _OPT_STD, ruby_nethttp),
]
    LanguageEntry("Ruby (Net::HTTP)", "ruby", _OPT_STD, ruby_nethttp),
]
