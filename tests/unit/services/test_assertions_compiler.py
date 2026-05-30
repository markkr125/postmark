"""Unit tests for declarative assertion compilation."""

from __future__ import annotations

from services.scripting.assertions_compiler import (
    SUBJECT_SUGGESTIONS,
    compile_to_js,
    compile_to_py,
)


class TestSubjectSuggestions:
    """The auto-complete suggestion list maps onto real subject grammar."""

    def test_concrete_suggestions_compile(self) -> None:
        """Every concrete suggestion (not the body-path prefix) yields a pm.test."""
        for subject in SUBJECT_SUGGESTIONS:
            if subject == "res.body.":
                continue
            rows = [
                {
                    "subject": subject,
                    "operator": "exists",
                    "expected": "",
                    "enabled": True,
                    "order_index": 0,
                }
            ]
            code = compile_to_js(rows)
            assert "pm.test" in code, f"suggestion did not compile: {subject}"


class TestAssertionsCompilerJs:
    """JavaScript compilation."""

    def test_status_equals_compiles_pm_test(self) -> None:
        rows = [
            {
                "subject": "res.status",
                "operator": "eq",
                "expected": "200",
                "enabled": True,
                "order_index": 0,
            }
        ]
        code = compile_to_js(rows)
        assert 'globalThis.__pm_test_source_name = "declarative"' in code
        assert "pm.test" in code
        assert "pm.response.code" in code
        assert ".to.equal(200)" in code
        assert "globalThis.__pm_test_source_name = null" in code

    def test_disabled_rows_are_skipped(self) -> None:
        rows = [
            {
                "subject": "res.status",
                "operator": "eq",
                "expected": "200",
                "enabled": False,
                "order_index": 0,
            }
        ]
        code = compile_to_js(rows)
        assert "pm.test" not in code

    def test_json_path_exists(self) -> None:
        rows = [
            {
                "subject": "res.body.user.id",
                "operator": "exists",
                "expected": "",
                "enabled": True,
                "order_index": 0,
            }
        ]
        code = compile_to_js(rows)
        assert 'jsonBody("user.id")' in code

    def test_header_contains(self) -> None:
        rows = [
            {
                "subject": 'res.headers["Content-Type"]',
                "operator": "contains",
                "expected": "json",
                "enabled": True,
                "order_index": 0,
            }
        ]
        code = compile_to_js(rows)
        assert "Content-Type" in code
        assert ".to.include" in code


class TestAssertionsCompilerPy:
    """Python compilation."""

    def test_status_equals_compiles_pm_test(self) -> None:
        rows = [
            {
                "subject": "res.status",
                "operator": "eq",
                "expected": "201",
                "enabled": True,
                "order_index": 0,
            }
        ]
        code = compile_to_py(rows)
        assert 'pm._test_source_name = "declarative"' in code
        assert "pm.test" in code
        assert "pm.response.code" in code
        assert ".to.equal(201)" in code
        assert "pm._test_source_name = None" in code

    def test_time_less_than(self) -> None:
        rows = [
            {
                "subject": "res.time",
                "operator": "lt",
                "expected": "500",
                "enabled": True,
                "order_index": 0,
            }
        ]
        code = compile_to_py(rows)
        assert "pm.response.response_time" in code
        assert ".to.be.below(500)" in code

    def test_invalid_subject_is_skipped(self) -> None:
        rows = [
            {
                "subject": "unknown.field",
                "operator": "eq",
                "expected": "1",
                "enabled": True,
                "order_index": 0,
            }
        ]
        code = compile_to_py(rows)
        assert "pm.test" not in code
