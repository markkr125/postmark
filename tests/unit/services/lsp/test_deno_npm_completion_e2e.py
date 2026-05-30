"""End-to-end Deno LSP completion for ``pm.require('npm:…')`` variables (headless).

The completion UI is a process-wide singleton with ``parent=None``. Showing it during
tests can leave a top-level window on the user's desktop if pytest is interrupted.
This module never calls ``CompletionPopup.show`` and captures items via a patched
``_show_completion_popup`` instead.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from services.lsp.js_lsp_preamble import JS_LSP_PREAMBLE_LINE_COUNT
from services.lsp.server_registry import LspRegistry, reset_registry_for_tests
from services.scripting.runtime_settings import RuntimeSettings
from tests.qt_popup_cleanup import reset_code_editor_popups
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.code_editor.completion.engine import CompletionItem
from ui.widgets.code_editor.completion.popup import CompletionPopup


def _wait_for(predicate: Callable[[], bool], qapp: QApplication, timeout_ms: int = 15000) -> bool:
    """Poll *predicate* while pumping Qt events until *timeout_ms* elapses."""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture(autouse=True)
def _isolated_lsp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test workspace so xdist workers do not race on ``~/.local/share/postmark/lsp-workspace``."""
    root = tmp_path / "lsp-workspace"
    root.mkdir()
    monkeypatch.setattr(
        "services.lsp.servers._workspace.user_lsp_root",
        lambda: root,
    )


@pytest.fixture(autouse=True)
def _headless_completion_popup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block the shared completion popup from mapping onto the user desktop."""
    monkeypatch.setattr(CompletionPopup, "show", lambda _self: None)


@pytest.fixture
def _enable_lsp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(RuntimeSettings, "lsp_enabled", staticmethod(lambda: True))


@pytest.mark.skipif(
    not RuntimeSettings.deno_path() or not Path(RuntimeSettings.deno_path() or "").is_file(),
    reason="managed Deno not configured",
)
@pytest.mark.xdist_group("deno_lsp")
@pytest.mark.timeout(180)
class TestDenoNpmVariableCompletion:
    """Real Deno LSP must complete lodash members on ``npmVariableName.``."""

    def test_lodash_chunk_completion(
        self, qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch, _enable_lsp: None
    ) -> None:
        reset_registry_for_tests()
        editor = CodeEditorWidget()
        qtbot.addWidget(editor)
        captured: list[CompletionItem] = []

        def _capture_completion(items: list[CompletionItem], _prefix: str) -> None:
            captured[:] = items

        monkeypatch.setattr(editor, "_show_completion_popup", _capture_completion)

        try:
            script = "const npmVariableName = pm.require('npm:lodash');\nnpmVariableName."
            editor.setPlainText(script)
            editor.set_language("javascript")

            assert _wait_for(lambda: editor._lsp_adapter is not None, qapp, 20000), (
                "LSP adapter should attach when enabled"
            )
            adapter = editor._lsp_adapter
            assert adapter is not None
            assert _wait_for(lambda: adapter.is_ready, qapp, 20000), "Deno LSP did not become ready"

            assert _wait_for(
                lambda: (Path(adapter._js_workspace or "") / ".pm_require_cached.json").is_file(),
                qapp,
                120000,
            ), "npm:lodash was not cached for LSP types"

            adapter._flush_pm_require_types()
            adapter._republish_script_buffer()
            qapp.processEvents()
            time.sleep(0.3)
            qapp.processEvents()

            cur = editor.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            editor.setTextCursor(cur)

            editor._trigger_completion()

            assert _wait_for(lambda: bool(captured), qapp, 30000), (
                "completion did not return lodash members; "
                f"preamble_lines={JS_LSP_PREAMBLE_LINE_COUNT}"
            )
            labels = [item.label for item in captured]
            assert "chunk" in labels, f"expected lodash members, got sample: {labels[:25]}"
        finally:
            reset_code_editor_popups()
            editor.detach_lsp()
            inst = LspRegistry._instance
            if inst is not None:
                inst.shutdown()
            reset_registry_for_tests()
