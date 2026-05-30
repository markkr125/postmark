"""Tests for the CompletionEngine.

Exercises dot-path resolution, variable completions, language switching,
prefix filtering, top-level completion generation, ``pm.response.to`` chain,
``resolve_call_signature``, ``resolve_nearest_call_signature``, and rich
signature formatting.
"""

from __future__ import annotations

from services.environment_service import VariableDetail
from ui.widgets.code_editor.completion.engine import CompletionEngine
from ui.widgets.code_editor.completion.parameter_hint import format_signature_rich

# -- Construction & language switching ---------------------------------


class TestCompletionEngineConstruction:
    """Basic engine construction and language switching."""

    def test_default_language_is_javascript(self) -> None:
        """Engine defaults to JavaScript schema."""
        engine = CompletionEngine()
        assert engine.language == "javascript"

    def test_explicit_python_language(self) -> None:
        """Engine can be initialised with Python."""
        engine = CompletionEngine("python")
        assert engine.language == "python"

    def test_language_case_insensitive(self) -> None:
        """Language name is normalised to lowercase."""
        engine = CompletionEngine("JavaScript")
        assert engine.language == "javascript"

    def test_set_language_switches_schema(self) -> None:
        """Switching language updates the active schema."""
        engine = CompletionEngine("javascript")
        engine.set_language("python")
        assert engine.language == "python"

    def test_set_language_noop_for_same(self) -> None:
        """Switching to the same language is a no-op."""
        engine = CompletionEngine("javascript")
        engine.set_language("javascript")
        assert engine.language == "javascript"


# -- Dot-path completions (JavaScript) --------------------------------


class TestDotPathJS:
    """Dot-path resolution against the JavaScript schema."""

    def test_pm_dot_returns_children(self) -> None:
        """'pm.' returns pm's child members."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.")
        labels = {item.label for item in items}
        assert "response" in labels
        assert "variables" in labels
        assert "environment" in labels
        assert "test" in labels

    def test_pm_response_dot_returns_response_members(self) -> None:
        """'pm.response.' returns response members."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.response.")
        labels = {item.label for item in items}
        assert "code" in labels
        assert "status" in labels
        assert "headers" in labels
        assert "json" in labels
        assert "to" in labels

    def test_pm_response_headers_dot(self) -> None:
        """'pm.response.headers.' returns header methods."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.response.headers.")
        labels = {item.label for item in items}
        assert "get" in labels
        assert "has" in labels
        assert "toObject" in labels

    def test_console_dot_returns_methods(self) -> None:
        """'console.' returns console methods."""
        engine = CompletionEngine("javascript")
        items = engine.complete("console.")
        labels = {item.label for item in items}
        assert "log" in labels
        assert "warn" in labels
        assert "error" in labels

    def test_unknown_root_returns_empty(self) -> None:
        """Unknown root object returns no completions."""
        engine = CompletionEngine("javascript")
        items = engine.complete("unknown.")
        assert items == []

    def test_deep_unknown_path_returns_empty(self) -> None:
        """Unknown deep path returns no completions."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.response.nonexistent.")
        assert items == []

    def test_items_have_correct_types(self) -> None:
        """Completion items carry kind, type_str, and doc."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.")
        test_item = next(i for i in items if i.label == "test")
        assert test_item.kind == "method"
        assert test_item.insert_text == "test"
        assert test_item.doc  # has a description

    def test_leaf_node_returns_empty(self) -> None:
        """Completing on a leaf value (no children) returns nothing."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.response.code.")
        assert items == []

    def test_text_before_dot_path_is_ignored(self) -> None:
        """Leading text / whitespace before the dot-path is ignored."""
        engine = CompletionEngine("javascript")
        items = engine.complete("var x = pm.response.")
        labels = {item.label for item in items}
        assert "code" in labels

    def test_pm_request_headers_mutable(self) -> None:
        """'pm.request.headers.' includes mutable methods (add, remove)."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.request.headers.")
        labels = {item.label for item in items}
        assert "add" in labels
        assert "remove" in labels
        assert "upsert" in labels
        assert "get" in labels


# -- Dot-path mid-typing (prefix after dot) ---------------------------


class TestDotPathMidTypingJS:
    """``pm.v``-style contexts narrow schema children instead of top-level fallback."""

    def test_pm_v_narrows_to_variables_not_top_level(self) -> None:
        """'pm.v' suggests variables among pm children, not CryptoJS/console."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.v")
        labels = {item.label for item in items}
        assert "variables" in labels
        for bad in ("CryptoJS", "console", "postman", "atob", "pm"):
            assert bad not in labels

    def test_pm_variables_without_trailing_dot_narrows(self) -> None:
        """'pm.variables' filters pm children to the variables property."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.variables")
        labels = {item.label for item in items}
        assert labels == {"variables"}

    def test_pm_variables_s_narrows_to_set(self) -> None:
        """'pm.variables.s' narrows VariableScope methods to set."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.variables.s")
        labels = {item.label for item in items}
        assert "set" in labels
        for bad in ("CryptoJS", "console", "postman", "get", "has"):
            assert bad not in labels

    def test_pm_variables_trailing_dot_still_full_children(self) -> None:
        """'pm.variables.' returns full scope children (regression vs prefix branch)."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.variables.")
        labels = {item.label for item in items}
        assert "set" in labels
        assert "get" in labels
        assert "has" in labels
        assert "toObject" in labels


class TestDotPathMidTypingPython:
    """Same mid-dot behaviour for the Python schema."""

    def test_pm_var_narrows_to_variables(self) -> None:
        """'pm.var' narrows to variables."""
        engine = CompletionEngine("python")
        items = engine.complete("pm.var")
        labels = {item.label for item in items}
        assert "variables" in labels
        for bad in ("CryptoJS", "console", "postman", "pm"):
            assert bad not in labels

    def test_pm_variables_s_narrows_to_set(self) -> None:
        """'pm.variables.s' narrows to set."""
        engine = CompletionEngine("python")
        items = engine.complete("pm.variables.s")
        labels = {item.label for item in items}
        assert labels == {"set"}


# -- Dot-path completions (Python) ------------------------------------


class TestDotPathPython:
    """Dot-path resolution against the Python schema."""

    def test_pm_dot_returns_python_members(self) -> None:
        """'pm.' in Python returns snake_case members."""
        engine = CompletionEngine("python")
        items = engine.complete("pm.")
        labels = {item.label for item in items}
        assert "response" in labels
        assert "variables" in labels
        assert "environment" in labels

    def test_python_uses_snake_case(self) -> None:
        """Python schema uses snake_case method names."""
        engine = CompletionEngine("python")
        items = engine.complete("pm.response.headers.")
        labels = {item.label for item in items}
        # Python uses to_dict instead of toObject
        assert "to_dict" in labels
        assert "get" in labels

    def test_python_collection_variables(self) -> None:
        """Python uses snake_case 'collection_variables'."""
        engine = CompletionEngine("python")
        items = engine.complete("pm.")
        labels = {item.label for item in items}
        assert "collection_variables" in labels


# -- pm.response.to expectation chain ---------------------------------


class TestPmResponseToExpectationChainJS:
    """``pm.response.to`` uses the shared expectation chain schema."""

    def test_pm_response_to_dot_returns_chain(self) -> None:
        """``pm.response.to.`` lists chain connectors and assertion helpers."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.response.to.")
        labels = {item.label for item in items}
        assert "have" in labels
        assert "be" in labels
        assert "equal" in labels
        assert "not" in labels

    def test_pm_response_to_have_dot_still_chain(self) -> None:
        """``pm.response.to.have.`` continues the fluent chain."""
        engine = CompletionEngine("javascript")
        items = engine.complete("pm.response.to.have.")
        labels = {item.label for item in items}
        assert "status" in labels
        assert "header" in labels
        assert "equal" in labels

    def test_pm_response_to_have_status_mid_typing(self) -> None:
        """Mid-word filter on ``status`` under the chain."""
        engine = CompletionEngine("javascript")
        for fragment in ("pm.response.to.have.status", "pm.response.to.have.s"):
            items = engine.complete(fragment)
            labels = {item.label for item in items}
            assert "status" in labels


class TestPmResponseToExpectationChainPython:
    """Python schema mirrors ``pm.response.to`` chain."""

    def test_pm_response_includes_to(self) -> None:
        engine = CompletionEngine("python")
        items = engine.complete("pm.response.")
        labels = {item.label for item in items}
        assert "to" in labels

    def test_pm_response_to_dot_and_have(self) -> None:
        engine = CompletionEngine("python")
        labels_to = {item.label for item in engine.complete("pm.response.to.")}
        assert "have" in labels_to
        labels_have = {item.label for item in engine.complete("pm.response.to.have.")}
        assert "status" in labels_have

    def test_pm_response_to_have_status_mid_typing(self) -> None:
        engine = CompletionEngine("python")
        items = engine.complete("pm.response.to.have.s")
        labels = {item.label for item in items}
        assert "status" in labels


class TestResolveCallSignature:
    """``CompletionEngine.resolve_call_signature`` for parameter hints."""

    def test_status_call_js(self) -> None:
        engine = CompletionEngine("javascript")
        got = engine.resolve_call_signature("pm.response.to.have.status(")
        assert got is not None
        sig, idx = got
        assert sig == "(code: number)"
        assert idx == 0

    def test_expect_receiver_strips_simple_parens_js(self) -> None:
        engine = CompletionEngine("javascript")
        got = engine.resolve_call_signature("pm.expect(value).to.equal(")
        assert got is not None
        sig, idx = got
        assert sig == "(expected: any)"
        assert idx == 0

    def test_variables_set_second_param_js(self) -> None:
        engine = CompletionEngine("javascript")
        got = engine.resolve_call_signature('pm.variables.set("foo", ')
        assert got is not None
        sig, idx = got
        assert "value" in sig
        assert idx == 1

    def test_variables_set_python(self) -> None:
        engine = CompletionEngine("python")
        got = engine.resolve_call_signature('pm.variables.set("foo", ')
        assert got is not None
        sig, idx = got
        assert "value" in sig
        assert idx == 1

    def test_no_open_call_returns_none(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.resolve_call_signature("pm.response.code") is None

    def test_outer_call_with_inner_simple_group_strips_to_inner_method(self) -> None:
        """Receiver ``f(g()).m(`` resolves ``m`` on parent ``f`` after stripping ``(g())``."""
        engine = CompletionEngine("javascript")
        got = engine.resolve_call_signature("pm.expect(pm.response).to.equal(")
        assert got is not None
        assert got[0] == "(expected: any)"


class TestResolveNearestCallSignature:
    """``CompletionEngine.resolve_nearest_call_signature`` — Ctrl+P / past-`)` fallback."""

    def test_past_closing_paren_js_status(self) -> None:
        engine = CompletionEngine("javascript")
        got = engine.resolve_nearest_call_signature("pm.response.to.have.status(201);")
        assert got is not None
        sig, idx = got
        assert sig == "(code: number)"
        assert idx == 0

    def test_past_closing_paren_js_variables_set(self) -> None:
        engine = CompletionEngine("javascript")
        got = engine.resolve_nearest_call_signature('pm.variables.set("foo", 1);')
        assert got is not None
        sig, idx = got
        assert "value" in sig
        assert idx == 1

    def test_no_schema_match_returns_none(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.resolve_nearest_call_signature("foo();\n") is None

    def test_open_call_delegates_like_strict(self) -> None:
        engine = CompletionEngine("javascript")
        strict = engine.resolve_call_signature("pm.response.to.have.status(")
        nearest = engine.resolve_nearest_call_signature("pm.response.to.have.status(")
        assert strict == nearest

    def test_past_closing_paren_python(self) -> None:
        engine = CompletionEngine("python")
        got = engine.resolve_nearest_call_signature("pm.response.to.have.status(201);")
        assert got is not None
        assert got[0] == "(code: int)"
        assert got[1] == 0


class TestFormatSignatureRich:
    """HTML formatting for the parameter hint label."""

    def test_bolds_active_param(self) -> None:
        html = format_signature_rich("(key: string, value: any)", 1)
        assert "<b" in html and "value: any</b>" in html
        assert "key: string" in html
        assert html.startswith("(")


# -- Variable completions ---------------------------------------------


class TestVariableCompletions:
    """Tests for {{ and .get(" variable completions."""

    def test_double_brace_trigger(self) -> None:
        """'{{' returns variable completions."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "base_url": VariableDetail(
                    value="https://api.example.com", source="env", source_id=0
                ),
                "api_key": VariableDetail(value="secret", source="env", source_id=0),
            }
        )
        items = engine.complete("{{")
        labels = {item.label for item in items}
        assert "base_url" in labels
        assert "api_key" in labels

    def test_double_brace_prefix_filter(self) -> None:
        """'{{base' filters to matching variables."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "base_url": VariableDetail(
                    value="https://api.example.com", source="env", source_id=0
                ),
                "api_key": VariableDetail(value="secret", source="env", source_id=0),
            }
        )
        items = engine.complete("{{base")
        labels = {item.label for item in items}
        assert "base_url" in labels
        assert "api_key" not in labels

    def test_get_string_trigger(self) -> None:
        """'pm.variables.get("' returns variable names."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "host": VariableDetail(value="localhost", source="env", source_id=0),
            }
        )
        items = engine.complete('pm.variables.get("')
        labels = {item.label for item in items}
        assert "host" in labels

    def test_get_single_quote_trigger(self) -> None:
        """pm.variables.get(' also triggers variable completions."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "host": VariableDetail(value="localhost", source="env", source_id=0),
            }
        )
        items = engine.complete("pm.variables.get('")
        labels = {item.label for item in items}
        assert "host" in labels

    def test_environment_get_trigger(self) -> None:
        """'pm.environment.get("' triggers variable completions."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "port": VariableDetail(value="8080", source="env", source_id=0),
            }
        )
        items = engine.complete('pm.environment.get("')
        labels = {item.label for item in items}
        assert "port" in labels

    def test_empty_variable_map_returns_empty(self) -> None:
        """No variables produces no completions from {{."""
        engine = CompletionEngine()
        items = engine.complete("{{")
        assert items == []

    def test_variable_items_have_source(self) -> None:
        """Variable completions carry source and value in doc."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "url": VariableDetail(value="https://api.test", source="globals", source_id=0),
            }
        )
        items = engine.complete("{{")
        url_item = next(i for i in items if i.label == "url")
        assert "globals" in url_item.doc
        assert "https://api.test" in url_item.doc
        assert url_item.kind == "variable"


# -- Top-level completions --------------------------------------------


class TestTopLevelCompletions:
    """Tests for top_level_completions() used by Ctrl+Space."""

    def test_js_top_level_includes_pm_and_console(self) -> None:
        """JavaScript top-level includes pm and console."""
        engine = CompletionEngine("javascript")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "pm" in labels
        assert "console" in labels

    def test_python_top_level_includes_globals(self) -> None:
        """Python top-level includes pm, console, and Python globals."""
        engine = CompletionEngine("python")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "pm" in labels
        assert "console" in labels
        # Python-only globals
        assert "json_loads" in labels
        assert "json_dumps" in labels

    def test_js_top_level_excludes_python_globals(self) -> None:
        """JavaScript top-level does not include Python globals."""
        engine = CompletionEngine("javascript")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "json_loads" not in labels

    def test_js_top_level_includes_keywords(self) -> None:
        """JavaScript top-level includes language keywords."""
        engine = CompletionEngine("javascript")
        labels = {item.label for item in engine.top_level_completions()}
        assert "const" in labels
        assert "let" in labels

    def test_python_top_level_includes_keywords(self) -> None:
        """Python top-level includes language keywords."""
        engine = CompletionEngine("python")
        labels = {item.label for item in engine.top_level_completions()}
        assert "def" in labels
        assert "class" in labels


class TestIdentifierPrefix:
    """Tests for identifier_prefix (typed word before cursor)."""

    def test_suffix_con(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.identifier_prefix("con") == "con"

    def test_word_after_space(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.identifier_prefix("  con") == "con"

    def test_no_match_for_member_access(self) -> None:
        """``pm.con`` should not treat ``con`` as a free identifier prefix."""
        engine = CompletionEngine("javascript")
        assert engine.identifier_prefix("pm.con") == ""


class TestDotMemberAccessContext:
    """Dot-member access must not fall back to top-level globals (Array, etc.)."""

    def test_detects_receiver_dot(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.is_dot_member_access_context("const x = 1; npmVariableName.")

    def test_detects_partial_member(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.is_dot_member_access_context("npmVariableName.chu")

    def test_plain_identifier_is_not_dot_member(self) -> None:
        engine = CompletionEngine("javascript")
        assert not engine.is_dot_member_access_context("npmVariableName")

    def test_complete_unknown_receiver_returns_empty(self) -> None:
        engine = CompletionEngine("javascript")
        assert engine.complete("npmVariableName.") == []
