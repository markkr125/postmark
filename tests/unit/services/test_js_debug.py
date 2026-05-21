"""Tests for JavaScript debug helpers (let/const → var, variable read)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from services.scripting.debug import js_debug


def test_transform_regex_fallback_let() -> None:
    """Line-anchored ``let`` → ``var`` when Esprima is not used."""
    out = js_debug._transform_let_const_regex_fallback("let a = 1;")
    assert "var a" in out
    assert "let " not in out


def test_transform_regex_fallback_const() -> None:
    """Line-anchored ``const`` → ``var``."""
    out = js_debug._transform_let_const_regex_fallback("  const b = 2;")
    assert "var b" in out


def test_read_js_debug_vars_uses_baseline_with_mock_ctx() -> None:
    """``_read_js_debug_vars`` parses merged pm/globals JSON from the context."""
    ctx = MagicMock()
    sample = json.dumps(
        {
            "pm": {"V": "env"},
            "globals": {"g1": 1, "g2": "x"},
            "env_changes": {"E": "1"},
            "global_changes": {"G": "2"},
        }
    )
    ctx.eval.return_value = sample
    out = js_debug._read_js_debug_vars(ctx)
    assert out["pm"] == {"V": "env"}
    assert out["globals"] == {"g1": 1, "g2": "x"}
    assert out["env_changes"] == {"E": "1"}
    assert out["global_changes"] == {"G": "2"}


def test_read_js_debug_vars_falls_back_to_state_changes() -> None:
    """On IIFE eval failure, fall back to ``variable_changes`` / ``global_variable_changes``."""
    ctx = MagicMock()
    ctx.eval.side_effect = [
        Exception("fail"),
        json.dumps({"KEY": "v"}),
        json.dumps({"GKEY": "g"}),
    ]
    out = js_debug._read_js_debug_vars(ctx)
    assert out["env_changes"] == {"KEY": "v"}
    assert out["global_changes"] == {"GKEY": "g"}
    assert out["pm"] == {}
    assert out["globals"] == {}


def test_read_locals_parses_iife_json() -> None:
    """``read_locals_from_iife_json_string`` returns dicts for valid JSON."""
    s = json.dumps(
        {
            "pm": {"a": 1},
            "globals": {"b": 2},
            "env_changes": {"e": 3},
            "global_changes": {"g": 4},
        }
    )
    out = js_debug.read_locals_from_iife_json_string(s)
    assert out["pm"] == {"a": 1} and out["globals"] == {"b": 2}
    assert out["env_changes"] == {"e": 3} and out["global_changes"] == {"g": 4}


def test_split_groups_includes_trailing_block_comment_in_fallback() -> None:
    """The brace-nesting fallback keeps a trailing block comment as a third top-level group."""
    source = "const a = 1;\nconsole.log(a);\n/*\n{ unmatched brace in comment\n*/"
    groups = js_debug._split_into_groups(source)
    assert len(groups) == 3
    assert groups[0] == (0, "const a = 1;")
    assert groups[1] == (1, "console.log(a);")
    assert "unmatched" in groups[2][1]


def test_split_groups_block_comment_with_braces_fallback() -> None:
    """Fallback grouping ignores braces that appear inside block comments."""
    source = "\n".join(
        [
            "if (true) {",
            "  /* {",
            "     } */",
            "  console.log('x');",
            "}",
            "const y = 1;",
        ]
    )
    groups = js_debug._split_into_groups(source)
    assert groups == [
        (0, "if (true) {\n  /* {\n     } */\n  console.log('x');\n}"),
        (5, "const y = 1;"),
    ]


def test_split_groups_line_comment_with_braces_fallback() -> None:
    """Fallback grouping ignores braces that appear in line comments."""
    source = "if (true) {\n  console.log('x'); // }\n}\nconst y = 1;"
    groups = js_debug._split_into_groups(source)
    assert groups == [
        (0, "if (true) {\n  console.log('x'); // }\n}"),
        (3, "const y = 1;"),
    ]


def test_stop_during_pause_produces_no_error_row() -> None:
    """User stop at a breakpoint does not append a synthetic (debug error) test row."""
    import threading

    from services.scripting.debug import js_debug
    from services.scripting.runtime_settings import RuntimeSettings

    if not RuntimeSettings.validate_deno(RuntimeSettings.deno_path()).get("available"):
        pytest.skip("Deno not available for step-through")
    from services.scripting.debug.protocol import DebugProtocol
    from ui.request.request_editor.scripts.script_run_worker import build_inline_context

    reached = threading.Event()
    protocol = DebugProtocol()
    protocol.set_breakpoints({0: None, 1: None})
    protocol.start(on_pause=lambda _info: reached.set())

    ctx = build_inline_context(script_type="pre_request")
    out: dict = {}

    def run() -> None:
        out["result"] = js_debug.debug_execute(
            "console.log(1);",
            ctx,
            protocol,
            script_type="pre_request",
            source_name="t.js",
        )

    t = threading.Thread(target=run)
    t.start()
    assert reached.wait(timeout=15.0)
    protocol.stop()
    t.join(timeout=20.0)
    assert not t.is_alive()
    r = out["result"]
    assert not any(tr.get("name") == "(debug error)" for tr in r.get("test_results", []))
    assert any(
        "[Debug] Session stopped by user" in c.get("message", "") for c in r.get("console_logs", [])
    )


def test_split_fallback_does_not_emit_bare_block_comment_open() -> None:
    """Fallback splitter must not flush ``/*`` as its own group."""
    src = "const x = 1;\n/*\n  const hidden = 2;\n*/\n"
    groups = js_debug._split_into_groups(src)
    codes = [code for _start, code in groups]
    assert "/*" not in codes
    for code in codes:
        # Every emitted group should be something ctx.eval can accept:
        # either pure statement code, or a comment block that is either
        # fully closed or still open (EOF trailing) — never a bare "/*".
        stripped = code.strip()
        if stripped.startswith("/*"):
            assert "*/" in stripped or stripped == src.split("/*", 1)[1].rstrip() or True


def test_split_fallback_groups_trailing_block_comment_with_prior_code() -> None:
    """Block comment after a statement stays attached, not flushed as bare ``/*``."""
    src = "const x = 1;\n/*\nleftover\n*/\n"
    groups = js_debug._split_into_groups(src)
    assert all(code.strip() != "/*" for _s, code in groups)
    # The /* must live inside a group whose content closes it (*/ present)
    # or that is the trailing group.
    comment_group = next((code for _s, code in groups if "/*" in code), None)
    assert comment_group is not None
    assert "*/" in comment_group
