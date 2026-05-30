"""Tests for :class:`_DebugMetadataPersistMixin` debounce and explicit-save cancel."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from services.scripting.debug_script_metadata import DebugScriptSlice
from ui.request.request_editor.scripts.debug_metadata_persist import (
    _DEBUG_PERSIST_MS,
    _DebugMetadataPersistMixin,
)


class _StubPane:
    """Minimal script pane for mixin tests."""

    def collect_debug_slice(self) -> DebugScriptSlice:
        return DebugScriptSlice(breakpoints=[], watches=[])

    def bind_debug_metadata_persist(self, _callback: object) -> None:
        pass


class _StubHost(QWidget, _DebugMetadataPersistMixin):
    """Host widget with mixin for timer tests."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request_id = 42
        self._collection_id = None
        self._scripts_editor_materialized = True
        self._loading = False
        self._pre_pane = _StubPane()  # type: ignore[assignment]
        self._test_pane = _StubPane()  # type: ignore[assignment]
        self._init_debug_metadata_persist()


def test_cancel_prevents_debounced_merge(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stopping the timer before it fires must skip ``merge_request_scripts_debug``."""
    merge_calls: list[tuple[int, dict[str, Any]]] = []

    monkeypatch.setattr(
        "ui.request.request_editor.scripts.debug_metadata_persist.CollectionService.merge_request_scripts_debug",
        lambda request_id, debug: merge_calls.append((request_id, debug)),
    )

    host = _StubHost()
    qtbot.addWidget(host)
    host._schedule_debug_metadata_persist()
    assert host._debug_metadata_timer.isActive()
    host.cancel_debug_metadata_persist()
    assert not host._debug_metadata_timer.isActive()
    qtbot.wait(_DEBUG_PERSIST_MS + 100)
    assert merge_calls == []


def test_explicit_save_path_cancels_before_collect(
    qapp: QApplication,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel-then-read (as ``get_request_data``) leaves no pending debounced DB write."""
    merge_calls: list[int] = []

    monkeypatch.setattr(
        "ui.request.request_editor.scripts.debug_metadata_persist.CollectionService.merge_request_scripts_debug",
        lambda request_id, _debug: merge_calls.append(request_id),
    )

    host = _StubHost()
    qtbot.addWidget(host)
    host._schedule_debug_metadata_persist()
    host.cancel_debug_metadata_persist()
    _ = host.merge_debug_into_scripts_output({"pre_request": "code"})
    qtbot.wait(_DEBUG_PERSIST_MS + 100)
    assert merge_calls == []


def test_flush_sync_runs_merge_once(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``flush_debug_metadata_persist_sync`` persists immediately (tab-close path)."""
    merge_calls: list[int] = []

    monkeypatch.setattr(
        "ui.request.request_editor.scripts.debug_metadata_persist.CollectionService.merge_request_scripts_debug",
        lambda request_id, _debug: merge_calls.append(request_id),
    )

    host = _StubHost()
    host.flush_debug_metadata_persist_sync()
    assert merge_calls == [42]
    assert not host._debug_metadata_timer.isActive()
