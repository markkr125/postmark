"""Tests for background local-script LSP prep."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.lsp.local_script_lsp_prep import (
    LocalScriptLspPrepResult,
    prepare_local_script_lsp_attach,
)
from services.lsp.local_script_lsp_prep_worker import LocalScriptLspPrepWorker
from services.lsp.servers._workspace import ensure_js_workspace
from services.scripting.local_script_modules import build_module_index
from ui.widgets.code_editor import editor_lsp_glue as lsp_glue


def test_prepare_local_script_lsp_attach_success() -> None:
    """Prep mirrors a JS local script and returns a file URI."""
    folder = create_folder("PrepFolder")
    script = create_script(
        folder.id,
        "entry",
        language="javascript",
        content="export const x = 1;\n",
    )
    workspace = ensure_js_workspace()
    result = prepare_local_script_lsp_attach(
        script_id=script.id,
        language="javascript",
        buffer_text="export const x = 1;\n",
        workspace=workspace,
    )
    assert result.ok is True
    assert result.target_uri is not None
    assert result.target_uri.startswith("file://")
    assert result.error_message is None


def test_prepare_local_script_lsp_attach_missing_script() -> None:
    """Unknown script id returns a failed result without raising."""
    workspace = ensure_js_workspace()
    result = prepare_local_script_lsp_attach(
        script_id=999_999,
        language="javascript",
        buffer_text="",
        workspace=workspace,
    )
    assert result.ok is False
    assert result.target_uri is None


def test_prepare_local_script_lsp_attach_builds_module_index_once(monkeypatch) -> None:
    """Prep builds the module index once per call (not repeatedly on the GUI attach path)."""
    folder = create_folder("IndexOnce")
    script = create_script(
        folder.id,
        "entry",
        language="javascript",
        content="export const x = 1;\n",
    )
    calls = 0
    real_build = build_module_index

    def counting_build(session: Any) -> Any:
        nonlocal calls
        calls += 1
        return real_build(session)

    monkeypatch.setattr(
        "services.lsp.local_script_lsp_prep.build_module_index",
        counting_build,
    )
    result = prepare_local_script_lsp_attach(
        script_id=script.id,
        language="javascript",
        buffer_text="export const x = 1;\n",
        workspace=ensure_js_workspace(),
    )
    assert result.ok is True
    assert calls == 1


def test_local_script_lsp_prep_worker_emits_and_stops(qapp, qtbot) -> None:
    """Worker thread runs prep off the GUI thread and exits cleanly."""
    folder = create_folder("WorkerFolder")
    script = create_script(
        folder.id,
        "worker",
        language="javascript",
        content="export const z = 3;\n",
    )
    worker = LocalScriptLspPrepWorker(
        1,
        script.id,
        "javascript",
        "export const z = 3;\n",
        ensure_js_workspace(),
    )
    with qtbot.waitSignal(worker.finished_with, timeout=30_000) as blocker:
        worker.start()
    attach_token, result = blocker.args
    assert attach_token == 1
    assert isinstance(result, LocalScriptLspPrepResult)
    assert result.ok is True
    assert result.target_uri is not None
    worker.wait(5000)
    assert not worker.isRunning()


def test_prepare_local_script_lsp_attach_rejects_python() -> None:
    """Async prep is JS/TS only; Python uses synchronous attach."""
    folder = create_folder("PyFolder")
    script = create_script(folder.id, "main", language="python", content="x = 1\n")
    result = prepare_local_script_lsp_attach(
        script_id=script.id,
        language="python",
        buffer_text="x = 1\n",
        workspace=ensure_js_workspace(),
    )
    assert result.ok is False
    assert "JS/TS" in (result.error_message or "")


def test_finalize_local_script_lsp_attach_ignores_stale_token(qapp, monkeypatch) -> None:
    """Finalize is a no-op when the attach token no longer matches the editor."""
    from PySide6.QtWidgets import QApplication

    from ui.widgets.code_editor.editor_widget import CodeEditorWidget

    editor = CodeEditorWidget()
    editor.next_lsp_attach_token()
    attach_mock = MagicMock()
    monkeypatch.setattr(lsp_glue, "attach_lsp", attach_mock)
    prep = LocalScriptLspPrepResult(
        ok=True,
        target_uri="file:///tmp/example.js",
        index_changed=False,
        error_message=None,
    )
    lsp_glue.finalize_local_script_lsp_attach(
        editor,
        "javascript",
        prep,
        attach_token=0,
    )
    attach_mock.assert_not_called()
    QApplication.processEvents()


def test_finalize_local_script_lsp_attach_with_matching_token(qapp, monkeypatch) -> None:
    """Finalize calls attach when the token matches."""
    from PySide6.QtWidgets import QApplication

    from ui.widgets.code_editor.editor_widget import CodeEditorWidget

    editor = CodeEditorWidget()
    token = editor.lsp_attach_token()
    attach_mock = MagicMock()
    monkeypatch.setattr(lsp_glue, "attach_lsp", attach_mock)
    prep = LocalScriptLspPrepResult(
        ok=True,
        target_uri="file:///tmp/example.js",
        index_changed=False,
        error_message=None,
    )
    lsp_glue.finalize_local_script_lsp_attach(
        editor,
        "javascript",
        prep,
        attach_token=token,
    )
    attach_mock.assert_called_once()
    QApplication.processEvents()
