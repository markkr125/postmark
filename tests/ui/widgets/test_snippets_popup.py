"""Tests for script snippet JSON loading and :class:`~ui.widgets.snippets.popup.SnippetsPopup`.

Test matrix
-----------
**Loader**

- ``test_load_javascript_snippets`` — ``javascript.json`` loads; categories
  include Workflows and Variables; HTTP snippet references ``pm.sendRequest``.
- ``test_load_javascript_includes_tests_and_pre_request_categories`` — Tests and
  Pre-request helpers rows reference status/body/oneOf-style APIs.
- ``test_typescript_falls_back_to_javascript`` — TypeScript uses the JS file.
- ``test_load_python_snippets_use_snake_case`` — Python bodies use snake_case.
- ``test_load_python_includes_tests_and_pre_request_categories`` — Python mirrors
  Tests / Pre-request helpers with ``to.be.least`` and related APIs.
- ``test_python_snippet_bodies_avoid_restricted_forbidden_imports`` — No raw
  ``import json`` / ``jsonschema`` / ``import base64`` / ``from datetime import``.
- ``test_unknown_language_returns_empty`` — Missing JSON yields an empty tuple.
- ``test_malformed_json_returns_empty`` — Invalid JSON yields an empty tuple.

**Popover**

- ``test_popup_search_filters_list`` — Search narrows visible rows.
- ``test_popup_pick_invokes_callback`` — Picking a row calls ``on_pick`` with the body.
- ``test_popup_category_header_not_pickable`` — Category headers carry no body role.
- ``test_popup_escape_hides`` — Escape hides the popover and clears the callback.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

import ui.widgets.snippets.loader as snippet_loader
from ui.widgets.snippets.loader import load_snippets
from ui.widgets.snippets.popup import SnippetsPopup

_BODY_ROLE = Qt.ItemDataRole.UserRole + 1


@pytest.fixture(autouse=True)
def _clear_snippet_loader_cache() -> Iterator[None]:
    """Snippet JSON is memoised; clear between tests so edits reload reliably."""
    snippet_loader.load_snippets.cache_clear()
    yield
    snippet_loader.load_snippets.cache_clear()


def test_load_javascript_snippets() -> None:
    """``javascript.json`` defines Send requests and Variables with a sendRequest example."""
    cats = load_snippets("javascript")
    assert cats, "javascript.json missing"
    names = {c.name for c in cats}
    assert "Send requests" in names and "Variables" in names
    sends = [s for c in cats for s in c.snippets if "HTTP" in s.name]
    assert sends and "pm.sendRequest" in sends[0].body


def test_load_javascript_includes_tests_and_request_setup_categories() -> None:
    """``javascript.json`` ships Postman-style Tests and Request setup rows."""
    cats = load_snippets("javascript")
    names = {c.name for c in cats}
    assert "Tests" in names and "Request setup" in names
    tests = next(c for c in cats if c.name == "Tests")
    assert any("pm.response.to.have.status" in s.body for s in tests.snippets)
    assert any("pm.response.to.have.body" in s.body for s in tests.snippets)
    assert any("oneOf" in s.body for s in tests.snippets)


def test_typescript_falls_back_to_javascript() -> None:
    """Editor language ``typescript`` resolves to the same data as ``javascript``."""
    assert load_snippets("typescript") == load_snippets("javascript")


def test_load_python_snippets_use_snake_case() -> None:
    """Python snippets use ``pm.collection_variables`` and ``pm.send_request``."""
    cats = load_snippets("python")
    bodies = " ".join(s.body for c in cats for s in c.snippets)
    assert "pm.collection_variables" in bodies
    assert "pm.send_request" in bodies
    assert "pm.collectionVariables" not in bodies
    assert "pm.sendRequest" not in bodies


def test_load_python_includes_tests_and_request_setup_categories() -> None:
    """``python.json`` mirrors Tests / Request setup with snake_case ``pm`` APIs."""
    cats = load_snippets("python")
    names = {c.name for c in cats}
    assert "Tests" in names and "Request setup" in names
    tests = next(c for c in cats if c.name == "Tests")
    assert any("to.have.status" in s.body for s in tests.snippets)
    assert any("to.have.body" in s.body for s in tests.snippets)
    assert any("one_of" in s.body or "oneOf" in s.body for s in tests.snippets)
    assert any("to.be.least" in s.body for s in tests.snippets)


def test_python_snippet_bodies_avoid_restricted_forbidden_imports() -> None:
    """RestrictedPython subprocess path does not allow arbitrary stdlib imports."""
    bodies = "\n".join(s.body for c in load_snippets("python") for s in c.snippets)
    assert re.search(r"\bimport json\b", bodies) is None
    assert re.search(r"\bimport base64\b", bodies) is None
    assert re.search(r"\bfrom datetime import\b", bodies) is None
    assert re.search(r"\bimport jsonschema\b", bodies) is None
    assert re.search(r"\bfrom jsonschema\b", bodies) is None


def test_unknown_language_returns_empty() -> None:
    """Languages with no JSON file produce an empty category tuple."""
    assert load_snippets("ruby") == ()


def test_malformed_json_returns_empty(tmp_path, monkeypatch) -> None:
    """Invalid JSON on disk is treated as no snippets (and does not raise)."""
    (tmp_path / "javascript.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr("ui.widgets.snippets.loader._data_dir", lambda: tmp_path)
    snippet_loader.load_snippets.cache_clear()
    try:
        assert load_snippets("javascript") == ()
    finally:
        snippet_loader.load_snippets.cache_clear()


def test_popup_search_filters_list(qapp, qtbot) -> None:
    """Typing in the search field filters snippet rows by name or body substring."""
    popup = SnippetsPopup.instance()
    anchor = QPushButton("Snippets")
    qtbot.addWidget(anchor)
    anchor.show()

    popup.show_for(anchor, "javascript", "test", on_pick=lambda _b: None)
    qapp.processEvents()

    popup._search.setText("global")
    qapp.processEvents()
    visible_texts = [popup._list.item(i).text().strip() for i in range(popup._list.count())]
    assert any("global" in t.lower() for t in visible_texts)
    popup.hidePopup()


def test_popup_pick_invokes_callback(qapp, qtbot) -> None:
    """Clicking a snippet row invokes ``on_pick`` with a body containing ``globals``."""
    popup = SnippetsPopup.instance()
    anchor = QPushButton("Snippets")
    qtbot.addWidget(anchor)
    anchor.show()

    received: list[str] = []
    popup.show_for(anchor, "javascript", "test", on_pick=received.append)
    qapp.processEvents()

    for i in range(popup._list.count()):
        item = popup._list.item(i)
        if isinstance(item.data(_BODY_ROLE), str) and "global" in item.text().lower():
            popup._on_item_activated(item)
            break

    assert received and "globals" in received[0]


def test_popup_category_header_not_pickable(qapp, qtbot) -> None:
    """Category header items must not expose a string body role."""
    popup = SnippetsPopup.instance()
    anchor = QPushButton("Snippets")
    qtbot.addWidget(anchor)
    anchor.show()
    popup.show_for(anchor, "javascript", "test", on_pick=lambda _b: None)
    qapp.processEvents()

    for i in range(popup._list.count()):
        item = popup._list.item(i)
        if item.flags() == Qt.ItemFlag.NoItemFlags:
            assert not isinstance(item.data(_BODY_ROLE), str)
    popup.hidePopup()


def test_popup_escape_hides(qapp, qtbot) -> None:
    """Pressing Escape clears the popover and the pending ``on_pick`` callback."""
    popup = SnippetsPopup.instance()
    anchor = QPushButton("Snippets")
    qtbot.addWidget(anchor)
    anchor.show()

    called = False

    def _cb(_: str) -> None:
        nonlocal called
        called = True

    popup.show_for(anchor, "javascript", "test", on_pick=_cb)
    qapp.processEvents()
    qtbot.keyClick(popup, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert not popup.isVisible()
    assert popup._on_pick is None
    assert not called


def test_pre_request_filter_excludes_tests() -> None:
    """``Tests`` is hidden from the pre-request editor; ``Send requests`` and ``Request setup`` show."""
    from ui.widgets.snippets.loader import load_snippets_for

    cats = load_snippets_for("javascript", "pre_request")
    names = {c.name for c in cats}
    assert "Tests" not in names
    assert "Send requests" in names
    assert "Request setup" in names


def test_post_response_filter_excludes_request_setup() -> None:
    """``Request setup`` is hidden from the post-response editor; ``Tests`` shows."""
    from ui.widgets.snippets.loader import load_snippets_for

    cats = load_snippets_for("javascript", "test")
    names = {c.name for c in cats}
    assert "Tests" in names
    assert "Request setup" not in names


def test_javascript_snippets_use_modern_let_const() -> None:
    """JS / TS snippet bodies must not contain bare ``var`` declarations."""
    bodies = "\n".join(s.body for c in load_snippets("javascript") for s in c.snippets)
    assert re.search(r"\bvar\s+\w", bodies) is None, "JS snippets should use const/let"
