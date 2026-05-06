"""Tests for the DebugPanel sidebar widget."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem

from services.scripting.debug import DebugPauseInfo
from ui.sidebar.debug_panel import DEBUG_VARIABLES_PAGE_MESSAGE, DebugPanel
from ui.widgets.debug_value_tree import debug_tree_cell_text


def _with_pause_keys(d: dict[str, Any]) -> DebugPauseInfo:
    """Ensure ``DebugPauseInfo`` optional keys exist for static typing."""
    out = dict(d)
    out.setdefault("env_changes", {})
    out.setdefault("global_changes", {})
    return cast(DebugPauseInfo, out)


def _walk_debug_tree_items(item: QTreeWidgetItem) -> Iterator[QTreeWidgetItem]:
    yield item
    for i in range(item.childCount()):
        yield from _walk_debug_tree_items(item.child(i))


def _walk_all_tree_items(tree: QTreeWidget) -> Iterator[QTreeWidgetItem]:
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top is None:
            continue
        yield from _walk_debug_tree_items(top)


def _section_titles(panel: DebugPanel) -> list[str]:
    """Top-level section titles (column 0) in the unified variables tree."""
    tree = panel._tree
    out: list[str] = []
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top is not None:
            out.append(top.text(0))
    return out


def _keys_under(panel: DebugPanel, section_title: str) -> set[str]:
    """Direct child keys (column 0) under the section whose title matches *section_title*."""
    tree = panel._tree
    for i in range(tree.topLevelItemCount()):
        root = tree.topLevelItem(i)
        if root is None:
            continue
        if root.text(0) == section_title:
            return {debug_tree_cell_text(root.child(j), 0) for j in range(root.childCount())}
    return set()


def _first_level_keys_all_sections(panel: DebugPanel) -> set[str]:
    """Union of every direct child name column under all top-level sections."""
    keys: set[str] = set()
    tree = panel._tree
    for i in range(tree.topLevelItemCount()):
        sec = tree.topLevelItem(i)
        if sec is None:
            continue
        for j in range(sec.childCount()):
            ch = sec.child(j)
            if ch is not None:
                keys.add(debug_tree_cell_text(ch, 0))
    return keys


def _debug_panel_all_texts(panel: DebugPanel) -> str:
    """All name/value column strings in the unified debug variables tree."""
    parts: list[str] = []
    for it in _walk_all_tree_items(panel._tree):
        parts.append(debug_tree_cell_text(it, 0))
        parts.append(debug_tree_cell_text(it, 1))
    return " ".join(parts)


class TestDebugPanel:
    """Tests for the debug panel widget — step controls and variable display."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """DebugPanel can be instantiated without errors."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        assert panel._position_label.text() == "Idle"

    def test_buttons_start_disabled(self, qapp: QApplication, qtbot) -> None:
        """Step buttons are disabled when no session is active."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        assert not panel._continue_btn.isEnabled()
        assert not panel._step_over_btn.isEnabled()
        assert not panel._step_into_btn.isEnabled()
        assert not panel._step_out_btn.isEnabled()
        assert not panel._stop_btn.isEnabled()

    def test_update_pause_enables_buttons(self, qapp: QApplication, qtbot) -> None:
        """update_pause() enables step buttons and shows position."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 5,
                    "source_name": "test.js",
                    "local_vars": {"x": 42},
                    "script_type": "pre_request",
                }
            )
        )
        assert panel._continue_btn.isEnabled()
        assert panel._stop_btn.isEnabled()
        assert "line 6" in panel._position_label.text()
        assert "pre_request" in panel._position_label.text()
        assert panel._position_label.objectName() == "sidebarTitleLabel"

    def test_update_pause_shows_variables(self, qapp: QApplication, qtbot) -> None:
        """update_pause() populates the variable list."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {"a": 1, "b": "hello"},
                    "script_type": "test",
                }
            )
        )
        assert panel._tree.topLevelItemCount() >= 1
        texts = _debug_panel_all_texts(panel)
        assert "Local Variables" in texts
        assert "a" in texts
        assert "b" in texts
        assert "1" in texts
        assert "hello" in texts

    def test_update_pause_structured_pm_and_globals(self, qapp: QApplication, qtbot) -> None:
        """JS debug can pass ``pm`` and ``globals`` with subsection labels."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {
                    "pm": {"V": "x"},
                    "globals": {"a": 1},
                },
                "env_changes": {"H": "sig"},
                "global_changes": {},
                "script_type": "pre_request",
            }
        )
        assert panel._tree.topLevelItemCount() >= 1
        texts = _debug_panel_all_texts(panel)
        for chunk in (
            "V",
            "H",
            "x",
            "1",
            "sig",
            "pm (request",
            "globalThis",
            "Variables set by script",
        ):
            assert chunk in texts

    def test_structured_empty_pm_globals_shows_lexical_flat(
        self, qapp: QApplication, qtbot
    ) -> None:
        """When ``pm``/``globals`` are empty dicts, flat ``locals`` still renders (CDP fallback)."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 12,
                    "source_name": "pre.js",
                    "local_vars": {
                        "pm": {},
                        "globals": {},
                        "locals": {"randomId": 7, "timestamp": "iso"},
                        "scopes": [],
                    },
                    "env_changes": {"userId": "42"},
                    "global_changes": {},
                    "script_type": "pre_request",
                }
            )
        )
        keys = _first_level_keys_all_sections(panel)
        assert "randomId" in keys
        assert "timestamp" in keys
        assert "userId" in keys
        titles = _section_titles(panel)
        assert "Lexical locals" in titles
        assert "Variables set by script (pm.variables)" in titles

    def test_pm_variables_section_below_lexical_locals(self, qapp: QApplication, qtbot) -> None:
        """``pm.variables`` updates appear after CDP locals (same panel order)."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 12,
                    "source_name": "pre.js",
                    "local_vars": {
                        "pm": {},
                        "globals": {},
                        "locals": {"randomId": 7},
                        "scopes": [],
                    },
                    "env_changes": {"userId": "42"},
                    "global_changes": {},
                    "script_type": "pre_request",
                }
            )
        )
        titles = _section_titles(panel)
        env_i = titles.index("Variables set by script (pm.variables)")
        lex_i = titles.index("Lexical locals")
        assert lex_i < env_i

    def test_scope_sections_skip_duplicate_lexical_header(self, qapp: QApplication, qtbot) -> None:
        """Per-scope rows satisfy ``has_any``; do not add a second Lexical locals block."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {
                        "pm": {},
                        "globals": {},
                        "locals": {"a": 1},
                        "scopes": [
                            {"type": "module", "name": "Module", "vars": {"a": 1}},
                        ],
                    },
                    "script_type": "pre_request",
                }
            )
        )
        texts_joined = _debug_panel_all_texts(panel)
        assert "Locals (call frame): Module" in texts_joined
        assert "Lexical locals" not in texts_joined

    def test_update_pause_empty_vars(self, qapp: QApplication, qtbot) -> None:
        """update_pause() shows placeholder when no variables exist."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {},
                    "script_type": "test",
                }
            )
        )
        assert panel._variables._stack.currentIndex() == DEBUG_VARIABLES_PAGE_MESSAGE
        assert "No local variables" in panel._variables._placeholder.text()

    def test_clear_session(self, qapp: QApplication, qtbot) -> None:
        """clear_session() disables buttons and shows ended message."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {"x": 1},
                    "script_type": "pre_request",
                }
            )
        )
        panel.clear_session()
        assert not panel._continue_btn.isEnabled()
        assert "ended" in panel._position_label.text().lower()
        assert panel._position_label.objectName() == "mutedLabel"
        assert panel._variables._stack.currentIndex() == DEBUG_VARIABLES_PAGE_MESSAGE
        assert "Session ended" in panel._variables._placeholder.text()

    def test_set_idle(self, qapp: QApplication, qtbot) -> None:
        """set_idle() resets to initial idle state."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 3,
                    "source_name": "",
                    "local_vars": {"a": 1},
                    "script_type": "test",
                }
            )
        )
        panel.set_idle()
        assert panel._position_label.text() == "Idle"
        assert not panel._continue_btn.isEnabled()
        assert panel._position_label.objectName() == "mutedLabel"
        assert panel._tree.topLevelItemCount() == 0

    def test_step_signal_emitted(self, qapp: QApplication, qtbot) -> None:
        """Clicking a step button emits step_requested with the mode name."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {},
                    "script_type": "pre_request",
                }
            )
        )
        with qtbot.waitSignal(panel.step_requested, timeout=1000) as blocker:
            panel._continue_btn.click()
        assert blocker.args == ["continue"]

    def test_step_over_signal(self, qapp: QApplication, qtbot) -> None:
        """Step Over button emits 'step_over'."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {},
                    "script_type": "pre_request",
                }
            )
        )
        with qtbot.waitSignal(panel.step_requested, timeout=1000) as blocker:
            panel._step_over_btn.click()
        assert blocker.args == ["step_over"]

    def test_stop_signal(self, qapp: QApplication, qtbot) -> None:
        """Stop button emits 'stop'."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {},
                    "script_type": "pre_request",
                }
            )
        )
        with qtbot.waitSignal(panel.step_requested, timeout=1000) as blocker:
            panel._stop_btn.click()
        assert blocker.args == ["stop"]

    def test_variables_replaced_on_subsequent_pause(self, qapp: QApplication, qtbot) -> None:
        """Calling update_pause() again replaces previous variables."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {"a": 1, "b": 2, "c": 3},
                    "script_type": "test",
                }
            )
        )
        count_before = panel._tree.topLevelItemCount()
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 1,
                    "source_name": "",
                    "local_vars": {"x": 10},
                    "script_type": "test",
                }
            )
        )
        texts = _debug_panel_all_texts(panel)
        assert "x" in texts
        assert "10" in texts
        assert _keys_under(panel, "Local Variables") == {"x"}
        assert panel._tree.topLevelItemCount() <= count_before

    def test_very_long_string_elides_tree_cell_with_full_tooltip(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Long string leaves elide in the value column; the tooltip keeps the full text."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        long_val = "x" * 200
        panel.update_pause(
            _with_pause_keys(
                {
                    "line": 0,
                    "source_name": "",
                    "local_vars": {"pm": {"huge": long_val}, "globals": {}},
                    "script_type": "test",
                }
            )
        )
        tree = panel._tree
        sec = None
        for i in range(tree.topLevelItemCount()):
            t = tree.topLevelItem(i)
            if t is not None and "pm (request" in t.text(0):
                sec = t
                break
        assert sec is not None
        assert sec.childCount() >= 1
        leaf = sec.child(0)
        assert leaf is not None
        assert debug_tree_cell_text(leaf, 0) == "huge"
        shown = debug_tree_cell_text(leaf, 1)
        assert len(shown) < len(long_val) + 10
        assert long_val in (leaf.toolTip(1) or "")
