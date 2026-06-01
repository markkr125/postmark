"""Fixtures for local-script UI tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.local_scripts.local_script_editor_widget import LocalScriptEditorWidget


@pytest.fixture
def local_script_editor(qtbot) -> Iterator[LocalScriptEditorWidget]:
    """``LocalScriptEditorWidget`` that never becomes a desktop window during tests."""
    editor = LocalScriptEditorWidget()
    editor.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    qtbot.addWidget(editor)
    yield editor


@pytest.fixture(autouse=True)
def _teardown_local_script_editors() -> Iterator[None]:
    """Cancel async LSP prep and tear down any stray script-editor top-level windows."""
    yield
    from shiboken6 import Shiboken

    from tests.qt_popup_cleanup import dismiss_all_top_level_test_widgets

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for widget in app.allWidgets():
        if not Shiboken.isValid(widget):
            continue
        pane = getattr(widget, "_pane", None)
        if pane is not None and hasattr(pane, "cancel_async_lsp_prep"):
            pane.cancel_async_lsp_prep()
    dismiss_all_top_level_test_widgets(app)
