"""AiProviderDialog — connection test lifecycle and save behaviour."""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtWidgets import QDialog

from services.ai.ai_config import AiModelEntry
from services.ai.provider_catalog import ModelSpec
from ui.dialogs.settings.ai_provider_dialog import AiProviderDialog


def _ollama_dialog(qtbot) -> AiProviderDialog:
    dlg = AiProviderDialog()
    qtbot.addWidget(dlg)
    idx = dlg._provider_combo.findData("ollama")
    assert idx >= 0
    dlg._provider_combo.setCurrentIndex(idx)
    return dlg


def test_cancel_during_test_waits_for_thread(qapp, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing the dialog while setup_provider runs must not abort the process."""

    def _slow_setup(**_kwargs: object) -> tuple[bool, str, tuple[()]]:
        time.sleep(0.4)
        return True, "Found 1 model(s)", ()

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _slow_setup,
    )
    dlg = _ollama_dialog(qtbot)
    dlg._on_refresh_models()
    assert dlg._setup_thread is not None
    qtbot.wait(50)
    dlg.reject()
    assert dlg.result() == QDialog.DialogCode.Rejected


def test_cancel_test_button_stops_without_closing(
    qapp, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancel test stops the worker and re-enables Save."""
    hold = threading.Event()

    def _slow_setup(**_kwargs: object) -> tuple[bool, str, tuple[ModelSpec, ...]]:
        hold.wait(timeout=10.0)
        return True, "Found 1 model(s)", (ModelSpec("ollama/x", "x", 8192, True, False, True),)

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _slow_setup,
    )
    dlg = _ollama_dialog(qtbot)
    dlg._on_refresh_models()
    assert dlg._setup_thread is not None
    assert not dlg._test_btn.isEnabled()
    assert not dlg._save_btn.isEnabled()
    dlg._on_cancel_test()
    hold.set()
    qtbot.waitUntil(lambda: dlg._setup_thread is None, timeout=15_000)
    assert dlg._test_btn.isEnabled()
    assert dlg._save_btn.isEnabled()


def test_save_skips_retest_when_fingerprint_unchanged(
    qapp, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save accepts without calling setup_provider when credentials are unchanged."""
    calls: list[int] = []

    def _setup(**_kwargs: object) -> tuple[bool, str, tuple[ModelSpec, ...]]:
        calls.append(1)
        return True, "Found 1 model(s)", (ModelSpec("ollama/x", "x", 8192, True, False, True),)

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _setup,
    )
    dlg = _ollama_dialog(qtbot)
    dlg._on_refresh_models()
    qtbot.waitUntil(lambda: dlg._setup_thread is None, timeout=15_000)
    assert calls == [1]
    dlg._label_edit.setText("My Ollama")
    dlg._on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert calls == [1]


def test_save_runs_test_when_url_changed(qapp, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing the base URL after a successful test triggers a new test on Save."""
    calls: list[int] = []

    def _setup(**_kwargs: object) -> tuple[bool, str, tuple[ModelSpec, ...]]:
        calls.append(1)
        return True, "Found 1 model(s)", (ModelSpec("ollama/x", "x", 8192, True, False, True),)

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _setup,
    )
    dlg = _ollama_dialog(qtbot)
    dlg._on_refresh_models()
    qtbot.waitUntil(lambda: dlg._setup_thread is None, timeout=15_000)
    base = dlg._cred_edits.get("base_url")
    assert isinstance(base, type(dlg._label_edit))
    base.setText("http://127.0.0.1:11435")
    dlg._on_accept()
    qtbot.waitUntil(lambda: len(calls) >= 2, timeout=15_000)
    qtbot.waitUntil(lambda: dlg._setup_thread is None, timeout=15_000)
    assert len(calls) == 2


def test_save_auto_test_failure_blocks_accept(qapp, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Save runs test when needed and stays open on failure."""

    def _fail(**_kwargs: object) -> tuple[bool, str, tuple[()]]:
        return False, "Connection refused", ()

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _fail,
    )
    dlg = _ollama_dialog(qtbot)
    dlg._on_accept()
    qtbot.waitUntil(lambda: dlg._setup_thread is None, timeout=15_000)
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert "Connection refused" in dlg._error_label.text()


def test_ollama_shows_default_context_combo(qapp, qtbot) -> None:
    """Ollama provider dialog includes a default context size selector (32k default)."""
    dlg = _ollama_dialog(qtbot)
    assert dlg._ollama_context_combo is not None
    assert dlg._collect_ollama_default_context() == 32_768


def test_edit_ollama_restores_saved_default_context(qapp, qtbot) -> None:
    """Edit dialog selects the saved Ollama default context."""
    entry: AiModelEntry = {
        "id": "m1",
        "provider": "ollama",
        "label": "llama",
        "provider_display_name": "Home",
        "model": "ollama/llama3:latest",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "default_context": 131_072,
    }
    dlg = AiProviderDialog(entry=entry)
    qtbot.addWidget(dlg)
    assert dlg._collect_ollama_default_context() == 131_072


def test_edit_display_name_only_skips_connection_test(
    qapp, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Renaming a provider on edit does not require test connection on Save."""
    calls: list[int] = []

    def _setup(**_kwargs: object) -> tuple[bool, str, tuple[()]]:
        calls.append(1)
        return True, "Found 1 model(s)", ()

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _setup,
    )

    def _secret(ref: str) -> str | None:
        return "sk-test" if ref == "ai:m1" else None

    monkeypatch.setattr("ui.dialogs.settings.ai_provider_dialog.get_secret", _secret)
    monkeypatch.setattr("ui.dialogs.settings.ai_page_actions.get_secret", _secret)
    entry: AiModelEntry = {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "provider_display_name": "OpenAI",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "token",
        "auth_ref": "ai:m1",
    }
    dlg = AiProviderDialog(entry=entry, existing_entries=[entry])
    qtbot.addWidget(dlg)
    dlg._label_edit.setText("Work OpenAI")
    dlg._on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert calls == []
    rows = dlg.result_entries()
    assert len(rows) == 1
    assert rows[0]["provider_display_name"] == "Work OpenAI"
    assert rows[0]["model"] == "openai/gpt-4o"


def test_edit_ollama_default_context_only_skips_connection_test(
    qapp, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing Ollama default context on edit does not require test connection on Save."""
    calls: list[int] = []

    def _setup(**_kwargs: object) -> tuple[bool, str, tuple[()]]:
        calls.append(1)
        return True, "Found 1 model(s)", ()

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _setup,
    )
    entry: AiModelEntry = {
        "id": "m1",
        "provider": "ollama",
        "label": "llama3",
        "provider_display_name": "Home Ollama",
        "model": "ollama/llama3:latest",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "default_context": 32_768,
    }
    dlg = AiProviderDialog(entry=entry, existing_entries=[entry])
    qtbot.addWidget(dlg)
    assert dlg._ollama_context_combo is not None
    idx = dlg._ollama_context_combo.findData(65_536)
    dlg._ollama_context_combo.setCurrentIndex(idx)
    dlg._on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert calls == []
    rows = dlg.result_entries()
    assert rows[0]["default_context"] == 65_536
    assert rows[0]["provider_display_name"] == "Home Ollama"


def test_edit_ollama_context_after_test_skips_retest_on_save(
    qapp, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a successful test, changing default context alone does not re-run on Save."""
    calls: list[int] = []

    def _setup(**_kwargs: object) -> tuple[bool, str, tuple[ModelSpec, ...]]:
        calls.append(1)
        return True, "Found 1 model(s)", (ModelSpec("ollama/x", "x", 8192, True, False, True),)

    monkeypatch.setattr(
        "ui.dialogs.settings.ai_provider_workers.setup_provider",
        _setup,
    )
    entry: AiModelEntry = {
        "id": "m1",
        "provider": "ollama",
        "label": "llama3",
        "provider_display_name": "Home",
        "model": "ollama/llama3:latest",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "default_context": 32_768,
    }
    dlg = AiProviderDialog(entry=entry, existing_entries=[entry])
    qtbot.addWidget(dlg)
    dlg._on_refresh_models()
    qtbot.waitUntil(lambda: dlg._setup_thread is None, timeout=15_000)
    assert calls == [1]
    combo = dlg._ollama_context_combo
    assert combo is not None
    idx = combo.findData(131_072)
    assert idx >= 0
    combo.setCurrentIndex(idx)
    dlg._on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert calls == [1]


def test_edit_prefills_models_list_from_saved_rows(qapp, qtbot) -> None:
    """Edit provider shows models already stored for that connection."""
    entries: list[AiModelEntry] = [
        {
            "id": "m1",
            "provider": "ollama",
            "label": "llama3",
            "provider_display_name": "Home",
            "model": "ollama/llama3:latest",
            "base_url": "http://127.0.0.1:11434",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "context": 8192,
            "tools": True,
            "enabled": True,
        },
        {
            "id": "m2",
            "provider": "ollama",
            "label": "devstral",
            "provider_display_name": "Home",
            "model": "ollama/devstral:latest",
            "base_url": "http://127.0.0.1:11434",
            "api_version": "",
            "auth_kind": "none",
            "auth_ref": "",
            "enabled": False,
        },
    ]
    dlg = AiProviderDialog(entry=entries[0], existing_entries=entries)
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: dlg._models_list.count() == 2, timeout=5000)
    assert dlg._fetched_models == ()
    texts = {dlg._models_list.item(i).text() for i in range(2)}
    assert any("llama3" in t for t in texts)
    assert any("devstral" in t for t in texts)


def test_edit_prefills_provider_display_name(qapp) -> None:
    """Edit uses provider_display_name, not the first model row label."""
    entry: AiModelEntry = {
        "id": "m1",
        "provider": "ollama",
        "label": "devstral",
        "provider_display_name": "Home GPU",
        "model": "ollama/devstral:latest",
        "base_url": "http://127.0.0.1:11434",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "ai:test",
    }
    dlg = AiProviderDialog(entry=entry)
    assert dlg._label_edit.text() == "Home GPU"


def test_add_allocates_numbered_display_name_when_taken(qapp) -> None:
    """Empty display name on add picks catalog name with a numeric suffix when needed."""
    dlg = AiProviderDialog(
        entry=None,
        existing_provider_display_names=frozenset({"Ollama (local)"}),
    )
    idx = dlg._provider_combo.findData("ollama")
    assert idx >= 0
    dlg._provider_combo.setCurrentIndex(idx)
    dlg._label_is_auto = True
    dlg._apply_default_display_name()
    assert dlg._label_edit.text() == "Ollama (local) 2"
