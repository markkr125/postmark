"""Tests for scripting API quickref generation."""

from __future__ import annotations

import re

from database.data_paths import project_root
from services.ai.chat.app_wiki.quickref import (
    _parse_pm_dts,
    _parse_pm_pyi,
    write_scripting_quickrefs,
)
from services.ai.chat.app_wiki.sandbox_globals import (
    JS_SANDBOX_GLOBALS,
    PYTHON_SANDBOX_GLOBALS,
)


def test_parse_pm_dts_includes_expect() -> None:
    """DTS parser finds top-level pm functions."""
    text = (project_root() / "data/lsp/stubs/pm.d.ts").read_text(encoding="utf-8")
    members = _parse_pm_dts(text)
    assert "pm.expect" in members
    assert "pm.test" in members
    assert any(m.startswith("pm.collectionVariables.") for m in members)


def test_parse_pm_pyi_includes_expect() -> None:
    """PYI parser finds flat pm methods on ``_Pm``."""
    text = (project_root() / "data/lsp/stubs/pm.pyi").read_text(encoding="utf-8")
    members = _parse_pm_pyi(text)
    assert "pm.expect" in members
    assert "pm.test" in members
    assert "pm.sendRequest" in members


def test_write_scripting_quickrefs_is_deterministic() -> None:
    """Regenerating quickref produces stable member lists."""
    root = project_root()
    first = write_scripting_quickrefs(root)
    write_scripting_quickrefs(root)
    assert first
    for path in first:
        text1 = path.read_text(encoding="utf-8")
        text2 = path.read_text(encoding="utf-8")
        members1 = re.findall(r"^- `([^`]+)`", text1, flags=re.MULTILINE)
        members2 = re.findall(r"^- `([^`]+)`", text2, flags=re.MULTILINE)
        assert members1 == members2
        assert members1


def test_python_quickref_lists_sandbox_globals() -> None:
    """Python quickref surfaces bare globals like datetime_now (no pm. prefix)."""
    root = project_root()
    written = write_scripting_quickrefs(root)
    py = next(p for p in written if p.name == "python-quickref.md")
    text = py.read_text(encoding="utf-8")
    assert "Global helpers" in text
    assert "- `datetime_now()`" in text
    assert "- `uuid_v4()`" in text
    # The misuse the model made must NOT appear as a listed member bullet.
    assert "- `pm.datetime_now" not in text


def test_js_quickref_lists_sandbox_globals() -> None:
    """JS quickref surfaces require/atob/btoa globals."""
    root = project_root()
    written = write_scripting_quickrefs(root)
    js = next(p for p in written if p.name == "javascript-quickref.md")
    text = js.read_text(encoding="utf-8")
    assert "Global helpers" in text
    assert "require(module)" in text


def test_sandbox_globals_match_prose_docs() -> None:
    """Curated sandbox globals stay in sync with the prose API docs."""
    root = project_root()
    py_doc = (root / "docs/scripting/python-api.md").read_text(encoding="utf-8")
    for name, _sig, _doc in PYTHON_SANDBOX_GLOBALS:
        assert name in py_doc, f"{name} missing from python-api.md"
    js_doc = (root / "docs/scripting/javascript-api.md").read_text(encoding="utf-8")
    for name, _sig, _doc in JS_SANDBOX_GLOBALS:
        assert name in js_doc, f"{name} missing from javascript-api.md"
