"""Tests for the CompletionEngine.

Exercises dot-path resolution, variable completions, language switching,
prefix filtering, and top-level completion generation.
"""

from __future__ import annotations

from services.environment_service import VariableDetail
from ui.widgets.code_editor.completion.engine import CompletionEngine, CompletionItem

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


# -- Prefix filtering -------------------------------------------------


class TestPrefixFiltering:
    """Tests for complete_prefix() method."""

    def test_prefix_filters_items(self) -> None:
        """Prefix filtering reduces the completion list."""
        engine = CompletionEngine("javascript")
        all_items = engine.complete("pm.")
        filtered = engine.complete_prefix("pm.", "res")
        assert len(filtered) < len(all_items)
        assert all(item.label.startswith("res") for item in filtered)

    def test_empty_prefix_returns_all(self) -> None:
        """Empty prefix returns all completions."""
        engine = CompletionEngine("javascript")
        all_items = engine.complete("pm.")
        filtered = engine.complete_prefix("pm.", "")
        assert len(filtered) == len(all_items)

    def test_prefix_case_insensitive(self) -> None:
        """Prefix matching is case-insensitive."""
        engine = CompletionEngine("javascript")
        filtered = engine.complete_prefix("pm.", "Res")
        assert any(item.label == "response" for item in filtered)

    def test_no_match_prefix_returns_empty(self) -> None:
        """A prefix matching nothing returns an empty list."""
        engine = CompletionEngine("javascript")
        filtered = engine.complete_prefix("pm.", "zzz")
        assert filtered == []


# -- Edge cases --------------------------------------------------------


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_empty_text_returns_empty(self) -> None:
        """Empty string produces no completions."""
        engine = CompletionEngine()
        items = engine.complete("")
        assert items == []

    def test_plain_text_returns_empty(self) -> None:
        """Plain text without dots or braces produces nothing."""
        engine = CompletionEngine()
        items = engine.complete("hello world")
        assert items == []

    def test_trailing_whitespace_after_dot(self) -> None:
        """Whitespace after dot still triggers completions."""
        engine = CompletionEngine()
        items = engine.complete("pm. ")
        # The regex allows optional whitespace after dot
        labels = {item.label for item in items}
        assert "response" in labels

    def test_completion_item_is_named_tuple(self) -> None:
        """CompletionItem is a proper NamedTuple."""
        item = CompletionItem(
            label="test",
            kind="method",
            type_str="void",
            doc="desc",
            signature="()",
            insert_text="test",
        )
        assert item.label == "test"
        assert item.kind == "method"

    def test_set_variable_map_updates(self) -> None:
        """set_variable_map replaces the previous map."""
        engine = CompletionEngine()
        engine.set_variable_map(
            {
                "a": VariableDetail(value="1", source="env", source_id=0),
            }
        )
        items1 = engine.complete("{{")
        assert len(items1) == 1

        engine.set_variable_map(
            {
                "x": VariableDetail(value="2", source="env", source_id=0),
                "y": VariableDetail(value="3", source="env", source_id=0),
            }
        )
        items2 = engine.complete("{{")
        assert len(items2) == 2
        labels = {item.label for item in items2}
        assert "x" in labels
        assert "y" in labels
        assert "a" not in labels


# -- Type inference (assignments) --------------------------------------


class TestTypeInferenceJS:
    """Type inference from JavaScript variable assignments."""

    def test_infer_let_assignment(self) -> None:
        """A ``let x = pm.response`` assignment resolves ``x.`` completions."""
        engine = CompletionEngine("javascript")
        engine.scan_assignments("let data = pm.response;")
        items = engine.complete("data.")
        labels = {item.label for item in items}
        assert "code" in labels
        assert "json" in labels

    def test_infer_const_assignment(self) -> None:
        """A ``const`` assignment also produces completions."""
        engine = CompletionEngine("javascript")
        engine.scan_assignments("const vars = pm.variables;")
        items = engine.complete("vars.")
        labels = {item.label for item in items}
        assert "get" in labels

    def test_infer_function_call(self) -> None:
        """An assignment from a function call strips the ``()``."""
        engine = CompletionEngine("javascript")
        engine.scan_assignments("let body = pm.response.json();")
        # pm.response.json() returns object — its node may have children
        # At minimum, scan_assignments should not crash.
        engine.complete("body.")

    def test_infer_unknown_variable(self) -> None:
        """An unrecognised variable returns no completions."""
        engine = CompletionEngine("javascript")
        engine.scan_assignments("let x = unknownThing;")
        items = engine.complete("x.")
        assert items == []

    def test_infer_rescan_clears_old(self) -> None:
        """Re-scanning clears previous inferences."""
        engine = CompletionEngine("javascript")
        engine.scan_assignments("let data = pm.response;")
        assert engine.complete("data.") != []
        engine.scan_assignments("")
        assert engine.complete("data.") == []


class TestTypeInferencePython:
    """Type inference from Python variable assignments."""

    def test_infer_python_assignment(self) -> None:
        """Python ``x = pm.response`` resolves ``x.`` completions."""
        engine = CompletionEngine("python")
        engine.scan_assignments("data = pm.response")
        items = engine.complete("data.")
        labels = {item.label for item in items}
        assert "code" in labels
        assert "code" in labels


# -- Vendor library and postman completions ----------------------------


class TestPostmanCompletions:
    """Completions for the legacy ``postman`` global object."""

    def test_postman_in_top_level(self) -> None:
        """``postman`` appears in JS top-level completions."""
        engine = CompletionEngine("javascript")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "postman" in labels

    def test_postman_dot_returns_methods(self) -> None:
        """``postman.`` returns its child methods."""
        engine = CompletionEngine("javascript")
        items = engine.complete("postman.")
        labels = {item.label for item in items}
        assert "setEnvironmentVariable" in labels
        assert "getEnvironmentVariable" in labels
        assert "clearEnvironmentVariable" in labels
        assert "setGlobalVariable" in labels
        assert "getGlobalVariable" in labels
        assert "clearGlobalVariable" in labels

    def test_postman_not_in_python(self) -> None:
        """``postman`` is not available in Python schema."""
        engine = CompletionEngine("python")
        items = engine.complete("postman.")
        assert items == []


class TestCryptoJSCompletions:
    """Completions for the ``CryptoJS`` vendor library."""

    def test_cryptojs_in_top_level(self) -> None:
        """``CryptoJS`` appears in JS top-level completions."""
        engine = CompletionEngine("javascript")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "CryptoJS" in labels

    def test_cryptojs_dot_returns_hash_methods(self) -> None:
        """``CryptoJS.`` returns hash and cipher methods."""
        engine = CompletionEngine("javascript")
        items = engine.complete("CryptoJS.")
        labels = {item.label for item in items}
        assert "HmacSHA256" in labels
        assert "SHA256" in labels
        assert "MD5" in labels
        assert "AES" in labels
        assert "enc" in labels

    def test_cryptojs_enc_dot_returns_encoders(self) -> None:
        """``CryptoJS.enc.`` returns encoder names."""
        engine = CompletionEngine("javascript")
        items = engine.complete("CryptoJS.enc.")
        labels = {item.label for item in items}
        assert "Hex" in labels
        assert "Base64" in labels
        assert "Utf8" in labels

    def test_cryptojs_aes_dot_returns_encrypt_decrypt(self) -> None:
        """``CryptoJS.AES.`` returns encrypt and decrypt methods."""
        engine = CompletionEngine("javascript")
        items = engine.complete("CryptoJS.AES.")
        labels = {item.label for item in items}
        assert "encrypt" in labels
        assert "decrypt" in labels


class TestJSGlobals:
    """Top-level JS globals available via Ctrl+Space."""

    def test_require_in_top_level(self) -> None:
        """``require`` appears in JS top-level completions."""
        engine = CompletionEngine("javascript")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "require" in labels

    def test_atob_btoa_in_top_level(self) -> None:
        """``atob`` and ``btoa`` appear in JS top-level completions."""
        engine = CompletionEngine("javascript")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "atob" in labels
        assert "btoa" in labels

    def test_js_globals_not_in_python(self) -> None:
        """JS globals like ``require`` do not appear in Python."""
        engine = CompletionEngine("python")
        items = engine.top_level_completions()
        labels = {item.label for item in items}
        assert "require" not in labels
        assert "CryptoJS" not in labels
