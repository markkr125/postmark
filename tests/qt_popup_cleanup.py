"""Shared Qt popup teardown for tests (app-wide singletons survive per-test widget delete)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import Shiboken

# Top-level widgets created by tests that call ``show()`` without a real parent.
_TEST_TOP_LEVEL_TYPES = frozenset(
    {
        "LocalScriptEditorWidget",
        "MainWindow",
        "HistoryPanel",
        "RequestEditorWidget",
        "FolderEditorWidget",
        "CollectionWidget",
        "SavedResponsesPanel",
    }
)


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


def _is_test_leak_top_level(widget: QWidget, qapp: QApplication) -> bool:
    """Return True if *widget* looks like a pytest-created freestanding window."""
    if widget is qapp or not Shiboken.isValid(widget):
        return False
    if widget.parent() is not None:
        return False
    if type(widget).__name__ in _TEST_TOP_LEVEL_TYPES:
        return True
    if hasattr(widget, "_pane") and hasattr(getattr(widget, "_pane", None), "output_panel"):
        return True
    title = widget.windowTitle()
    return title.endswith(".py") or title == "conftest.py"


def dismiss_all_top_level_test_widgets(qapp: QApplication) -> None:
    """Close every orphan top-level widget (visible or hidden) except ``qapp`` itself."""
    for widget in list(QApplication.topLevelWidgets()):
        if not _is_test_leak_top_level(widget, qapp):
            continue
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        widget.hide()
        widget.close()
        widget.deleteLater()
    flush_deferred_widget_deletes(qapp)
    qapp.processEvents()


def dismiss_orphan_editor_windows(qapp: QApplication) -> None:
    """Backward-compatible alias for autouse teardown hooks."""
    dismiss_all_top_level_test_widgets(qapp)
