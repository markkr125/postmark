"""Unified variables tree: watches, locals, pm, globals, env (JetBrains-style)."""

from __future__ import annotations

import contextlib
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from shiboken6 import Shiboken

from services.scripting.debug import DebugProtocol, DebugState
from ui.sidebar.debug_watch_in_tree import (
    WATCH_SECTION_SOURCE,
    WatchState,
    _set_watch_row_columns,
    format_watch_display,
    rebuild_watch_rows,
)
from ui.styling.theme import (
    DEBUG_INSPECTOR_RIGHT_PANE_H_LEFT_PX,
    DEBUG_INSPECTOR_RIGHT_PANE_H_RIGHT_PX,
)
from ui.widgets.debug_value_tree import (
    TreeFillState,
    debug_tree_cell_text,
    fill_tree_item,
    make_debug_value_tree,
    refresh_debug_tree_cell_elides,
    source_dot_icon,
)

DEBUG_SCOPES_PAGE_TREE: int = 0
DEBUG_SCOPES_PAGE_MESSAGE: int = 1


def _qt_valid(obj: object | None) -> bool:
    """Return whether *obj* is a live Qt C++ wrapper (not deleted)."""
    return obj is not None and Shiboken.isValid(obj)


class DebugScopesPanel(QWidget):
    """Right-hand inspector: Watches section + scope variables in one tree."""

    watch_expressions_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build stacked tree vs placeholder page."""
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack, 1)

        page_tree = QWidget()
        tree_lay = QVBoxLayout(page_tree)
        tree_lay.setContentsMargins(
            DEBUG_INSPECTOR_RIGHT_PANE_H_LEFT_PX,
            0,
            DEBUG_INSPECTOR_RIGHT_PANE_H_RIGHT_PX,
            0,
        )
        self._tree = make_debug_value_tree(
            object_name="debugScopesTree",
            watch_actions_column=True,
        )
        tree_lay.addWidget(self._tree, 1)
        self._stack.addWidget(page_tree)

        page_msg = QWidget()
        msg_lay = QVBoxLayout(page_msg)
        msg_lay.setContentsMargins(0, 8, 0, 8)
        self._placeholder = QLabel("")
        self._placeholder.setObjectName("mutedLabel")
        self._placeholder.setWordWrap(True)
        msg_lay.addWidget(self._placeholder)
        msg_lay.addStretch()
        self._stack.addWidget(page_msg)

        self._stack.setCurrentIndex(DEBUG_SCOPES_PAGE_TREE)
        self._fill_state = TreeFillState()
        self._watch_state = WatchState()
        self._watches_root: QTreeWidgetItem | None = None
        self._protocol: DebugProtocol | None = None
        self._show_internal_debug_vars = False
        self._last_local_vars: dict[str, Any] = {}
        self._last_env_changes: dict[str, Any] = {}
        self._last_global_changes: dict[str, Any] = {}

    @property
    def watch_state(self) -> WatchState:
        """Ordered watch expressions for this inspector."""
        return self._watch_state

    @property
    def watches_root(self) -> QTreeWidgetItem | None:
        """Top-level Watches section item, if present."""
        return self._watches_root

    def set_protocol(self, protocol: DebugProtocol | None) -> None:
        """Attach the active :class:`DebugProtocol` for watch evaluation."""
        if self._protocol is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                self._protocol.evaluated.disconnect(self._on_eval_result)
        self._protocol = protocol
        if protocol is not None:
            protocol.evaluated.connect(self._on_eval_result)

    def _on_eval_result(self, expr: str, value: str) -> None:
        """Update a watch row when a background evaluation completes."""
        root = self._watches_root
        if not _qt_valid(self._tree) or root is None or not _qt_valid(root):
            return
        for i in range(root.childCount()):
            child = root.child(i)
            if child is not None and debug_tree_cell_text(child, 0) == expr:
                display, tip = format_watch_display(value)
                _set_watch_row_columns(child, expr, display, tip)
                refresh_debug_tree_cell_elides(self._tree)
                return

    def refresh_watches(self) -> None:
        """Queue watch expression re-evaluation when paused."""
        protocol = self._protocol
        if protocol is None:
            return
        for expr in self._watch_state.expressions:
            protocol.submit_evaluate(expr)

    def is_paused(self) -> bool:
        """Return whether a debug protocol is attached and execution is paused."""
        protocol = self._protocol
        return protocol is not None and protocol.state == DebugState.PAUSED

    def set_watch_expressions(self, expressions: list[str]) -> None:
        """Replace the watch list and rebuild the Watches section."""
        self._watch_state.expressions = [e.strip() for e in expressions if e.strip()]
        self._load_watches_only_tree()
        self.watch_expressions_changed.emit()
        if self.is_paused():
            self.refresh_watches()

    def add_watch_expression(self, text: str) -> None:
        """Append *text* to the watch list and refresh the tree."""
        if not text:
            return
        self._watch_state.expressions.append(text)
        self._ensure_watches_section()
        self.watch_expressions_changed.emit()
        if self.is_paused():
            self.refresh_watches()

    def remove_selected_watch(self) -> None:
        """Remove the selected watch row under the Watches section."""
        root = self._watches_root
        if not _qt_valid(self._tree) or root is None:
            return
        item = self._tree.currentItem()
        if item is None or item.parent() is not root:
            return
        idx = root.indexOfChild(item)
        if idx < 0:
            return
        self.remove_watch_at_index(idx)

    def remove_watch_at_index(self, idx: int) -> None:
        """Remove the watch expression at *idx* in the Watches section."""
        root = self._watches_root
        if not _qt_valid(self._tree) or root is None:
            return
        if idx < 0 or idx >= len(self._watch_state.expressions):
            return
        self._watch_state.expressions.pop(idx)
        if not self._watch_state.expressions:
            self._drop_watches_section()
        else:
            rebuild_watch_rows(
                root,
                self._watch_state,
                self._tree,
                on_remove_at_index=self.remove_watch_at_index,
            )
        self.watch_expressions_changed.emit()
        if self.is_paused():
            self.refresh_watches()

    def _drop_watches_section(self) -> None:
        if not _qt_valid(self._tree):
            self._watches_root = None
            return
        root = self._watches_root
        if root is None or not _qt_valid(root):
            self._watches_root = None
            return
        idx = self._tree.indexOfTopLevelItem(root)
        if idx >= 0:
            self._tree.takeTopLevelItem(idx)
        self._watches_root = None

    def _ensure_watches_section(self) -> None:
        if not _qt_valid(self._tree) or not self._watch_state.expressions:
            return
        if self._watches_root is None or not _qt_valid(self._watches_root):
            self._watches_root = self._create_watches_section_root()
            self._tree.insertTopLevelItem(0, self._watches_root)
        rebuild_watch_rows(
            self._watches_root,
            self._watch_state,
            self._tree,
            on_remove_at_index=self.remove_watch_at_index,
        )
        self._watches_root.setExpanded(True)

    def _create_watches_section_root(self) -> QTreeWidgetItem:
        root = QTreeWidgetItem(["Watches", ""])
        root.setData(0, Qt.ItemDataRole.UserRole, "section")
        root.setData(0, Qt.ItemDataRole.UserRole + 1, WATCH_SECTION_SOURCE)
        root.setIcon(0, source_dot_icon(WATCH_SECTION_SOURCE))
        font = root.font(0)
        font.setBold(True)
        root.setFont(0, font)
        return root

    def _load_watches_only_tree(self) -> None:
        """Rebuild tree with only the Watches section (placeholder values)."""
        if not _qt_valid(self._tree):
            return
        self._tree.clear()
        self._fill_state = TreeFillState()
        self._watches_root = None
        if self._watch_state.expressions:
            self._ensure_watches_section()
        self._show_tree_page()

    def update_pause(
        self,
        local_vars: dict[str, Any],
        env_changes: dict[str, Any],
        global_changes: dict[str, Any],
    ) -> None:
        """Refresh watches and scope sections from a pause payload."""
        self._last_local_vars = dict(local_vars)
        self._last_env_changes = dict(env_changes)
        self._last_global_changes = dict(global_changes)
        self._load_pause_sections(local_vars, env_changes, global_changes)
        protocol = self._protocol
        if protocol is not None and protocol.state == DebugState.PAUSED:
            self.refresh_watches()

    def set_show_internal_debug_vars(self, enabled: bool) -> None:
        """Toggle display of internal ``__pm_*`` runtime globals."""
        self._show_internal_debug_vars = bool(enabled)
        self._load_pause_sections(
            self._last_local_vars,
            self._last_env_changes,
            self._last_global_changes,
        )
        protocol = self._protocol
        if protocol is not None and protocol.state == DebugState.PAUSED:
            self.refresh_watches()

    def clear_session(self) -> None:
        """End session: keep watch expressions with placeholder values."""
        if not _qt_valid(self._tree):
            return
        self._load_watches_only_tree()
        if not self._watch_state.expressions and _qt_valid(self._placeholder):
            self._placeholder.setText("Session ended")
            self._stack.setCurrentIndex(DEBUG_SCOPES_PAGE_MESSAGE)

    def set_idle(self) -> None:
        """Clear protocol; keep watch expressions with placeholder values."""
        if self._protocol is not None:
            self._protocol.clear_eval_cache()
        self._protocol = None
        self._load_watches_only_tree()

    def _show_tree_page(self) -> None:
        self._stack.setCurrentIndex(DEBUG_SCOPES_PAGE_TREE)

    def _add_section(self, title: str, source: str, items: dict[str, Any]) -> None:
        items = self._visible_items(items)
        if not items:
            return
        root = QTreeWidgetItem([title, ""])
        root.setData(0, Qt.ItemDataRole.UserRole, "section")
        root.setData(0, Qt.ItemDataRole.UserRole + 1, source)
        root.setIcon(0, source_dot_icon(source))
        font = root.font(0)
        font.setBold(True)
        root.setFont(0, font)
        self._tree.addTopLevelItem(root)
        fill_tree_item(root, items, 1, self._fill_state, frozenset())
        root.setExpanded(True)

    def _visible_items(self, items: dict[str, Any]) -> dict[str, Any]:
        """Optionally hide internal ``__pm_*`` keys from debug variable sections."""
        if self._show_internal_debug_vars:
            return items
        return {k: v for k, v in items.items() if not str(k).startswith("__pm_")}

    def _load_pause_sections(
        self,
        local_vars: dict[str, Any],
        env_changes: dict[str, Any],
        global_changes: dict[str, Any],
    ) -> None:
        if not _qt_valid(self._tree):
            return
        self._tree.clear()
        self._fill_state = TreeFillState()
        self._watches_root = None
        if self._watch_state.expressions:
            self._ensure_watches_section()
        has_vars = False
        if (
            "pm" in local_vars
            and "globals" in local_vars
            and isinstance(local_vars.get("pm"), dict)
            and isinstance(local_vars.get("globals"), dict)
        ):
            pm = local_vars["pm"]
            gl = local_vars["globals"]
            if pm:
                has_vars = True
                self._add_section("pm (request / collection)", "collection", pm)
            if gl:
                has_vars = True
                self._add_section("globalThis (script)", "local", gl)
            scopes = local_vars.get("scopes")
            scope_sections_added = False
            if isinstance(scopes, list):
                for sc in scopes:
                    if not isinstance(sc, dict):
                        continue
                    vars_ = sc.get("vars") or {}
                    if not isinstance(vars_, dict) or not vars_:
                        continue
                    has_vars = True
                    scope_sections_added = True
                    label = sc.get("name") or "Locals"
                    self._add_section(f"Locals (call frame): {label}", "local", vars_)
            lex = local_vars.get("locals")
            if isinstance(lex, dict) and lex and not scope_sections_added:
                has_vars = True
                self._add_section("Lexical locals", "local", lex)
            if env_changes:
                has_vars = True
                self._add_section(
                    "Variables set by script (pm.variables)",
                    "environment",
                    env_changes,
                )
            if global_changes:
                has_vars = True
                self._add_section("Workspace changes", "collection", global_changes)
        else:
            if local_vars:
                has_vars = True
                skip = {"locals", "scopes"}
                flat = {
                    k: v
                    for k, v in sorted(
                        ((k, v) for k, v in local_vars.items() if k not in skip),
                        key=lambda kv: kv[0],
                    )
                }
                self._add_section("Local Variables", "local", flat)
            if env_changes:
                has_vars = True
                self._add_section(
                    "Variables set by script (pm.variables)",
                    "environment",
                    env_changes,
                )
            if global_changes:
                has_vars = True
                self._add_section("Workspace changes", "collection", global_changes)
        self._show_tree_page()
        if has_vars or self._watch_state.expressions:
            self._tree.resizeColumnToContents(0)
        refresh_debug_tree_cell_elides(self._tree)
