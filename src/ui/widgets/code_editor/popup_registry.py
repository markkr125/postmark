"""App-wide singletons for code-editor popup widgets.

Every ``CodeEditorWidget`` previously instantiated four popup ``QWidget``
objects up-front (``CompletionPopup``, ``ParameterHintPopup``,
``SymbolDocPopup``, ``DebugValuePopup``).  With many open tabs this
multiplies into hundreds of hidden top-level windows.

Only one popup of each kind is ever visible across the whole app, so we
keep one shared instance and retarget it per use.  Each accessor
constructs the popup lazily on first call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shiboken6 import Shiboken

if TYPE_CHECKING:
    from ui.widgets.code_editor.completion.parameter_hint import ParameterHintPopup
    from ui.widgets.code_editor.completion.popup import CompletionPopup
    from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDocPopup
    from ui.widgets.code_editor.debug_hover_popup import DebugValuePopup


_completion: CompletionPopup | None = None
_parameter_hint: ParameterHintPopup | None = None
_symbol_doc: SymbolDocPopup | None = None
_debug_value: DebugValuePopup | None = None


def completion_popup() -> CompletionPopup:
    """Return the shared ``CompletionPopup`` instance, building it lazily."""
    global _completion
    if _completion is not None and not Shiboken.isValid(_completion):
        _completion = None
    if _completion is None:
        from ui.widgets.code_editor.completion.popup import CompletionPopup

        _completion = CompletionPopup(parent=None)
    return _completion


def parameter_hint_popup() -> ParameterHintPopup:
    """Return the shared ``ParameterHintPopup`` instance, building it lazily."""
    global _parameter_hint
    if _parameter_hint is not None and not Shiboken.isValid(_parameter_hint):
        _parameter_hint = None
    if _parameter_hint is None:
        from ui.widgets.code_editor.completion.parameter_hint import ParameterHintPopup

        _parameter_hint = ParameterHintPopup(parent=None)
    return _parameter_hint


def symbol_doc_popup() -> SymbolDocPopup:
    """Return the shared ``SymbolDocPopup`` instance, building it lazily."""
    global _symbol_doc
    if _symbol_doc is not None and not Shiboken.isValid(_symbol_doc):
        _symbol_doc = None
    if _symbol_doc is None:
        from ui.widgets.code_editor.completion.symbol_doc_popup import SymbolDocPopup

        _symbol_doc = SymbolDocPopup(parent=None)
    return _symbol_doc


def debug_value_popup() -> DebugValuePopup:
    """Return the shared ``DebugValuePopup`` instance, building it lazily.

    The popup keeps an anchor widget for click-outside event filtering;
    callers must invoke :meth:`DebugValuePopup.set_anchor` before showing it.
    """
    global _debug_value
    if _debug_value is not None and not Shiboken.isValid(_debug_value):
        _debug_value = None
    if _debug_value is None:
        from ui.widgets.code_editor.debug_hover_popup import DebugValuePopup

        _debug_value = DebugValuePopup(anchor=None)
    return _debug_value
