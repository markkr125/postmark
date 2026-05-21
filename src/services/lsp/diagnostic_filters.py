"""Filters for noisy LSP diagnostics before they reach script editors."""

from __future__ import annotations

from typing import Any

# checkJs suggestions on plain ``.js`` buffers (not errors; ``noImplicitAny`` is off).
_IMPLICIT_ANY_INFER_MARKERS = (
    "implicitly has an 'any' type",
    "better type may be inferred from usage",
)


def _is_javascript_document_uri(document_uri: str | None) -> bool:
    """Return whether *document_uri* points at a ``.js`` buffer (not ``.ts``)."""
    if not document_uri:
        return False
    path = document_uri.split("?", 1)[0].lower()
    return path.endswith(".js")


def should_publish_lsp_diagnostic(
    raw: dict[str, Any],
    *,
    document_uri: str | None = None,
) -> bool:
    """Return ``False`` to drop *raw* before it becomes a :class:`Diagnostic`."""
    message = str(raw.get("message", ""))
    return not (
        _is_javascript_document_uri(document_uri)
        and all(marker in message for marker in _IMPLICIT_ANY_INFER_MARKERS)
    )
