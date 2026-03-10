"""Code snippet generation sub-package.

Re-exports the public API so existing imports continue to work::

    from services.http.snippet_generator import SnippetGenerator
    from services.http.snippet_generator import SnippetOptions
"""

from __future__ import annotations

from services.http.snippet_generator.generator import (
    LanguageEntry,
    SnippetGenerator,
    SnippetOptions,
)

__all__ = [
    "LanguageEntry",
    "SnippetGenerator",
    "SnippetOptions",
]
