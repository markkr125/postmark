"""Generate code snippets for HTTP requests in various languages.

Provides a ``SnippetGenerator`` with static methods that convert
request parameters (method, URL, headers, body) into runnable code
snippets for different languages and libraries.
"""

from __future__ import annotations

import json
import shlex


def _parse_headers(headers_text: str | None) -> dict[str, str]:
    """Parse ``Key: Value`` header lines into a dict."""
    if not headers_text:
        return {}
    result: dict[str, str] = {}
    for line in headers_text.splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            result[key.strip()] = value.strip()
    return result


class SnippetGenerator:
    """Generate code snippets from request parameters.

    Every method is a ``@staticmethod`` — no shared state.
    """

    @staticmethod
    def curl(
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
    ) -> str:
        """Generate a cURL command."""
        parts = ["curl", "-X", method.upper(), shlex.quote(url)]
        for key, value in _parse_headers(headers).items():
            parts.append("-H")
            parts.append(shlex.quote(f"{key}: {value}"))
        if body:
            parts.append("-d")
            parts.append(shlex.quote(body))
        return " \\\n  ".join(parts)

    @staticmethod
    def python_requests(
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
    ) -> str:
        """Generate a Python ``requests`` snippet."""
        lines = ["import requests", ""]
        hdr = _parse_headers(headers)

        if hdr:
            lines.append(f"headers = {json.dumps(hdr, indent=4)}")
            lines.append("")

        call = f'response = requests.{method.lower()}("{url}"'
        if hdr:
            call += ", headers=headers"
        if body:
            # Try JSON
            try:
                json.loads(body)
                lines.append(f"payload = {body}")
                lines.append("")
                call += ", json=payload"
            except (json.JSONDecodeError, TypeError):
                call += f', data="""{body}"""'
        call += ")"
        lines.append(call)
        lines.append("print(response.status_code)")
        lines.append("print(response.text)")
        return "\n".join(lines)

    @staticmethod
    def javascript_fetch(
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
    ) -> str:
        """Generate a JavaScript ``fetch`` snippet."""
        hdr = _parse_headers(headers)
        opts: list[str] = [f'  method: "{method.upper()}"']
        if hdr:
            hdr_str = json.dumps(hdr, indent=4)
            # Indent the headers block
            hdr_lines = hdr_str.splitlines()
            indented = "\n".join(
                f"    {line}" if i > 0 else f"  headers: {line}" for i, line in enumerate(hdr_lines)
            )
            opts.append(indented)
        if body:
            opts.append(f"  body: {json.dumps(body)}")
        opts_block = ",\n".join(opts)
        return (
            f'fetch("{url}", {{\n'
            f"{opts_block}\n"
            f"}})\n"
            f"  .then(response => response.json())\n"
            f"  .then(data => console.log(data));"
        )

    @staticmethod
    def available_languages() -> list[str]:
        """Return the list of supported snippet languages."""
        return ["cURL", "Python (requests)", "JavaScript (fetch)"]

    @staticmethod
    def generate(
        language: str,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
    ) -> str:
        """Generate a snippet for the given language label.

        The *language* parameter should be one of the values returned by
        :meth:`available_languages`.
        """
        if language == "cURL":
            return SnippetGenerator.curl(method=method, url=url, headers=headers, body=body)
        if language == "Python (requests)":
            return SnippetGenerator.python_requests(
                method=method, url=url, headers=headers, body=body
            )
        if language == "JavaScript (fetch)":
            return SnippetGenerator.javascript_fetch(
                method=method, url=url, headers=headers, body=body
            )
        return f"# Unsupported language: {language}"
