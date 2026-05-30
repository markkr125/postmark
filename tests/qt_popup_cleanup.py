"""Shared Qt popup teardown for tests (app-wide singletons survive per-test widget delete)."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import Shiboken


def reset_code_editor_popups() -> None:
    """Hide and disconnect shared code-editor popups so they do not leak onto the desktop."""
    from ui.widgets.code_editor import popup_registry

    for getter in (
        popup_registry.completion_popup,
        popup_registry.parameter_hint_popup,
        popup_registry.symbol_doc_popup,
        popup_registry.debug_value_popup,
    ):
        popup = getter()
        if not Shiboken.isValid(popup):
            continue
        if hasattr(popup, "clear_target"):
            popup.clear_target()
        if hasattr(popup, "is_active") and popup.is_active() and hasattr(popup, "dismiss"):
            popup.dismiss()
        else:
            popup.hide()


def flush_deferred_widget_deletes(qapp: QApplication) -> None:
    """Process queued ``DeferredDelete`` events after popup/editor teardown."""
    qapp.sendPostedEvents(None, int(QEvent.Type.DeferredDelete))
