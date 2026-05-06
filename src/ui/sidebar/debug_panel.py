"""Debug UI: step controls, variable inspector, and combined facade.

``DebugControls`` is the toolbar (step buttons + position).  ``DebugVariablesPanel``
shows script locals in one collapsible ``QTreeWidget`` (section roots + values).
``DebugPanel`` composes both for tests and legacy callers.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.scripting.debug import DebugPauseInfo
from ui.styling.icons import phi
from ui.styling.theme import COLOR_WHITE
from ui.widgets.debug_value_tree import (
    TreeFillState,
    fill_tree_item,
    make_debug_value_tree,
    source_dot_icon,
)

DEBUG_VARIABLES_PAGE_TREE: int = 0
DEBUG_VARIABLES_PAGE_MESSAGE: int = 1


class DebugControls(QWidget):
    """Step buttons and pause position label (for output panel or composed panel)."""

    step_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the control row and position line; hidden until a pause event."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._continue_btn = self._make_btn("play", "Continue", "continue")
        self._step_over_btn = self._make_btn("arrow-line-down", "Step Over", "step_over")
        self._step_into_btn = self._make_btn("arrow-line-down-right", "Step Into", "step_into")
        self._step_out_btn = self._make_btn("arrow-line-up-right", "Step Out", "step_out")
        self._stop_btn = self._make_btn("stop", "Stop", "stop")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setIcon(phi("stop", color=COLOR_WHITE, size=16))

        for btn in (
            self._continue_btn,
            self._step_over_btn,
            self._step_into_btn,
            self._step_out_btn,
            self._stop_btn,
        ):
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._position_label = QLabel("Idle")
        self._position_label.setObjectName("mutedLabel")
        self._position_label.setWordWrap(True)
        layout.addWidget(self._position_label)

        self._set_buttons_enabled(False)
        self.hide()

    def _make_btn(self, icon_name: str, tooltip: str, mode: str) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(phi(icon_name, size=14))
        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.step_requested.emit(mode))
        return btn

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn in (
            self._continue_btn,
            self._step_over_btn,
            self._step_into_btn,
            self._step_out_btn,
            self._stop_btn,
        ):
            btn.setEnabled(enabled)

    def _set_object_name_for_idle_title(self) -> None:
        self._position_label.setObjectName("mutedLabel")

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Set position text and enable step controls."""
        source = info.get("source_name", "")
        line = info.get("line", 0)
        script_type = info.get("script_type", "")
        self._position_label.setObjectName("sidebarTitleLabel")
        self._position_label.setText(
            f"Paused at line {line + 1}  \u2014  {script_type}" + (f" ({source})" if source else "")
        )
        self._set_buttons_enabled(True)

    def clear_session(self) -> None:
        """Disable controls after a session ends."""
        self._position_label.setText("Session ended")
        self._set_object_name_for_idle_title()
        self._set_buttons_enabled(False)

    def set_idle(self) -> None:
        """Reset toolbar to idle."""
        self._position_label.setText("Idle")
        self._set_object_name_for_idle_title()
        self._set_buttons_enabled(False)


class DebugVariablesPanel(QWidget):
    """Single-tree variable inspector for script debug (sidebar or output panel)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build stacked tree vs placeholder pages."""
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(0)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack, 1)

        page_tree = QWidget()
        tree_lay = QVBoxLayout(page_tree)
        tree_lay.setContentsMargins(0, 0, 0, 0)
        self._tree = make_debug_value_tree(object_name="debugVariablesTree")
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

        self._stack.setCurrentIndex(DEBUG_VARIABLES_PAGE_TREE)
        self._fill_state = TreeFillState()

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Refresh variable sections from a pause event."""
        self._load_pause_sections(
            info.get("local_vars", {}),
            info.get("env_changes", {}) or {},
            info.get("global_changes", {}) or {},
        )

    def clear_session(self) -> None:
        """Clear the tree and show a session-ended hint."""
        self._tree.clear()
        self._placeholder.setText("Session ended")
        self._stack.setCurrentIndex(DEBUG_VARIABLES_PAGE_MESSAGE)

    def set_idle(self) -> None:
        """Clear the tree when the debugger is idle (empty tree page)."""
        self._tree.clear()
        self._stack.setCurrentIndex(DEBUG_VARIABLES_PAGE_TREE)

    def _show_tree_page(self) -> None:
        """Show the variables tree (may be empty)."""
        self._stack.setCurrentIndex(DEBUG_VARIABLES_PAGE_TREE)

    def _show_message_page(self, text: str) -> None:
        """Show a full-page placeholder instead of the tree."""
        self._placeholder.setText(text)
        self._stack.setCurrentIndex(DEBUG_VARIABLES_PAGE_MESSAGE)

    def _add_section(self, title: str, source: str, items: dict[str, Any]) -> None:
        """Append a collapsible section root and fill children from *items*."""
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

    def _load_pause_sections(
        self,
        local_vars: dict[str, Any],
        env_changes: dict[str, Any],
        global_changes: dict[str, Any],
    ) -> None:
        self._show_tree_page()
        self._tree.clear()
        self._fill_state = TreeFillState()
        has_any = False
        if (
            "pm" in local_vars
            and "globals" in local_vars
            and isinstance(local_vars.get("pm"), dict)
            and isinstance(local_vars.get("globals"), dict)
        ):
            pm = local_vars["pm"]
            gl = local_vars["globals"]
            if pm:
                has_any = True
                self._add_section("pm (request / collection)", "collection", pm)
            if gl:
                has_any = True
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
                    has_any = True
                    scope_sections_added = True
                    label = sc.get("name") or "Locals"
                    self._add_section(f"Locals (call frame): {label}", "local", vars_)
            lex = local_vars.get("locals")
            if isinstance(lex, dict) and lex and not scope_sections_added:
                has_any = True
                self._add_section("Lexical locals", "local", lex)
            if env_changes:
                has_any = True
                self._add_section(
                    "Variables set by script (pm.variables)",
                    "environment",
                    env_changes,
                )
            if global_changes:
                has_any = True
                self._add_section("Workspace changes", "collection", global_changes)
        else:
            if local_vars:
                has_any = True
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
                has_any = True
                self._add_section(
                    "Variables set by script (pm.variables)",
                    "environment",
                    env_changes,
                )
            if global_changes:
                has_any = True
                self._add_section("Workspace changes", "collection", global_changes)
        if not has_any:
            self._show_message_page("No local variables")
        else:
            self._tree.resizeColumnToContents(0)


class DebugPanel(QWidget):
    """Sidebar panel showing debug state: controls + step + variables (facade)."""

    step_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Stack controls and variables (legacy combined sidebar widget)."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._controls = DebugControls(self)
        self._controls.step_requested.connect(self.step_requested.emit)
        layout.addWidget(self._controls)

        self._variables = DebugVariablesPanel(self)
        layout.addWidget(self._variables, 1)

    @property
    def _position_label(self) -> QLabel:
        return self._controls._position_label

    @property
    def _continue_btn(self) -> QPushButton:
        return self._controls._continue_btn

    @property
    def _step_over_btn(self) -> QPushButton:
        return self._controls._step_over_btn

    @property
    def _step_into_btn(self) -> QPushButton:
        return self._controls._step_into_btn

    @property
    def _step_out_btn(self) -> QPushButton:
        return self._controls._step_out_btn

    @property
    def _stop_btn(self) -> QPushButton:
        return self._controls._stop_btn

    @property
    def _tree(self) -> QTreeWidget:
        """Unified debug variables tree (tests and introspection)."""
        return self._variables._tree

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Refresh the toolbar and variable list."""
        self._controls.update_pause(info)
        self._variables.update_pause(info)

    def clear_session(self) -> None:
        """End-of-session state for both halves."""
        self._controls.clear_session()
        self._variables.clear_session()

    def set_idle(self) -> None:
        """Reset both halves to the idle state."""
        self._controls.set_idle()
        self._variables.set_idle()
