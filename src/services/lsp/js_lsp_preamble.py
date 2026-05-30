"""Invisible preamble prepended to script buffers sent to Deno LSP.

Deno type-checks each virtual ``.js`` file in isolation. Without explicit
references, ``pm`` is undefined and ``pm.require('npm:…')`` overloads from
``pm_require_index.ts`` are never applied — completions fall back to globals
like ``Array``. Triple-slash references pull the stub and generated index into
the buffer's compilation unit.
"""

from __future__ import annotations

from pathlib import Path

from services.lsp.client import Diagnostic
from services.lsp.qt_lsp_offsets import qpos_to_lsp

_PREAMBLE_TEXT = (
    '/// <reference path="./stubs/pm.d.ts" />\n/// <reference path="./pm_require_index.ts" />\n\n'
)

JS_LSP_PREAMBLE_LINE_COUNT = 3


def workspace_ambient_pm_enabled(workspace: Path | None = None) -> bool:
    """Return whether ``ambient_pm.d.ts`` makes the triple-slash preamble unnecessary."""
    from services.lsp.servers._workspace import ensure_js_workspace

    ws = workspace or ensure_js_workspace()
    return (ws / "ambient_pm.d.ts").is_file()


def uses_js_lsp_preamble(
    language_id: str | None,
    *,
    workspace: Path | None = None,
) -> bool:
    """Return whether *language_id* buffers are wrapped with the JS preamble."""
    lang = (language_id or "").lower().strip()
    if lang not in ("javascript", "typescript"):
        return False
    return not workspace_ambient_pm_enabled(workspace)


def wrap_script_for_lsp(user_text: str, *, workspace: Path | None = None) -> str:
    """Prefix *user_text* with reference directives for Deno LSP when needed."""
    if not uses_js_lsp_preamble("javascript", workspace=workspace):
        return user_text
    return _PREAMBLE_TEXT + user_text


def editor_position_to_lsp(
    document: object,
    position: int,
    *,
    language_id: str | None,
    workspace: Path | None = None,
) -> tuple[int, int]:
    """Map a QTextDocument offset to LSP ``(line, column)`` including preamble lines."""
    line, col = qpos_to_lsp(document, position)  # type: ignore[arg-type]
    if uses_js_lsp_preamble(language_id, workspace=workspace):
        line += JS_LSP_PREAMBLE_LINE_COUNT
    return line, col


def lsp_line_to_editor_line(
    lsp_line: int,
    *,
    language_id: str | None,
    workspace: Path | None = None,
) -> int | None:
    """Map an LSP 0-based line to editor 0-based line, or ``None`` if in the preamble."""
    if not uses_js_lsp_preamble(language_id, workspace=workspace):
        return lsp_line
    editor_line = lsp_line - JS_LSP_PREAMBLE_LINE_COUNT
    return editor_line if editor_line >= 0 else None


def shift_diagnostics_to_editor(
    diags: list[Diagnostic],
    *,
    language_id: str | None,
    workspace: Path | None = None,
) -> list[Diagnostic]:
    """Drop preamble-only diagnostics and shift the rest to editor line numbers."""
    if not uses_js_lsp_preamble(language_id, workspace=workspace):
        return list(diags)
    out: list[Diagnostic] = []
    for d in diags:
        start = lsp_line_to_editor_line(
            d.line,
            language_id=language_id,
            workspace=workspace,
        )
        if start is None:
            continue
        end = lsp_line_to_editor_line(
            d.end_line,
            language_id=language_id,
            workspace=workspace,
        )
        if end is None:
            end = start
        out.append(
            Diagnostic(
                line=start,
                column=d.column,
                end_line=end,
                end_column=d.end_column,
                severity=d.severity,
                message=d.message,
                source=d.source,
            )
        )
    return out


__all__ = [
    "JS_LSP_PREAMBLE_LINE_COUNT",
    "editor_position_to_lsp",
    "lsp_line_to_editor_line",
    "shift_diagnostics_to_editor",
    "uses_js_lsp_preamble",
    "workspace_ambient_pm_enabled",
    "wrap_script_for_lsp",
]
