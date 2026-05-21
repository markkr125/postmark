"""CDP scope materialization, hover merge, and Deno debug bundle shape tests."""

from __future__ import annotations

from typing import Any

from services.scripting import ScriptInput


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


class TestDenoMaterializeRemoteValue:
    """``_materialize_remote_value`` reduces CDP RemoteObject dicts for display."""

    def test_primitives(self) -> None:
        from services.scripting.debug.deno_scope import _materialize_remote_value

        assert (
            _materialize_remote_value(
                {"type": "string", "value": "hi"},
            )
            == "hi"
        )
        assert _materialize_remote_value({"type": "number", "value": 42}) == 42
        assert _materialize_remote_value({"type": "boolean", "value": True}) is True

    def test_undefined_and_null(self) -> None:
        from services.scripting.debug.deno_scope import _materialize_remote_value

        assert _materialize_remote_value({"type": "undefined"}) is None
        assert (
            _materialize_remote_value(
                {"type": "object", "subtype": "null"},
            )
            is None
        )

    def test_object_function_symbol(self) -> None:
        from services.scripting.debug.deno_scope import _materialize_remote_value

        assert (
            _materialize_remote_value(
                {"type": "object", "description": "Object {a: 1}"},
            )
            == "Object {a: 1}"
        )
        assert (
            _materialize_remote_value(
                {"type": "function", "description": "function foo() {}"},
            )
            == "function foo() {}"
        )
        assert (
            _materialize_remote_value(
                {"type": "symbol", "description": "Symbol(s)"},
            )
            == "Symbol(s)"
        )


class TestPmClassnameKeyLiteral:
    """``_PM_CLASSNAME_KEY`` must stay aligned with the UI tree sentinel."""

    def test_matches_widget_constant(self) -> None:
        from services.scripting.debug import deno_scope
        from ui.widgets.debug_value_tree import CLASSNAME_KEY

        assert deno_scope._PM_CLASSNAME_KEY == CLASSNAME_KEY


class TestCollectCallFrameScopes:
    """``_collect_call_frame_scopes`` flattens innermost-first, ignores bad rows."""

    def test_innermost_binding_wins(self) -> None:
        from services.scripting.debug.deno_scope import _collect_call_frame_scopes

        class _FakeCdp:
            def req(self, method: str, params: dict) -> dict:
                oid = params.get("objectId")
                if oid == "inner":
                    return {
                        "result": [
                            {
                                "name": "a",
                                "value": {
                                    "type": "number",
                                    "value": 1,
                                },
                            },
                            {
                                "name": "b",
                                "value": {
                                    "type": "number",
                                    "value": 2,
                                },
                            },
                        ],
                    }
                if oid == "outer":
                    return {
                        "result": [
                            {
                                "name": "b",
                                "value": {
                                    "type": "number",
                                    "value": 9,
                                },
                            },
                            {
                                "name": "c",
                                "value": {
                                    "type": "number",
                                    "value": 3,
                                },
                            },
                        ],
                    }
                return {"result": []}

        m = {
            "params": {
                "callFrames": [
                    {
                        "scopeChain": [
                            {
                                "type": "block",
                                "object": {"objectId": "inner"},
                            },
                            {
                                "type": "local",
                                "object": {"objectId": "outer"},
                            },
                        ],
                    }
                ],
            }
        }
        flat, scopes = _collect_call_frame_scopes(m, _FakeCdp())  # type: ignore[arg-type]
        assert flat == {"a": 1, "b": 2, "c": 3}
        assert len(scopes) == 2
        assert scopes[0]["name"] == "Block"
        assert scopes[1]["name"] == "Local"

    def test_module_scope_collected(self) -> None:
        """ES module scope (``.mjs`` debug bundle) exposes top-level ``const``/``let``."""
        from services.scripting.debug.deno_scope import _collect_call_frame_scopes

        class _FakeCdp:
            def req(self, method: str, params: dict) -> dict:
                oid = params.get("objectId")
                if oid == "mod":
                    return {
                        "result": [
                            {
                                "name": "randomId",
                                "value": {"type": "number", "value": 42},
                            },
                            {
                                "name": "timestamp",
                                "value": {"type": "string", "value": "2020-01-01"},
                            },
                        ],
                    }
                return {"result": []}

        m = {
            "params": {
                "callFrames": [
                    {
                        "functionName": "",
                        "scopeChain": [
                            {
                                "type": "module",
                                "object": {"objectId": "mod"},
                            },
                        ],
                    }
                ],
            }
        }
        flat, scopes = _collect_call_frame_scopes(m, _FakeCdp())  # type: ignore[arg-type]
        assert flat == {"randomId": 42, "timestamp": "2020-01-01"}
        assert len(scopes) == 1
        assert scopes[0]["name"] == "Module"

    def test_pm_binding_expanded_via_nested_get_properties(self) -> None:
        """Module-scope ``pm`` object is expanded with nested ``Runtime.getProperties``."""
        from services.scripting.debug.deno_scope import (
            _PM_CLASSNAME_KEY,
            _collect_call_frame_scopes,
        )

        class _FakeCdp:
            def req(self, method: str, params: dict) -> dict:
                oid = params.get("objectId")
                if oid == "mod":
                    return {
                        "result": [
                            {
                                "name": "pm",
                                "value": {
                                    "type": "object",
                                    "description": "Object",
                                    "objectId": "pm-obj",
                                },
                            },
                        ],
                    }
                if oid == "pm-obj":
                    return {
                        "result": [
                            {
                                "name": "response",
                                "value": {
                                    "type": "object",
                                    "description": "PmResponse",
                                    "objectId": "resp-obj",
                                },
                            },
                        ],
                    }
                if oid == "resp-obj":
                    return {
                        "result": [
                            {
                                "name": "code",
                                "value": {"type": "number", "value": 201},
                            },
                        ],
                    }
                return {"result": []}

        m = {
            "params": {
                "callFrames": [
                    {
                        "functionName": "",
                        "scopeChain": [
                            {"type": "module", "object": {"objectId": "mod"}},
                        ],
                    }
                ],
            }
        }
        flat, scopes = _collect_call_frame_scopes(m, _FakeCdp())  # type: ignore[arg-type]
        pm_val = flat["pm"]
        assert isinstance(pm_val, dict)
        assert pm_val["response"]["code"] == 201
        assert pm_val["response"][_PM_CLASSNAME_KEY] == "PmResponse"
        assert scopes[0]["vars"]["pm"] == pm_val

    def test_module_scope_skipped_inside_user_debug_wrapper(self) -> None:
        """``module`` is skipped when paused in ``__pm_debugUserScript`` (bundle noise)."""
        from services.scripting.debug.deno_scope import _collect_call_frame_scopes

        class _FakeCdp:
            def __init__(self) -> None:
                self.object_ids: list[str] = []

            def req(self, method: str, params: dict) -> dict:
                oid = params.get("objectId")
                if isinstance(oid, str):
                    self.object_ids.append(oid)
                if oid == "loc":
                    return {
                        "result": [
                            {
                                "name": "randomId",
                                "value": {"type": "number", "value": 9},
                            },
                        ],
                    }
                if oid == "mod":
                    return {
                        "result": [
                            {
                                "name": "__CONSOLE_LIMIT",
                                "value": {"type": "number", "value": 200},
                            },
                        ],
                    }
                return {"result": []}

        m = {
            "params": {
                "callFrames": [
                    {
                        "functionName": "__pm_debugUserScript",
                        "scopeChain": [
                            {
                                "type": "local",
                                "object": {"objectId": "loc"},
                            },
                            {
                                "type": "module",
                                "object": {"objectId": "mod"},
                            },
                        ],
                    }
                ],
            }
        }
        cdp = _FakeCdp()
        flat, scopes = _collect_call_frame_scopes(m, cdp)  # type: ignore[arg-type]
        assert flat == {"randomId": 9}
        assert len(scopes) == 1
        assert scopes[0]["name"] == "Local"
        assert "mod" not in cdp.object_ids

    def test_module_scope_filters_double_underscore_when_included(self) -> None:
        """When ``module`` is collected, strip ``__*`` names from the module record."""
        from services.scripting.debug.deno_scope import _collect_call_frame_scopes

        class _FakeCdp:
            def req(self, method: str, params: dict) -> dict:
                return {
                    "result": [
                        {
                            "name": "__internal",
                            "value": {"type": "number", "value": 1},
                        },
                        {
                            "name": "userVar",
                            "value": {"type": "number", "value": 2},
                        },
                    ],
                }

        m = {
            "params": {
                "callFrames": [
                    {
                        "functionName": "",
                        "scopeChain": [
                            {
                                "type": "module",
                                "object": {"objectId": "m"},
                            },
                        ],
                    }
                ],
            }
        }
        flat, scopes = _collect_call_frame_scopes(m, _FakeCdp())  # type: ignore[arg-type]
        assert flat == {"userVar": 2}
        assert scopes[0]["vars"] == {"userVar": 2}


class TestMergeDebugHoverValues:
    """``_merge_debug_hover_values`` — precedence for editor hover locals."""

    def test_structured_then_lexical_then_env(self) -> None:
        from ui.main_window.send_pipeline import _merge_debug_hover_values

        out = _merge_debug_hover_values(
            {
                "local_vars": {
                    "pm": {"x": 1, "a": "pm_a"},
                    "globals": {"y": 2, "a": "gl_a"},
                    "locals": {"a": "lex_a", "z": 3},
                    "scopes": [],
                },
                "env_changes": {"e": 4},
                "global_changes": {"a": "workspace_a", "g": 5},
            }
        )
        # globals, pm, then lexical a; env then global_changes (last wins a)
        assert out["x"] == 1
        assert out["y"] == 2
        assert out["a"] == "workspace_a"
        assert out["z"] == 3
        assert out["e"] == 4
        assert out["g"] == 5

    def test_legacy_flat_skips_scopes_and_merges_lexical(self) -> None:
        from ui.main_window.send_pipeline import _merge_debug_hover_values

        out = _merge_debug_hover_values(
            {
                "local_vars": {
                    "foo": 1,
                    "locals": {"foo": 2, "bar": 3},
                    "scopes": [{"name": "Block", "vars": {"nope": 0}}],
                },
            }
        )
        assert out["foo"] == 2
        assert out["bar"] == 3
        assert "scopes" not in out
        assert "nope" not in out


class TestDebugHoverRootObjects:
    """``_debug_hover_root_objects`` — whole ``pm`` / ``console`` for editor hover."""

    def test_extracts_pm_and_console_dicts(self) -> None:
        from ui.main_window.send_pipeline import _debug_hover_root_objects

        out = _debug_hover_root_objects(
            {
                "local_vars": {
                    "pm": {"response": {"code": 200}},
                    "globals": {"console": {"assert": "fn"}},
                },
            }
        )
        assert out["pm"] == {"response": {"code": 200}}
        assert out["console"] == {"assert": "fn"}

    def test_skips_non_dict_console(self) -> None:
        from ui.main_window.send_pipeline import _debug_hover_root_objects

        assert _debug_hover_root_objects({"local_vars": {"globals": {"console": "not-dict"}}}) == {}


class TestDebugBundleUserScriptWrapper:
    """Debug bundle shape for Deno step-through (lexical scope in CDP)."""

    def test_debug_bundle_wraps_user_script_in_named_function(self) -> None:
        from services.scripting.deno_runtime import build_debug_bundle_text

        txt, _needs_net, _local = build_debug_bundle_text("const x = 1;", _make_context())
        assert "function __pm_debugUserScript()" in txt
        assert "const x = 1;" in txt
        assert "__pm_debugUserScript();" in txt
        assert "globalThis.__pm_baseline_json = __pm_baseline_json" in txt


class TestEvaluationResultString:
    """CDP evaluate responses nest the RemoteObject under ``result``."""

    def test_unwraps_nested_remote_object_string(self) -> None:
        from services.scripting.debug.js_debug import cdp_evaluation_result_string

        wrapped = {"result": {"type": "string", "value": '{"pm":{},"globals":{}}'}}
        assert cdp_evaluation_result_string(wrapped) == '{"pm":{},"globals":{}}'

    def test_top_level_remote_object_still_works(self) -> None:
        from services.scripting.debug.js_debug import cdp_evaluation_result_string

        flat = {"type": "string", "value": "ok"}
        assert cdp_evaluation_result_string(flat) == "ok"


class TestBootstrapGlobalThisMirror:
    """``pm_bootstrap`` mirrors ``__pm_state`` / ``pm`` for CDP ``evaluateOnCallFrame``."""

    def test_bootstrap_assigns_pm_state_to_global_this(self) -> None:
        from services.scripting.js_runtime import _get_bootstrap

        text = _get_bootstrap()
        assert "globalThis.__pm_state = __pm_state" in text
        assert "globalThis.pm = pm" in text


class TestCdpBreakEditorLines:
    """``_cdp_break_editor_lines`` merges top-level group starts with editor breakpoints."""

    def test_unions_g0s_and_in_range_editor_breakpoints(self) -> None:
        from services.scripting.debug.deno_debug import _cdp_break_editor_lines

        assert _cdp_break_editor_lines({0, 10}, {3: None, 4: None}, 20) == [
            (0, None),
            (3, None),
            (4, None),
            (10, None),
        ]

    def test_out_of_range_breakpoints_clipped(self) -> None:
        from services.scripting.debug.deno_debug import _cdp_break_editor_lines

        assert _cdp_break_editor_lines({0}, {-1: None, 99: None, 100: None}, 10) == [(0, None)]

    def test_non_positive_n_user_lines_only_g0s(self) -> None:
        from services.scripting.debug.deno_debug import _cdp_break_editor_lines

        assert _cdp_break_editor_lines({2, 0}, {5: None, 7: None}, 0) == [(0, None), (2, None)]

    def test_conditional_breakpoint_carries_condition(self) -> None:
        from services.scripting.debug.deno_debug import _cdp_break_editor_lines

        assert _cdp_break_editor_lines({0}, {3: "x > 1"}, 10) == [(0, None), (3, "x > 1")]


class TestSourceMapDecode:
    """Source-map reverse mapping for ``.ts`` debug bundles (Deno transpile)."""

    def test_vlq_decode_basic(self) -> None:
        from services.scripting.debug.deno_debug import _vlq_decode

        # "AAAA" → four zero VLQs at columns 0,1,2,3
        v, i = _vlq_decode("A", 0)
        assert v == 0 and i == 1
        # "C" = 1 << 1 = 2 (positive)
        v, i = _vlq_decode("C", 0)
        assert v == 1 and i == 1
        # "D" = (1 << 1) | 1 → -1 (sign bit set)
        v, i = _vlq_decode("D", 0)
        assert v == -1 and i == 1

    def test_build_source_map_round_trip(self) -> None:
        from services.scripting.debug.deno_debug import _build_source_map

        # Hand-crafted: src lines 0,1,2 each map to one gen line in order.
        # Mapping segment shape: gen_col, src_idx, src_line, src_col.
        # "AAAA" = [0,0,0,0]; "AACA" = [0,0,1,0]; "AACA" = [0,0,1,0] (relative).
        mappings = "AAAA;AACA;AACA"
        src_to_gen, gen_to_src = _build_source_map(mappings)
        assert gen_to_src[0] == 0
        assert gen_to_src[1] == 1
        assert gen_to_src[2] == 2
        assert src_to_gen[0] == [0]
        assert src_to_gen[1] == [1]
        assert src_to_gen[2] == [2]

    def test_decode_inline_source_map_data_url(self) -> None:
        import base64
        import json

        from services.scripting.debug.deno_debug import _decode_inline_source_map

        sm = {"version": 3, "sources": ["x.ts"], "mappings": "AAAA"}
        b64 = base64.b64encode(json.dumps(sm).encode()).decode()
        url = f"data:application/json;base64,{b64}"
        decoded = _decode_inline_source_map(url)
        assert decoded == sm

    def test_decode_inline_source_map_rejects_non_data_url(self) -> None:
        from services.scripting.debug.deno_debug import _decode_inline_source_map

        assert _decode_inline_source_map("file:///x.ts.map") is None
        assert _decode_inline_source_map("") is None

    def test_src_to_gen_line_passthrough_when_no_map(self) -> None:
        from services.scripting.debug.deno_debug import _src_to_gen_line

        assert _src_to_gen_line(None, 42) == 42
        assert _src_to_gen_line({}, 42) == 42
        assert _src_to_gen_line({42: [17]}, 42) == 17

    def test_gen_to_src_line_passthrough_when_no_map(self) -> None:
        from services.scripting.debug.deno_debug import _gen_to_src_line

        assert _gen_to_src_line(None, 42) == 42
        assert _gen_to_src_line({}, 42) == 42
        assert _gen_to_src_line({17: 42}, 17) == 42


class _RecordingCdp:
    """Minimal CDP stand-in for :func:`_process_one_paused` tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def req(self, method: str, params: dict[str, Any] | None) -> Any:
        p = dict(params or {})
        self.calls.append((method, p))
        if method == "Debugger.evaluateOnCallFrame":
            return {"result": {"type": "string", "value": "{}"}}
        if method == "Runtime.evaluate":
            return {"result": {"type": "string", "value": "{}"}}
        if method == "Runtime.getProperties":
            return {"result": []}
        return {}


class TestProcessOnePausedUserLineRange:
    """Pauses inside the user script (not only top-level group starts) reach ``checkpoint``."""

    def _paused_at_bundle_line(self, bundle_line: int) -> dict:
        return {
            "params": {
                "callFrames": [
                    {
                        "callFrameId": "cf0",
                        "functionName": "__pm_debugUserScript",
                        "location": {"lineNumber": bundle_line},
                        "scopeChain": [],
                    },
                ],
            },
        }

    def test_before_user_script_only_resumes(self) -> None:
        from services.scripting.debug.deno_debug import _process_one_paused
        from services.scripting.debug.protocol import DebugProtocol

        proto = DebugProtocol()
        proto.start()
        c = _RecordingCdp()
        u0 = 100
        m = self._paused_at_bundle_line(50)
        assert _process_one_paused(m, c, proto, u0, 20, "(test)", "test") is True
        methods = [x[0] for x in c.calls]
        assert "Debugger.evaluateOnCallFrame" not in methods
        assert methods.count("Debugger.resume") == 1

    def test_after_user_script_only_resumes(self) -> None:
        from services.scripting.debug.deno_debug import _process_one_paused
        from services.scripting.debug.protocol import DebugProtocol

        proto = DebugProtocol()
        proto.start()
        c = _RecordingCdp()
        u0 = 100
        n_user = 5
        m = self._paused_at_bundle_line(u0 + n_user + 50)
        assert _process_one_paused(m, c, proto, u0, n_user, "(test)", "test") is True
        assert "Debugger.evaluateOnCallFrame" not in [x[0] for x in c.calls]

    def test_inside_user_script_calls_evaluate_and_checkpoint(self) -> None:
        from services.scripting.debug.deno_debug import _process_one_paused
        from services.scripting.debug.protocol import DebugProtocol

        proto = DebugProtocol()
        proto.start()
        c = _RecordingCdp()
        u0 = 100
        el = 3
        m = self._paused_at_bundle_line(u0 + el)
        assert _process_one_paused(m, c, proto, u0, 20, "(test)", "test") is True
        methods = [x[0] for x in c.calls]
        assert "Debugger.evaluateOnCallFrame" in methods
        assert "Debugger.resume" in methods
