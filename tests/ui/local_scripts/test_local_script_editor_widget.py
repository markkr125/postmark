"""Tests for :class:`LocalScriptEditorWidget`."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.local_script_service import LocalScriptService
from services.lsp import local_script_lsp_prep as prep_mod
from services.lsp.local_script_lsp_prep import prepare_local_script_lsp_attach
from services.lsp.servers._workspace import ensure_js_workspace
from services.scripting.local_script_modules import build_module_index
from ui.local_scripts.local_script_editor_widget import LocalScriptEditorWidget


def test_autosave_persist_writes_script_content(
    local_script_editor: LocalScriptEditorWidget,
) -> None:
    """Auto-save callback persists buffer text to the database."""
    folder = create_folder("Scripts")
    script = create_script(folder.id, "Helper", language="javascript", content="original")

    local_script_editor.load_script(LocalScriptService.get_script_load_dict(script.id) or {})
    local_script_editor._pane.editor.setPlainText("updated body")
    local_script_editor._persist_for_autosave()

    loaded = LocalScriptService.get_script_load_dict(script.id)
    assert loaded is not None
    assert loaded["content"] == "updated body"
    assert not local_script_editor.is_dirty()


def test_js_local_script_defers_lsp_attach_until_loaded(
    local_script_editor: LocalScriptEditorWidget,
) -> None:
    """LSP attach stays deferred at init; with LSP disabled in tests, sync attach after load."""
    folder = create_folder("Mods")
    script = create_script(folder.id, "Entry", language="javascript", content="export const x = 1;")

    assert local_script_editor._pane.editor._lsp_attach_deferred is True

    local_script_editor.load_script(LocalScriptService.get_script_load_dict(script.id) or {})
    # Tests autouse-disable LSP, so async prep falls back to immediate attach.
    assert local_script_editor._pane.editor._lsp_attach_deferred is False
    assert local_script_editor._pane._local_script_id == script.id


def test_js_local_script_async_prep_keeps_deferred_until_finalize(
    local_script_editor: LocalScriptEditorWidget,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When async prep is enabled, load returns before LSP attach finalizes."""
    folder = create_folder("AsyncMods")
    script = create_script(folder.id, "Async", language="javascript", content="export const y = 2;")

    settings = QSettings("Postmark", "Postmark")
    settings.setValue("scripting/lsp_enabled", True)
    monkeypatch.setattr(prep_mod, "ASYNC_LOCAL_LSP_PREP", True)

    started: list[bool] = []

    class _SlowWorker:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.finished_with = MagicMock()

        def start(self) -> None:
            started.append(True)

    monkeypatch.setattr(
        "ui.request.request_editor.scripts.script_editor_pane.pane.LocalScriptLspPrepWorker",
        _SlowWorker,
    )

    local_script_editor.load_script(LocalScriptService.get_script_load_dict(script.id) or {})
    qapp.processEvents()

    assert started, "expected async prep worker to start"
    assert "export const y" in local_script_editor._pane.editor.toPlainText()
    assert local_script_editor._pane.editor._lsp_attach_deferred is True
    assert local_script_editor._pane._local_script_id == script.id

    local_script_editor._pane.cancel_async_lsp_prep()
    settings.setValue("scripting/lsp_enabled", False)
    qapp.processEvents()


def test_load_script_does_not_build_module_index_on_gui_thread(
    local_script_editor: LocalScriptEditorWidget,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``load_script`` does not scan the module index on the GUI thread; prep does later."""
    folder = create_folder("GuiIndex")
    script = create_script(
        folder.id,
        "gui",
        language="javascript",
        content="export const n = 1;\n",
    )
    data = LocalScriptService.get_script_load_dict(script.id) or {}

    settings = QSettings("Postmark", "Postmark")
    settings.setValue("scripting/lsp_enabled", True)
    monkeypatch.setattr(prep_mod, "ASYNC_LOCAL_LSP_PREP", True)

    index_calls = 0
    real_build = build_module_index

    def counting_build(session: Any) -> Any:
        nonlocal index_calls
        index_calls += 1
        return real_build(session)

    monkeypatch.setattr(
        "services.lsp.local_script_lsp_prep.build_module_index",
        counting_build,
    )
    monkeypatch.setattr(
        "services.scripting.local_script_modules.build_module_index",
        counting_build,
    )

    class _SlowWorker:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.finished_with = MagicMock()

        def start(self) -> None:
            pass

    monkeypatch.setattr(
        "ui.request.request_editor.scripts.script_editor_pane.pane.LocalScriptLspPrepWorker",
        _SlowWorker,
    )

    local_script_editor.load_script(data)
    qapp.processEvents()

    assert index_calls == 0
    assert local_script_editor._pane.editor._lsp_attach_deferred is True

    result = prepare_local_script_lsp_attach(
        script_id=script.id,
        language="javascript",
        buffer_text=data.get("content") or "",
        workspace=ensure_js_workspace(),
    )
    assert result.ok is True
    assert index_calls >= 1

    local_script_editor._pane.cancel_async_lsp_prep()
    settings.setValue("scripting/lsp_enabled", False)
    qapp.processEvents()
