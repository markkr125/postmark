"""Centre-pane editor for a persisted local script."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from typing import Any
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from services.local_script_service import LocalScriptLoadDict, LocalScriptService
from services.scripting.debug_script_metadata import (
    parse_from_local_metadata,
    slice_is_empty,
    slice_to_local_metadata,
)
from ui.request.request_editor.scripts.script_editor_pane import (
    ScriptEditorPane,
    ScriptEditorPaneOptions,
)


class LocalScriptEditorWidget(QWidget):
    """Local script tab using the shared advanced script editor stack."""

    dirty_changed = Signal(bool)
    save_requested = Signal()
    local_script_saved = Signal(int)
    open_scripting_settings_requested = Signal()
    debug_step_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the script editor pane."""
        super().__init__(parent)
        self._script_id: int | None = None

        layout = QVBoxLayout(self)
        # Match RequestEditorWidget root insets so the shared script toolbar aligns.
        layout.setContentsMargins(12, 8, 12, 6)
        layout.setSpacing(0)

        opts = ScriptEditorPaneOptions(
            script_type="pre_request",
            host_kind="local_script",
            placeholder="Local script\u2026",
            show_inherited_banner=False,
            show_run_all=False,
            show_version_history=True,
            show_auto_save=True,
            enable_test_gutter=False,
            use_host_version_timer=False,
        )
        self._pane = ScriptEditorPane(opts, parent=self)
        layout.addWidget(self._pane, 1)

        self._pane.dirty_changed.connect(self.dirty_changed.emit)
        self._pane.save_requested.connect(self.save_requested.emit)
        self._pane.open_scripting_settings_requested.connect(
            self.open_scripting_settings_requested.emit
        )
        self._pane.debug_step_requested.connect(self.debug_step_requested.emit)
        self._pane._history_btn.clicked.connect(self._pane.open_version_history)
        self._pane.persist_content_callback = self._persist_for_autosave

        # Aliases used by MainWindow debug pause/step/cleanup (same as _ScriptsMixin).
        self._pre_request_edit = self._pane.editor
        self._test_script_edit = self._pane.editor
        self._pre_output_panel = self._pane.output_panel
        self._test_output_panel = None
        self._debug_controls = {"pre_request": self._pane.debug_controls}

        self._debug_metadata_timer = QTimer(self)
        self._debug_metadata_timer.setSingleShot(True)
        self._debug_metadata_timer.setInterval(500)
        self._debug_metadata_timer.timeout.connect(self._flush_debug_metadata_persist)
        self._pane.bind_debug_metadata_persist(self._schedule_debug_metadata_persist)
        self.destroyed.connect(self._cancel_async_lsp_prep_on_destroy)

    def _cancel_async_lsp_prep_on_destroy(self, *_args: object) -> None:
        """Ensure background prep is stopped when the tab widget is destroyed."""
        from shiboken6 import Shiboken

        pane = getattr(self, "_pane", None)
        if pane is not None and Shiboken.isValid(pane):
            pane.cancel_async_lsp_prep()

    def cancel_debug_metadata_persist(self) -> None:
        """Stop a pending debounced debug-metadata write."""
        self._debug_metadata_timer.stop()

    def flush_debug_metadata_persist_sync(self) -> None:
        """Cancel any pending debounce and persist debug metadata immediately."""
        self.cancel_debug_metadata_persist()
        self._flush_debug_metadata_persist()

    def _schedule_debug_metadata_persist(self) -> None:
        """Restart debounced persist for breakpoints and watches."""
        if self._script_id is None or self._pane._loading:
            return
        self._debug_metadata_timer.start()

    def _flush_debug_metadata_persist(self) -> None:
        """Write flat debug metadata to the database."""
        if self._script_id is None:
            return
        sl = self._pane.collect_debug_slice()
        meta: dict[str, Any] | None = (
            slice_to_local_metadata(sl) if not slice_is_empty(sl) else None
        )
        LocalScriptService.merge_debug_metadata(self._script_id, meta)

    def _schedule_refresh_script_split_full_width_line(self) -> None:
        """Reposition the editor/output divider (used by :class:`ScriptOutputPanel`)."""
        self._pane._schedule_refresh_script_split_full_width_line()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep the scripts split line aligned when the tab is resized."""
        super().resizeEvent(event)
        self._schedule_refresh_script_split_full_width_line()

    @property
    def script_id(self) -> int | None:
        """Return the loaded script primary key."""
        return self._script_id

    def is_dirty(self) -> bool:
        """Return whether the buffer differs from the last saved content."""
        return self._pane.is_dirty()

    def load_script(self, data: LocalScriptLoadDict) -> None:
        """Populate the editor from *data*."""
        self._script_id = data.get("id")
        language = data.get("language") or "javascript"
        module_format = data.get("module_format") or "esm"
        self._pane.set_version_owner(local_script_id=self._script_id)
        self._pane.load_content(
            data.get("content") or "",
            language,
            module_format=module_format,
        )
        meta = data.get("debug_metadata")
        if meta is not None:
            self._pane.apply_debug_slice(parse_from_local_metadata(meta))
        QTimer.singleShot(0, self._schedule_refresh_script_split_full_width_line)
        QTimer.singleShot(80, self._schedule_refresh_script_split_full_width_line)

    def save(self) -> bool:
        """Persist the current buffer. Returns ``True`` on success."""
        if self._script_id is None:
            return False
        self.flush_debug_metadata_persist_sync()
        content, language = self._pane.get_content()
        module_format = self._pane.editor.script_module_format
        LocalScriptService.save_script_content(
            self._script_id,
            content,
            language,
            module_format=module_format,
        )
        self._pane.load_content(content, language, module_format=module_format)
        self._pane.capture_version_now()
        if self._script_id is not None:
            self.local_script_saved.emit(self._script_id)
        return True

    def go_to_position(self, line_1: int, column_1: int) -> None:
        """Move the editor cursor to a 1-based line/column."""
        from services.lsp.qt_lsp_offsets import lsp_to_qpos

        doc = self._pane.editor.document()
        pos = lsp_to_qpos(doc, max(0, line_1 - 1), max(0, column_1 - 1))
        cur = self._pane.editor.textCursor()
        cur.setPosition(pos)
        self._pane.editor.setTextCursor(cur)
        self._pane.editor.setFocus()
        self._pane.editor.centerCursor()

    def _persist_for_autosave(self) -> None:
        """Write script body to the database when auto-save captures a version."""
        if self._script_id is None:
            return
        content, language = self._pane.get_content()
        LocalScriptService.save_script_content(self._script_id, content, language)
        self._pane.set_loading(True)
        try:
            self._pane.editor.document().setModified(False)
        finally:
            self._pane.set_loading(False)
        self.dirty_changed.emit(False)
        if self._script_id is not None:
            self.local_script_saved.emit(self._script_id)
