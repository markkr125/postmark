"""Shell and CLI snippet generators.

Generators for command-line tools and text-based formats:
cURL, wget, HTTPie, raw HTTP, and PowerShell.
"""

from __future__ import annotations

import json
import shlex

from services.http.snippet_generator.generator import (LanguageEntry,
                                                       SnippetOptions)


def curl(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a cURL command."""
    options = options or {}
    use_long = options.get("long_form", True)
    multiline = options.get("multiline", True)
    continuation = options.get("line_continuation", "\\")
    quote = options.get("quote_type", "single")
    silent = options.get("silent_mode", False)

    def _quote_url(raw: str) -> str:
        """Quote the URL with single or double quotes."""
        if quote == "double":
            return f'"{raw}"'
        return f"'{raw}'"

    parts = ["curl"]
    # Method
    if use_long:
        parts.append(f"--request {method.upper()}")
    else:
        parts.append(f"-X {method.upper()}")
    parts.append(_quote_url(url))
    # Follow redirect
    if options.get("follow_redirect", True):
        parts.append("--location" if use_long else "-L")
    # Follow original method
    if options.get("follow_original_method", False):
        parts.append("--post301")
        parts.append("--post302")
        parts.append("--post303")
    # Silent mode
    if silent:
        parts.append("--silent" if use_long else "-s")
    # Timeout
    timeout = options.get("request_timeout", 0)
    if timeout:
        parts.append(f"--max-time {timeout}")
    # Headers
    for key, value in headers.items():
        flag = "--header" if use_long else "-H"
        parts.append(f"{flag} {shlex.quote(f'{key}: {value}')}")
    # Body
    if body:
        flag = "--data" if use_long else "-d"
        parts.append(f"{flag} {shlex.quote(body)}")
    if multiline:
        return f" {continuation}\n  ".join(parts)
    return " ".join(parts)


def http_raw(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a raw HTTP/1.1 request."""
    # Extract host from URL
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    lines = [f"{method.upper()} {path} HTTP/1.1", f"Host: {host}"]
    for key, value in headers.items():
        lines.append(f"{key}: {value}")
    if body:
        lines.append(f"Content-Length: {len(body.encode())}")
        lines.append("")
        lines.append(body)
    else:
        lines.append("")
    return "\n".join(lines)


def shell_wget(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a wget command."""
    options = options or {}
    parts = ["wget", f"--method={method.upper()}"]
    if not options.get("follow_redirect", True):
        parts.append("--max-redirect=0")
    timeout = options.get("request_timeout", 0)
    if timeout:
        parts.append(f"--timeout={timeout}")
    for key, value in headers.items():
        parts.append(f"--header={shlex.quote(f'{key}: {value}')}")
    if body:
        parts.append(f"--body-data={shlex.quote(body)}")
    parts.append("-O-")
    parts.append(shlex.quote(url))
    return " \\\n  ".join(parts)


def shell_httpie(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate an HTTPie command."""
    options = options or {}
    parts = ["http", method.upper(), shlex.quote(url)]
    if not options.get("follow_redirect", True):
        parts.append("--follow=false")
    timeout = options.get("request_timeout", 0)
    if timeout:
        parts.append(f"--timeout={timeout}")
    for key, value in headers.items():
        parts.append(f"{shlex.quote(key)}:{shlex.quote(value)}")
    if body:
        # Try JSON for inline body
        try:
            json.loads(body)
            parts = ["echo", shlex.quote(body), "|", *parts]
            parts.append("--json")
        except (json.JSONDecodeError, TypeError):
            parts = ["echo", shlex.quote(body), "|", *parts]
    return " \\\n  ".join(parts)


def powershell_restmethod(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None = None,
    options: SnippetOptions | None = None,
) -> str:
    """Generate a PowerShell Invoke-RestMethod snippet."""
    options = options or {}
    lines: list[str] = []

    if headers:
        hdr_items = ", ".join(f'"{k}" = "{v}"' for k, v in headers.items())
        lines.append(f"$headers = @{{{hdr_items}}}")
        lines.append("")

    if body:
        escaped = body.replace("'", "''")
        lines.append(f"$body = '{escaped}'")
        lines.append("")

    call = f'Invoke-RestMethod -Uri "{url}" -Method {method.upper()}'
    if headers:
        call += " -Headers $headers"
    if body:
        call += " -Body $body"
        # Add content-type if present
        ct = headers.get("Content-Type")
        if ct:
            call += f' -ContentType "{ct}"'
    if not options.get("follow_redirect", True):
        call += " -MaximumRedirection 0"
    timeout = options.get("request_timeout", 0)
    if timeout:
        call += f" -TimeoutSec {timeout}"
    lines.append(call)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

SHELL_LANGUAGES: list[LanguageEntry] = [
    LanguageEntry(
        "cURL",
        "bash",
        (
            "trim_body",
            "request_timeout",
            "follow_redirect",
            "follow_original_method",
            "multiline",
            "long_form",
            "line_continuation",
            "quote_type",
            "silent_mode",
        ),
        curl,
    ),
    LanguageEntry("HTTP", "http", ("trim_body",), http_raw),
    LanguageEntry(
        "PowerShell (RestMethod)",
        "powershell",
        ("trim_body", "request_timeout", "follow_redirect"),
        powershell_restmethod,
    ),
    LanguageEntry(
        "Shell (HTTPie)",
        "bash",
        ("request_timeout", "follow_redirect"),
        shell_httpie,
    ),
    LanguageEntry(
        "Shell (wget)",
        "bash",
        ("indent_count", "indent_type", "trim_body", "request_timeout", "follow_redirect"),
        shell_wget,
    ),
]
]
