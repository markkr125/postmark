"""Tests for the script debug subsystem.

Covers:
- :class:`DebugProtocol` — state machine, breakpoint management,
  checkpoint blocking/resume, stop semantics.
- :func:`inject_checkpoints` — JS checkpoint injection.
- :func:`run_debug_chain` — debug-mode chain execution in the engine.
"""

from __future__ import annotations

import threading
import time
from typing import cast

import pytest

from services.scripting import ScriptEntry, ScriptInput, ScriptOutput
from services.scripting.debug.protocol import DebugPauseInfo, DebugProtocol, DebugState, StepMode

# ===================================================================
# DebugProtocol — lifecycle
# ===================================================================


class TestDebugProtocolLifecycle:
    """State transitions: idle → running → paused → running → stopped."""

    def test_initial_state_is_idle(self) -> None:
        """Protocol starts in IDLE state."""
        proto = DebugProtocol()
        assert proto.state == DebugState.IDLE

    def test_start_sets_running(self) -> None:
        """Calling start() transitions to RUNNING."""
        proto = DebugProtocol()
        proto.start()
        assert proto.state == DebugState.RUNNING

    def test_stop_sets_stopped(self) -> None:
        """Calling stop() transitions to STOPPED."""
        proto = DebugProtocol()
        proto.start()
        proto.stop()
        assert proto.state == DebugState.STOPPED

    def test_finish_returns_to_idle(self) -> None:
        """Calling finish() returns to IDLE."""
        proto = DebugProtocol()
        proto.start()
        proto.finish()
        assert proto.state == DebugState.IDLE

    def test_restart_resets_state(self) -> None:
        """Calling start() again clears previous stop state."""
        proto = DebugProtocol()
        proto.start()
        proto.stop()
        proto.start()
        assert proto.state == DebugState.RUNNING
        assert proto._stop_requested is False

    def test_is_stopped(self) -> None:
        """is_stopped follows stop() and clears after start()."""
        proto = DebugProtocol()
        assert not proto.is_stopped
        proto.start()
        assert not proto.is_stopped
        proto.stop()
        assert proto.is_stopped
        proto.start()
        assert not proto.is_stopped


# ===================================================================
# DebugProtocol — breakpoint management
# ===================================================================


class TestDebugProtocolBreakpoints:
    """Breakpoint set/toggle/query operations."""

    def test_set_breakpoints(self) -> None:
        """set_breakpoints() replaces the entire set."""
        proto = DebugProtocol()
        proto.set_breakpoints({1: None, 5: None, 10: None})
        assert proto.breakpoints == {1: None, 5: None, 10: None}

    def test_set_breakpoints_replaces(self) -> None:
        """A second call replaces the previous set."""
        proto = DebugProtocol()
        proto.set_breakpoints({1: None, 2: None})
        proto.set_breakpoints({3: None, 4: None})
        assert proto.breakpoints == {3: None, 4: None}

    def test_update_breakpoints_matches_set(self) -> None:
        """:meth:`update_breakpoints` is the live-session equivalent of :meth:`set_breakpoints`."""
        by_set = DebugProtocol()
        by_set.set_breakpoints({1: None, 2: None, 3: None})
        by_update = DebugProtocol()
        by_update.update_breakpoints({1: None, 2: None, 3: None})
        assert by_set.breakpoints == by_update.breakpoints

    def test_toggle_adds(self) -> None:
        """toggle_breakpoint() adds a line not in the set."""
        proto = DebugProtocol()
        result = proto.toggle_breakpoint(5)
        assert result is True
        assert 5 in proto.breakpoints

    def test_toggle_removes(self) -> None:
        """toggle_breakpoint() removes a line already in the set."""
        proto = DebugProtocol()
        proto.set_breakpoints({5: None})
        result = proto.toggle_breakpoint(5)
        assert result is False
        assert 5 not in proto.breakpoints

    def test_breakpoints_returns_copy(self) -> None:
        """The breakpoints property returns a copy, not the internal set."""
        proto = DebugProtocol()
        proto.set_breakpoints({1: None, 2: None, 3: None})
        bp = proto.breakpoints
        bp[99] = None
        assert 99 not in proto.breakpoints

    def test_breakpoint_condition_round_trip(self) -> None:
        """Conditional breakpoints store and return expression text per line."""
        proto = DebugProtocol()
        proto.set_breakpoints({4: "i > 5"})
        assert proto.breakpoint_condition(4) == "i > 5"
        proto.set_breakpoint_condition(4, "count < 10")
        assert proto.breakpoint_condition(4) == "count < 10"
        proto.set_breakpoint_condition(4, None)
        assert proto.breakpoint_condition(4) is None
        assert 4 in proto.breakpoints


class TestDebugProtocolEvaluate:
    """Watch-panel evaluate() adapter wiring."""

    def test_evaluate_when_not_paused(self) -> None:
        proto = DebugProtocol()
        assert proto.evaluate("pm.response.code") == "<not paused>"

    def test_evaluate_without_callback(self) -> None:
        from services.scripting.debug.protocol import DebugState

        proto = DebugProtocol()
        with proto._lock:
            proto._state = DebugState.PAUSED
        assert proto.evaluate("x") == "<unavailable>"

    def test_evaluate_uses_callback_for_selected_frame(self) -> None:
        proto = DebugProtocol()
        seen: list[tuple[str, int]] = []

        def _cb(expr: str, frame: int) -> str:
            seen.append((expr, frame))
            return "42"

        proto.set_evaluate_callback(_cb)
        from services.scripting.debug.protocol import DebugState

        with proto._lock:
            proto._state = DebugState.PAUSED
            proto._selected_frame_index = 1
        assert proto.evaluate("pm.response.code") == "42"
        assert seen == [("pm.response.code", 1)]
        assert proto.evaluate("other", frame_index=0) == "42"
        assert seen[-1] == ("other", 0)

    def test_evaluate_surfaces_callback_errors(self) -> None:
        proto = DebugProtocol()

        def _boom(_expr: str, _frame: int) -> str:
            raise RuntimeError("bad expr")

        proto.set_evaluate_callback(_boom)
        from services.scripting.debug.protocol import DebugState

        with proto._lock:
            proto._state = DebugState.PAUSED
        assert "bad expr" in proto.evaluate("1/0")


class TestDebugProtocolCallStack:
    """Call-stack frame selection refreshes pause info."""

    def test_select_frame_updates_line_and_locals(self) -> None:
        from services.scripting.debug.protocol import CallFrame, DebugState

        proto = DebugProtocol()
        stack: list[CallFrame] = [
            CallFrame(id="0", name="inner", line=3, column=0),
            CallFrame(id="1", name="outer", line=10, column=0),
        ]
        info = {
            "line": 3,
            "source_name": "t.js",
            "local_vars": {"a": 1},
            "script_type": "pre_request",
            "env_changes": {},
            "global_changes": {},
            "call_stack": stack,
            "selected_frame_index": 0,
        }
        from services.scripting.debug import DebugPauseInfo

        pause_info: DebugPauseInfo = cast(DebugPauseInfo, info)

        def _locals(frame: int) -> dict[str, object]:
            return {"frame": frame}

        proto.set_frame_locals_callback(_locals)
        with proto._lock:
            proto._state = DebugState.PAUSED
            proto._pause_info = pause_info

        updated = proto.select_frame(1)
        assert updated is not None
        assert updated["line"] == 10
        assert updated["selected_frame_index"] == 1
        assert updated["local_vars"] == {"frame": 1}


# ===================================================================
# DebugProtocol — checkpoint blocking / resume
# ===================================================================


class TestDebugProtocolCheckpoint:
    """Checkpoint pause/resume interactions across threads."""

    def test_checkpoint_continues_without_breakpoint(self) -> None:
        """checkpoint() returns True immediately when not at a breakpoint."""
        proto = DebugProtocol()
        proto.start()
        result = proto.checkpoint(5, source_name="test.js", script_type="pre_request")
        assert result is True

    def test_checkpoint_pauses_at_breakpoint(self) -> None:
        """checkpoint() blocks at a breakpoint and resumes when resume() is called."""
        proto = DebugProtocol()
        proto.set_breakpoints({3: None})
        paused_info: list[DebugPauseInfo] = []

        def on_pause(info: DebugPauseInfo) -> None:
            paused_info.append(info)

        proto.start(on_pause=on_pause)

        # Run checkpoint in a background thread (simulating worker)
        result_holder: list[bool] = []

        def worker() -> None:
            result = proto.checkpoint(
                3,
                source_name="test.js",
                local_vars={"x": 42},
                script_type="pre_request",
            )
            result_holder.append(result)

        t = threading.Thread(target=worker)
        t.start()

        # Give the worker time to reach the pause point
        time.sleep(0.05)
        assert proto.state == DebugState.PAUSED
        assert len(paused_info) == 1
        assert paused_info[0]["line"] == 3
        assert paused_info[0]["local_vars"] == {"x": 42}
        assert paused_info[0].get("env_changes") == {}
        assert paused_info[0].get("global_changes") == {}

        # Resume and check continuation
        proto.resume(StepMode.CONTINUE)
        t.join(timeout=2)
        assert not t.is_alive()
        assert result_holder == [True]

    def test_checkpoint_stops_when_stopped(self) -> None:
        """checkpoint() returns False immediately when stop was requested."""
        proto = DebugProtocol()
        proto.start()
        proto.stop()
        result = proto.checkpoint(0, source_name="test.js")
        assert result is False

    def test_checkpoint_pauses_on_step_over(self) -> None:
        """checkpoint() pauses on every line when step mode is STEP_OVER."""
        proto = DebugProtocol()
        proto.start()

        result_holder: list[bool] = []

        def worker() -> None:
            # First checkpoint — step_over should pause
            proto._step_mode = StepMode.STEP_OVER
            result = proto.checkpoint(0, source_name="test.js")
            result_holder.append(result)

        t = threading.Thread(target=worker)
        t.start()

        time.sleep(0.05)
        assert proto.state == DebugState.PAUSED

        proto.resume(StepMode.CONTINUE)
        t.join(timeout=2)
        assert result_holder == [True]

    def test_stop_unblocks_paused_checkpoint(self) -> None:
        """stop() unblocks a thread that is paused at a checkpoint."""
        proto = DebugProtocol()
        proto.set_breakpoints({0: None})
        proto.start()

        result_holder: list[bool] = []

        def worker() -> None:
            result = proto.checkpoint(0, source_name="test.js")
            result_holder.append(result)

        t = threading.Thread(target=worker)
        t.start()

        time.sleep(0.05)
        assert proto.state == DebugState.PAUSED

        proto.stop()
        t.join(timeout=2)
        assert not t.is_alive()
        assert result_holder == [False]

    def test_pause_info_recorded(self) -> None:
        """pause_info property returns the most recent pause data."""
        proto = DebugProtocol()
        proto.set_breakpoints({5: None})
        proto.start()

        def worker() -> None:
            proto.checkpoint(
                5,
                source_name="script.js",
                local_vars={"a": 1},
                script_type="test",
            )

        t = threading.Thread(target=worker)
        t.start()

        time.sleep(0.05)
        info = proto.pause_info
        assert info is not None
        assert info["line"] == 5
        assert info["source_name"] == "script.js"
        assert info["script_type"] == "test"
        assert info.get("env_changes") == {}
        assert info.get("global_changes") == {}

        proto.resume()
        t.join(timeout=2)


# ===================================================================
# Helpers
# ===================================================================


def _make_context(
    *,
    response: dict | None = None,
    variables: dict | None = None,
) -> ScriptInput:
    """Return a minimal ``ScriptInput`` for testing."""
    return {
        "request": {
            "url": "https://example.com",
            "method": "GET",
            "headers": {},
            "body": "",
        },
        "response": response,
        "variables": variables or {},
        "environment_vars": {},
        "collection_vars": {},
        "info": {"requestName": "test"},
    }


def _deno_debug_available() -> bool:
    """Return True if a valid Deno binary is available for JS debug tests."""
    from services.scripting.runtime_settings import RuntimeSettings

    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    return bool(st.get("available"))


# ===================================================================
# inject_checkpoints
# ===================================================================


class TestInjectCheckpoints:
    """Tests for JS checkpoint line injection."""

    def test_injects_before_each_non_empty_line(self) -> None:
        """Each non-empty line gets a __pm_checkpoint call before it."""
        from services.scripting.debug.js_debug import inject_checkpoints

        source = "var x = 1;\nvar y = 2;"
        result = inject_checkpoints(source)
        lines = result.split("\n")
        # Line 0: checkpoint(0, ...), Line 1: var x = 1;
        # Line 2: checkpoint(1, ...), Line 3: var y = 2;
        assert len(lines) == 4
        assert "__pm_checkpoint(0," in lines[0]
        assert "var x = 1;" in lines[1]
        assert "__pm_checkpoint(1," in lines[2]
        assert "var y = 2;" in lines[3]

    def test_preserves_empty_lines(self) -> None:
        """Empty lines are kept without checkpoint injection."""
        from services.scripting.debug.js_debug import inject_checkpoints

        source = "a;\n\nb;"
        result = inject_checkpoints(source)
        lines = result.split("\n")
        # checkpoint(0), a;, (empty), checkpoint(2), b;
        assert len(lines) == 5
        assert lines[2] == ""
        assert "__pm_checkpoint(0," in lines[0]
        assert "__pm_checkpoint(2," in lines[3]

    def test_preserves_indentation(self) -> None:
        """Checkpoint calls match the indentation of the following line."""
        from services.scripting.debug.js_debug import inject_checkpoints

        source = "if (true) {\n  x = 1;\n}"
        result = inject_checkpoints(source)
        lines = result.split("\n")
        # checkpoint lines should match indentation
        assert lines[2].startswith("  __pm_checkpoint(1,")
        assert "x = 1;" in lines[3]

    def test_empty_source(self) -> None:
        """An empty source string produces no checkpoints."""
        from services.scripting.debug.js_debug import inject_checkpoints

        result = inject_checkpoints("")
        assert "__pm_checkpoint" not in result


# ===================================================================
# Statement grouping
# ===================================================================


class TestSplitIntoGroups:
    """Tests for the JS statement splitter."""

    def test_simple_statements(self) -> None:
        """Each single-line statement becomes its own group."""
        from services.scripting.debug.js_debug import _split_into_groups

        groups = _split_into_groups("var x = 1;\nvar y = 2;")
        assert len(groups) == 2
        assert groups[0] == (0, "var x = 1;")
        assert groups[1] == (1, "var y = 2;")

    def test_block_statement(self) -> None:
        """A brace-delimited block is a single group."""
        from services.scripting.debug.js_debug import _split_into_groups

        source = "if (true) {\n  x = 1;\n}"
        groups = _split_into_groups(source)
        assert len(groups) == 1
        assert groups[0][0] == 0
        assert "if (true)" in groups[0][1]

    def test_mixed(self) -> None:
        """Statements before and after a block are separate groups."""
        from services.scripting.debug.js_debug import _split_into_groups

        source = "var a = 1;\nif (a) {\n  a++;\n}\nvar b = 2;"
        groups = _split_into_groups(source)
        assert len(groups) == 3
        assert groups[0][0] == 0
        assert groups[1][0] == 1
        assert groups[2][0] == 4

    def test_empty_source(self) -> None:
        """Empty source returns no groups."""
        from services.scripting.debug.js_debug import _split_into_groups

        assert _split_into_groups("") == []
        assert _split_into_groups("  \n  ") == []


# ===================================================================
# Engine — run_debug_chain
# ===================================================================


class TestRunDebugChain:
    """Tests for the debug chain runner in the engine."""

    def test_skips_empty_scripts(self) -> None:
        """Empty scripts are skipped without errors."""
        from services.scripting.engine import run_debug_chain

        proto = DebugProtocol()
        proto.start()

        chain: list[ScriptEntry] = [
            {"code": "", "language": "javascript", "source_name": "empty"},
            {"code": "   ", "language": "javascript", "source_name": "blank"},
        ]
        result = run_debug_chain(chain, _make_context(), proto, script_type="pre_request")
        assert result["test_results"] == []
        assert result["console_logs"] == []

    @pytest.mark.skipif(
        not _deno_debug_available(),
        reason="Deno not available for JS step-through",
    )
    def test_runs_js_with_debug(self) -> None:
        """A simple JS script runs through the debug engine."""
        from services.scripting.engine import run_debug_chain

        proto = DebugProtocol()
        proto.start()

        chain: list[ScriptEntry] = [
            {
                "code": "pm.variables.set('result', 'ok');",
                "language": "javascript",
                "source_name": "test",
            },
        ]
        result = run_debug_chain(chain, _make_context(), proto, script_type="pre_request")
        assert result["variable_changes"].get("result") == "ok"

    @pytest.mark.skipif(
        not _deno_debug_available(),
        reason="Deno not available for JS step-through",
    )
    def test_debug_breakpoint_fires(self) -> None:
        """Breakpoints cause the protocol to pause during debug execution."""
        from services.scripting.engine import run_debug_chain

        proto = DebugProtocol()
        proto.set_breakpoints({0: None})
        paused_lines: list[int] = []

        def on_pause(info: DebugPauseInfo) -> None:
            paused_lines.append(info["line"])
            # Auto-continue after each pause
            proto.resume(StepMode.CONTINUE)

        proto.start(on_pause=on_pause)

        chain: list[ScriptEntry] = [
            {
                "code": "var x = 1;",
                "language": "javascript",
                "source_name": "bp-test",
            },
        ]

        def worker() -> None:
            run_debug_chain(chain, _make_context(), proto, script_type="pre_request")

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive()
        assert 0 in paused_lines

    @pytest.mark.skipif(
        not _deno_debug_available(),
        reason="Deno not available for JS step-through",
    )
    def test_debug_stop_halts_execution(self) -> None:
        """Stopping the debug protocol halts script execution."""
        from services.scripting.engine import run_debug_chain

        proto = DebugProtocol()
        proto.set_breakpoints({0: None})

        def on_pause(info: DebugPauseInfo) -> None:
            proto.stop()

        proto.start(on_pause=on_pause)

        chain: list[ScriptEntry] = [
            {
                "code": "var x = 1;\nvar y = 2;",
                "language": "javascript",
                "source_name": "stop-test",
            },
        ]

        def worker() -> ScriptOutput:
            return run_debug_chain(chain, _make_context(), proto, script_type="pre_request")

        results: list[ScriptOutput] = []

        def run() -> None:
            results.append(worker())

        t = threading.Thread(target=run)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive()
        # The script was stopped — no variable changes from line 2
        assert results[0].get("variable_changes", {}).get("y") is None

    def test_merges_outputs_from_chain(self) -> None:
        """Debug chain merges test results from multiple scripts."""
        from unittest.mock import patch

        from services.scripting.engine import run_debug_chain

        proto = DebugProtocol()
        proto.start()

        chain: list[ScriptEntry] = [
            {"code": "script1", "language": "javascript", "source_name": "a"},
            {"code": "script2", "language": "javascript", "source_name": "b"},
        ]

        call_count = 0

        def mock_debug_dispatch(
            script, language, context, protocol, *, script_type="", source_name=""
        ):
            nonlocal call_count
            call_count += 1
            return {
                "test_results": [{"name": f"test_{call_count}", "passed": True}],
                "console_logs": [{"message": f"log_{call_count}"}],
                "variable_changes": {f"var_{call_count}": f"val_{call_count}"},
                "request_mutations": None,
            }

        with patch(
            "services.scripting.engine._debug_dispatch",
            side_effect=mock_debug_dispatch,
        ):
            result = run_debug_chain(chain, _make_context(), proto, script_type="test")

        assert len(result["test_results"]) == 2
        assert len(result["console_logs"]) == 2
        assert result["variable_changes"]["var_1"] == "val_1"
        assert result["variable_changes"]["var_2"] == "val_2"
