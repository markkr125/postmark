"""Unit tests for :mod:`services.lsp.js_lsp_preamble`."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.lsp.client import Diagnostic
from services.lsp.js_lsp_preamble import (
    JS_LSP_PREAMBLE_LINE_COUNT,
    editor_position_to_lsp,
    lsp_line_to_editor_line,
    shift_diagnostics_to_editor,
    wrap_script_for_lsp,
)


@pytest.fixture
def preamble_workspace(tmp_path: Path) -> Path:
    """Workspace without ``ambient_pm.d.ts`` (preamble still required)."""
    (tmp_path / "stubs").mkdir()
    (tmp_path / "stubs" / "pm.d.ts").write_text("declare namespace pm {}\n", encoding="utf-8")
    return tmp_path


class TestWrapScriptForLsp:
    """``wrap_script_for_lsp`` prefixes reference directives."""

    def test_includes_pm_stubs_reference(self, preamble_workspace: Path) -> None:
        wrapped = wrap_script_for_lsp("const x = 1;", workspace=preamble_workspace)
        assert '/// <reference path="./stubs/pm.d.ts" />' in wrapped
        assert '/// <reference path="./pm_require_index.ts" />' in wrapped
        assert wrapped.endswith("const x = 1;")

    def test_preamble_line_count_matches_prefix(self, preamble_workspace: Path) -> None:
        user = "line0\nline1"
        wrapped = wrap_script_for_lsp(user, workspace=preamble_workspace)
        lines = wrapped.splitlines()
        assert len(lines) >= JS_LSP_PREAMBLE_LINE_COUNT + 1
        assert lines[JS_LSP_PREAMBLE_LINE_COUNT] == "line0"


class TestLineMapping:
    """Editor ↔ LSP line offsets for JS buffers."""

    def test_user_line_zero_maps_after_preamble(self, preamble_workspace: Path) -> None:
        assert (
            lsp_line_to_editor_line(
                JS_LSP_PREAMBLE_LINE_COUNT,
                language_id="javascript",
                workspace=preamble_workspace,
            )
            == 0
        )

    def test_preamble_lines_map_to_none(self, preamble_workspace: Path) -> None:
        assert (
            lsp_line_to_editor_line(0, language_id="javascript", workspace=preamble_workspace)
            is None
        )

    def test_shift_diagnostics_drops_preamble(self, preamble_workspace: Path) -> None:
        diags = [
            Diagnostic(0, 0, 0, 5, "error", "preamble noise", "deno"),
            Diagnostic(
                JS_LSP_PREAMBLE_LINE_COUNT,
                4,
                JS_LSP_PREAMBLE_LINE_COUNT,
                10,
                "error",
                "user",
                "deno",
            ),
        ]
        shifted = shift_diagnostics_to_editor(
            diags,
            language_id="javascript",
            workspace=preamble_workspace,
        )
        assert len(shifted) == 1
        assert shifted[0].line == 0
        assert shifted[0].message == "user"


class TestEditorPositionToLsp:
    """``editor_position_to_lsp`` adds preamble offset for JS."""

    def test_python_has_no_offset(self) -> None:
        from PySide6.QtGui import QTextDocument

        doc = QTextDocument("abc")
        line, col = editor_position_to_lsp(doc, 0, language_id="python")
        assert line == 0
        assert col == 0
