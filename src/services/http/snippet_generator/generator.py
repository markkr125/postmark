"""Core registry, dispatch, and shared helpers for snippet generation.

Defines :class:`SnippetGenerator` (the public API), :class:`SnippetOptions`
(per-snippet configuration), :class:`LanguageEntry` (registry metadata),
and delegates auth injection to :func:`services.http.auth_handler.apply_auth`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple, TypedDict

from services.http.auth_handler import apply_auth
from services.http.header_utils import parse_header_dict

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

_DEFAULT_INDENT_COUNT = 2
_DEFAULT_INDENT_TYPE = "space"


class SnippetOptions(TypedDict, total=False):
    """Per-snippet configuration options.

    All fields are optional — missing keys fall back to defaults.
    """

    indent_count: int
    """Number of indentation characters per level (default 2)."""
    indent_type: str
    """``"space"`` or ``"tab"`` (default ``"space"``)."""
    trim_body: bool
    """Strip leading/trailing whitespace from the request body (default False)."""
    follow_redirect: bool
    """Include a follow-redirects flag in shell commands (default True)."""
    request_timeout: int
    """Timeout in seconds; 0 means no timeout (default 0)."""
    include_boilerplate: bool
    """Include boilerplate code such as imports and main wrappers (default True)."""
    async_await: bool
    """Use async/await syntax instead of promise chains (default False)."""
    es6_features: bool
    """Use ES6+ syntax such as ``import`` and arrow functions (default False)."""
    multiline: bool
    """Split shell commands across multiple lines (default True)."""
    long_form: bool
    """Use long-form options like ``--header`` instead of ``-H`` (default True)."""
    line_continuation: str
    """Line continuation char: ``\\``, ``^``, or backtick (default ``\\``)."""
    quote_type: str
    """``"single"`` or ``"double"`` quotes around URLs (default ``"single"``)."""
    follow_original_method: bool
    """Keep original HTTP method on redirect instead of GET (default False)."""
    silent_mode: bool
    """Suppress progress meter / error messages (default False)."""


def resolve_options(options: SnippetOptions | None) -> SnippetOptions:
    """Return *options* with defaults merged for any missing keys."""
    defaults: SnippetOptions = {
        "indent_count": _DEFAULT_INDENT_COUNT,
        "indent_type": _DEFAULT_INDENT_TYPE,
        "trim_body": False,
        "follow_redirect": True,
        "request_timeout": 0,
        "include_boilerplate": True,
        "async_await": False,
        "es6_features": False,
        "multiline": True,
        "long_form": True,
        "line_continuation": "\\\\",
        "quote_type": "single",
        "follow_original_method": False,
        "silent_mode": False,
    }
    if options:
        defaults.update(options)
    return defaults


def indent_str(options: SnippetOptions) -> str:
    """Build a single indentation string from resolved *options*."""
    char = "\t" if options.get("indent_type") == "tab" else " "
    return char * options.get("indent_count", _DEFAULT_INDENT_COUNT)


def prepare_body(body: str | None, options: SnippetOptions) -> str | None:
    """Optionally trim whitespace from *body* per *options*."""
    if body is None:
        return None
    if options.get("trim_body"):
        body = body.strip()
    return body if body else None


# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------


class LanguageEntry(NamedTuple):
    """Metadata for a single snippet language/library variant."""

    display_name: str
    lexer: str
    applicable_options: tuple[str, ...]
    generate: Callable[..., str]


def _build_registry() -> dict[str, LanguageEntry]:
    """Import all generator modules and build the master registry."""
    from services.http.snippet_generator.compiled_snippets import COMPILED_LANGUAGES
    from services.http.snippet_generator.dynamic_snippets import DYNAMIC_LANGUAGES
    from services.http.snippet_generator.shell_snippets import SHELL_LANGUAGES

    registry: dict[str, LanguageEntry] = {}
    for entries in (SHELL_LANGUAGES, DYNAMIC_LANGUAGES, COMPILED_LANGUAGES):
        for entry in entries:
            registry[entry.display_name] = entry
    return registry


# Lazy-initialised singleton
_REGISTRY: dict[str, LanguageEntry] | None = None


def _get_registry() -> dict[str, LanguageEntry]:
    """Return the language registry, building it on first call."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SnippetGenerator:
    """Generate code snippets from request parameters.

    Every method is a ``@staticmethod`` — no shared state.
    """

    @staticmethod
    def available_languages() -> list[str]:
        """Return the sorted list of supported snippet language labels."""
        return sorted(_get_registry().keys())

    @staticmethod
    def get_language_info(name: str) -> LanguageEntry | None:
        """Return the :class:`LanguageEntry` for *name*, or ``None``."""
        return _get_registry().get(name)

    @staticmethod
    def generate(
        language: str,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
        auth: dict | None = None,
        options: SnippetOptions | None = None,
    ) -> str:
        """Generate a snippet for the given language label.

        The *language* parameter should be one of the values returned
        by :meth:`available_languages`.  Headers are accepted as a raw
        newline-separated string and parsed internally.
        """
        entry = _get_registry().get(language)
        if entry is None:
            return f"# Unsupported language: {language}"

        hdr = parse_header_dict(headers)
        url, hdr = apply_auth(auth, url, hdr, method=method, body=body)
        opts = resolve_options(options)
        body = prepare_body(body, opts)

        return entry.generate(
            method=method,
            url=url,
            headers=hdr,
            body=body,
            options=opts,
        )
