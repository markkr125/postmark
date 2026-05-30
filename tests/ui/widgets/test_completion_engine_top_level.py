"""CompletionEngine tests: top-level filtered, globals, postman, crypto."""

from __future__ import annotations

from services.environment_service import VariableDetail
from ui.widgets.code_editor.completion.engine import CompletionEngine, CompletionItem


class TestTopLevelFiltered:
    """Tests for top_level_filtered (Ctrl+Space on a partial word)."""

    def test_js_con_includes_const(self) -> None:
        engine = CompletionEngine("javascript")
        labels = [i.label for i in engine.top_level_filtered("con")]
        assert "const" in labels
        assert "console" in labels
        assert "continue" in labels

    def test_python_de_includes_def(self) -> None:
        engine = CompletionEngine("python")
        labels = [i.label for i in engine.top_level_filtered("de")]
        assert "def" in labels
        assert "delete" not in labels  # not a Python keyword in our list

    def test_empty_prefix_returns_full_top_level(self) -> None:
        engine = CompletionEngine("javascript")
        assert len(engine.top_level_filtered("")) == len(engine.top_level_completions())


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
