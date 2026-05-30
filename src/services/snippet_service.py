"""Service layer for user-authored script snippets.

Widgets must call :class:`SnippetService` — never import
``snippet_repository`` from UI code.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from database.models.snippets.snippet_repository import (
    create_snippet,
    delete_snippet,
    list_snippets,
    update_snippet,
)

logger = logging.getLogger(__name__)

_LONG_TO_SHORT: dict[str, str] = {
    "javascript": "js",
    "python": "py",
    "typescript": "ts",
}
_SHORT_TO_LONG: dict[str, str] = {
    "js": "javascript",
    "py": "python",
    "ts": "typescript",
}

_VALID_CONTEXTS = frozenset({"pre", "test", "both"})
_DEFAULT_CATEGORY = "My snippets"


class UserSnippetDict(TypedDict):
    """User snippet row returned by :meth:`SnippetService.list`."""

    id: int
    name: str
    language: str
    category: str
    body: str
    context: str
    created_at: str | None
    is_user: bool


class SnippetService:
    """CRUD bridge for DB-backed script snippets."""

    @staticmethod
    def normalize_language(language: str) -> str:
        """Map editor language codes to DB short codes (``js`` / ``py`` / ``ts``)."""
        lang = (language or "").lower().strip()
        if lang == "typescript":
            return "js"
        return _LONG_TO_SHORT.get(lang, lang)

    @staticmethod
    def to_editor_language(short_code: str) -> str:
        """Map DB short codes back to editor language strings."""
        code = (short_code or "").lower().strip()
        return _SHORT_TO_LONG.get(code, code)

    @staticmethod
    def list_all(language: str) -> list[UserSnippetDict]:
        """Return all user snippets for *language* (no context filter)."""
        short = SnippetService.normalize_language(language)
        rows = list_snippets(language=short)
        return [
            UserSnippetDict(
                id=int(row["id"]),
                name=str(row["name"]),
                language=str(row["language"]),
                category=str(row.get("category") or _DEFAULT_CATEGORY),
                body=str(row["body"]),
                context=str(row.get("context") or "both"),
                created_at=row.get("created_at"),
                is_user=True,
            )
            for row in rows
        ]

    @staticmethod
    def list(language: str, context: str) -> list[UserSnippetDict]:
        """Return user snippets for *language* filtered by *context*."""
        ctx = SnippetService._normalize_context_key(context)
        return [
            row
            for row in SnippetService.list_all(language)
            if SnippetService._context_matches(row["context"], ctx)
        ]

    @staticmethod
    def create(
        *,
        name: str,
        language: str,
        body: str,
        category: str = _DEFAULT_CATEGORY,
        context: str = "both",
    ) -> int:
        """Persist a new snippet; return its id."""
        short = SnippetService.normalize_language(language)
        ctx = SnippetService._validate_context(context)
        cat = (category or "").strip() or _DEFAULT_CATEGORY
        nm = (name or "").strip()
        if not nm:
            raise ValueError("Snippet name is required")
        if not (body or "").strip():
            raise ValueError("Snippet body is required")
        row = create_snippet(
            name=nm,
            language=short,
            category=cat,
            body=body,
            context=ctx,
        )
        SnippetService._invalidate_loader_cache()
        return int(row.id)

    @staticmethod
    def update(
        snippet_id: int,
        *,
        name: str | None = None,
        category: str | None = None,
        body: str | None = None,
        context: str | None = None,
    ) -> None:
        """Update fields on an existing user snippet."""
        ctx = SnippetService._validate_context(context) if context is not None else None
        update_snippet(
            snippet_id,
            name=name.strip() if name is not None else None,
            category=category.strip() if category is not None else None,
            body=body,
            context=ctx,
        )
        SnippetService._invalidate_loader_cache()

    @staticmethod
    def delete(snippet_id: int) -> None:
        """Remove a user snippet from the database."""
        delete_snippet(snippet_id)
        SnippetService._invalidate_loader_cache()

    @staticmethod
    def _normalize_context_key(context: str) -> str:
        """Map editor script types to snippet context keys."""
        key = (context or "").lower().strip()
        if key == "pre_request":
            return "pre"
        if key in ("test", "post"):
            return "test"
        return key

    @staticmethod
    def _validate_context(context: str) -> str:
        """Return a normalised context or raise ``ValueError``."""
        key = SnippetService._normalize_context_key(context)
        if key not in _VALID_CONTEXTS:
            raise ValueError(f"Invalid snippet context: {context!r}")
        return key

    @staticmethod
    def _context_matches(stored: str, requested: str) -> bool:
        """Return whether a stored row is visible for the requested editor context."""
        if stored == "both":
            return True
        if requested == "both":
            return True
        return stored == requested

    @staticmethod
    def _invalidate_loader_cache() -> None:
        """Clear memoised built-in + user snippet merges."""
        from ui.widgets.snippets.loader import invalidate_snippet_cache

        invalidate_snippet_cache()
