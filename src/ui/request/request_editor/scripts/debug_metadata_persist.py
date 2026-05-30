"""Debounced persistence for breakpoints and watch expressions."""

from __future__ import annotations

from typing import Any, Protocol, cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget
from shiboken6 import Shiboken

from services.collection_service import CollectionService
from services.scripting.debug_script_metadata import (
    DEBUG_METADATA_KEY,
    SCRIPT_TYPE_PRE,
    SCRIPT_TYPE_TEST,
    DebugScriptSlice,
    merge_debug_into_scripts_dict,
    parse_from_scripts_dict,
    per_type_blob_to_db_dict,
    slice_is_empty,
)
from ui.request.request_editor.scripts.script_editor_pane import ScriptEditorPane

_DEBUG_PERSIST_MS = 500


class _DebugPersistHost(Protocol):
    """Editor host that owns pre/test script panes."""

    _request_id: int | None
    _collection_id: int | None
    _scripts_editor_materialized: bool
    _pre_pane: ScriptEditorPane
    _test_pane: ScriptEditorPane
    _loading: bool

    def _persist_open_tabs(self) -> None: ...


class _DebugMetadataPersistMixin:
    """Mixin: load/save debug slices and debounced DB or draft-session persist."""

    _debug_metadata_timer: QTimer
    _draft_debug_session_blob: dict[str, Any] | None
    _pre_pane: ScriptEditorPane
    _test_pane: ScriptEditorPane

    def _debug_persist_host(self) -> _DebugPersistHost:
        """Return this mixin host with protocol typing."""
        return cast(_DebugPersistHost, self)

    @staticmethod
    def _debug_persist_host_is_live(widget: QWidget) -> bool:
        """Return whether *widget* is still a valid Qt object (not deleted)."""
        return Shiboken.isValid(widget)

    def _init_debug_metadata_persist(self) -> None:
        """Create the debounce timer (idempotent)."""
        if getattr(self, "_debug_metadata_timer", None) is not None:
            return
        host_widget = cast(QWidget, self)
        self._debug_metadata_timer = QTimer(host_widget)
        self._debug_metadata_timer.setSingleShot(True)
        self._debug_metadata_timer.setInterval(_DEBUG_PERSIST_MS)
        self._debug_metadata_timer.timeout.connect(self._flush_debug_metadata_persist)
        self._draft_debug_session_blob = None

    def _bind_debug_metadata_persist(self) -> None:
        """Wire pane editors to the host debounce timer."""
        self._init_debug_metadata_persist()
        for pane in (self._pre_pane, self._test_pane):
            pane.bind_debug_metadata_persist(self._schedule_debug_metadata_persist)

    def cancel_debug_metadata_persist(self) -> None:
        """Stop a pending debounced write (call before explicit save or tab close)."""
        if getattr(self, "_debug_metadata_timer", None) is not None:
            self._debug_metadata_timer.stop()

    def flush_debug_metadata_persist_sync(self) -> None:
        """Cancel any pending debounce and persist debug metadata immediately."""
        self.cancel_debug_metadata_persist()
        if not self._debug_persist_host_is_live(cast(QWidget, self)):
            return
        self._flush_debug_metadata_persist()

    def _schedule_debug_metadata_persist(self) -> None:
        """Restart debounced persist unless the host is loading."""
        host = self._debug_persist_host()
        if getattr(host, "_loading", False):
            return
        if not getattr(host, "_scripts_editor_materialized", False):
            return
        if not self._debug_persist_host_is_live(cast(QWidget, self)):
            return
        self._init_debug_metadata_persist()
        self._debug_metadata_timer.start()

    def _flush_debug_metadata_persist(self) -> None:
        """Write debug metadata to DB or draft tab session."""
        if not self._debug_persist_host_is_live(cast(QWidget, self)):
            return
        host = self._debug_persist_host()
        if not getattr(host, "_scripts_editor_materialized", False):
            return
        rid = getattr(host, "_request_id", None)
        cid = getattr(host, "_collection_id", None)
        per_type = self._collect_debug_per_type()
        if rid is not None:
            blob = per_type_blob_to_db_dict(per_type)
            CollectionService.merge_request_scripts_debug(rid, blob)
            return
        if cid is not None:
            blob = per_type_blob_to_db_dict(per_type)
            CollectionService.merge_collection_events_debug(cid, blob)
            return
        self._draft_debug_session_blob = per_type_blob_to_db_dict(per_type)
        persist_tabs = getattr(host, "_persist_open_tabs", None)
        if callable(persist_tabs):
            persist_tabs()

    def _collect_debug_per_type(self) -> dict[str, DebugScriptSlice]:
        """Collect slices from both script panes."""
        return {
            SCRIPT_TYPE_PRE: self._pre_pane.collect_debug_slice(),
            SCRIPT_TYPE_TEST: self._test_pane.collect_debug_slice(),
        }

    def _apply_debug_from_scripts_raw(self, scripts: Any) -> None:
        """Restore breakpoints and watches from a scripts/events dict."""
        if not getattr(self, "_scripts_editor_materialized", False):
            return
        per_type = parse_from_scripts_dict(scripts)
        self._pre_pane.apply_debug_slice(per_type.get(SCRIPT_TYPE_PRE) or DebugScriptSlice())
        self._test_pane.apply_debug_slice(per_type.get(SCRIPT_TYPE_TEST) or DebugScriptSlice())

    def collect_draft_debug_blob(self) -> dict[str, Any] | None:
        """Return draft session ``debug`` subtree for tab persistence."""
        if getattr(self, "_scripts_editor_materialized", False):
            blob = per_type_blob_to_db_dict(self._collect_debug_per_type())
            return blob or None
        draft = getattr(self, "_draft_debug_session_blob", None)
        return draft if isinstance(draft, dict) and draft else None

    def apply_draft_debug_blob(self, blob: Any) -> None:
        """Restore draft session debug metadata after tab restore."""
        if not isinstance(blob, dict) or not blob:
            return
        if not getattr(self, "_scripts_editor_materialized", False):
            self._draft_debug_session_blob = dict(blob)
            return
        self._apply_debug_from_scripts_raw({DEBUG_METADATA_KEY: blob})

    def merge_debug_into_scripts_output(
        self,
        data: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Attach ``debug`` to scripts dict from live panes when materialised."""
        if not getattr(self, "_scripts_editor_materialized", False):
            if data is None and getattr(self, "_draft_debug_session_blob", None):
                return merge_debug_into_scripts_dict(
                    None,
                    parse_from_scripts_dict({DEBUG_METADATA_KEY: self._draft_debug_session_blob}),
                )
            return data
        per_type = self._collect_debug_per_type()
        has_debug = any(
            not slice_is_empty(per_type.get(st)) for st in (SCRIPT_TYPE_PRE, SCRIPT_TYPE_TEST)
        )
        if data is None and not has_debug:
            return None
        return merge_debug_into_scripts_dict(data, per_type)
