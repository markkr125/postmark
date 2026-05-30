"""Filters for noisy LSP diagnostics before they reach script editors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.lsp.client import Diagnostic
    from services.scripting.local_dependency_diagnostics import RequireSite

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


_UNUSED_BINDING_MARKERS = (
    "is declared but its value is never read",
    "is never used",
    "never read",
)


def should_suppress_unused_local_require_diagnostic(
    diag: Diagnostic,
    require_sites: list[RequireSite],
) -> bool:
    """Drop deno unused-variable noise on ``const x = pm.require('local:…')`` bindings."""
    if diag.related_local_path:
        return False
    source = (diag.source or "").lower()
    if source not in ("deno-ts", "deno-lint"):
        return False
    msg = diag.message.lower()
    if not any(marker in msg for marker in _UNUSED_BINDING_MARKERS):
        return False
    host_line_1 = diag.line + 1
    for site in require_sites:
        if not site.binding_name:
            continue
        if site.line != host_line_1:
            continue
        if site.binding_name.lower() in msg:
            return True
    return False


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
