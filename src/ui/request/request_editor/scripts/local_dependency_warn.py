"""Warn-only UX when direct ``local:`` dependencies have static errors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.scripting.local_dependency_diagnostics import (
    collect_direct_local_dependency_diagnostics,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStatusBar

    from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel


def count_dependency_errors_in_scripts(scripts: list[tuple[str, str]]) -> int:
    """Return total error-severity dependency issues across *scripts* (code, language)."""
    total = 0
    for code, language in scripts:
        if not (code or "").strip():
            continue
        bundle = collect_direct_local_dependency_diagnostics(code, language)
        total += sum(
            1
            for row in (*bundle.dependency_rows, *bundle.resolution_rows)
            if (row.severity or "").lower() == "error"
        )
    return total


def warn_local_dependency_errors(
    *,
    scripts: list[tuple[str, str]],
    output_panel: ScriptOutputPanel | None,
    status_bar: QStatusBar | None,
    message_prefix: str = "Script",
) -> bool:
    """Focus Problems and set status text when dependency errors exist. Returns whether warned."""
    error_count = count_dependency_errors_in_scripts(scripts)
    if error_count <= 0:
        return False
    if output_panel is not None:
        output_panel.focus_problems_tab()
    if status_bar is not None:
        noun = "error" if error_count == 1 else "errors"
        status_bar.showMessage(
            f"{message_prefix}: {error_count} {noun} in local "
            f"{'dependency' if error_count == 1 else 'dependencies'} — see Problems",
            8000,
        )
    return True
