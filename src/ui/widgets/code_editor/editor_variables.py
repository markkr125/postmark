"""Variable and debug-hover popup helpers for :class:`~editor_widget.CodeEditorWidget`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint
    from services.environment_service import VariableDetail
    from ui.widgets.code_editor.completion.engine import CompletionEngine
    from ui.widgets.code_editor.highlighter import PygmentsHighlighter
    from PySide6.QtWidgets import QPlainTextEdit

    _VariableBase = QPlainTextEdit
else:
    _VariableBase = object

# CDP scope rows often use the RemoteObject description alone (``Object``);
# :meth:`set_debug_locals` may also carry richer ``root_values`` for ``pm`` / ``console``.
_DEBUG_HOVER_PLACEHOLDER_OBJECT: frozenset[str] = frozenset({"Object", "Console", "[object]"})


class _VariableMixin(_VariableBase):
    """Mixin providing ``{{var}}`` and paused-debug hover popups."""

    _variable_map: dict[str, VariableDetail]
    _var_hover_name: str | None
    _var_hover_timer: Any
    _var_hover_global_pos: QPoint
    _debug_locals: dict[str, Any]
    _debug_root_values: dict[str, Any]
    _highlighter: PygmentsHighlighter
    _completion_engine: CompletionEngine
    _read_only: bool

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Update the variable resolution map and rehighlight."""
        self._variable_map = variables
        self._highlighter.set_variable_map(variables)
        self._highlighter.rehighlight()
        self._completion_engine.set_variable_map(variables)

    def set_debug_locals(
        self,
        locals_dict: dict[str, Any],
        *,
        root_values: dict[str, Any] | None = None,
    ) -> None:
        """Store flat debug names and optional whole-object roots (e.g. ``pm``).

        When ``globals``/``pm`` snapshots are merged into a flat map, ``pm`` is
        not a key in *locals_dict*; *root_values* keeps the full ``pm`` object
        for identifier hover. Passing only an empty *locals_dict* clears both
        maps. When *root_values* is omitted and *locals_dict* is non-empty,
        existing roots are left unchanged (callers should pass roots whenever
        they update locals during a pause).
        """
        self._debug_locals = dict(locals_dict)
        if root_values is not None:
            self._debug_root_values = dict(root_values)
        elif not locals_dict:
            self._debug_root_values = {}
        if not self._debug_locals and not self._debug_root_values:
            self._debug_popup.hide()

    def _debug_hover_resolved_value(self, name: str) -> Any | None:
        """Return the richest value for debug identifier hover."""
        if name in ("pm", "console"):
            local_v = self._debug_locals.get(name)
            root_v = self._debug_root_values.get(name)
            if isinstance(local_v, dict) and local_v:
                return local_v
            if isinstance(local_v, str) and local_v in _DEBUG_HOVER_PLACEHOLDER_OBJECT:
                return root_v if root_v is not None else local_v
            if root_v is not None:
                return root_v
            return local_v
        if name in self._debug_root_values:
            return self._debug_root_values[name]
        return self._debug_locals.get(name)

    def _show_var_hover_popup(self) -> None:
        """Show the variable popup for the currently hovered variable."""
        if self._var_hover_name is None:
            return
        name = self._var_hover_name
        if name in self._debug_locals or name in self._debug_root_values:
            resolved = self._debug_hover_resolved_value(name)
            if resolved is not None:
                self._show_debug_value_popup(name, resolved)
            return
        from ui.widgets.variable_popup import VariablePopup

        self._debug_popup.hide()
        detail = self._variable_map.get(self._var_hover_name)
        VariablePopup.show_variable(self._var_hover_name, detail, self._var_hover_global_pos, self)

    def _show_debug_value_popup(self, name: str, value: Any) -> None:
        """Show a styled popup for a paused-debug value (tree or text)."""
        self._debug_popup.set_anchor(self)
        self._debug_popup.show_value(name, value, self._var_hover_global_pos)

    def _hide_debug_value_popup(self) -> None:
        """Hide the debug hover popup if visible."""
        self._debug_popup.hide()
