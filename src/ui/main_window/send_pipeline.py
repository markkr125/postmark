"""HTTP send pipeline mixin for the main window.

Provides ``_SendPipelineMixin`` with background HTTP request execution,
cancel, debug mode, and cleanup methods.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSettings, QThread

if TYPE_CHECKING:
    from services.scripting.debug import DebugProtocol
    from ui.environments.environment_sidebar_panel import EnvironmentSidebarPanel
    from ui.panels.history_panel import HistoryPanel
    from ui.request.http_worker import HttpSendWorker
    from ui.request.navigation.request_tab_bar import RequestTabBar
    from ui.request.navigation.tab_manager import TabContext
    from ui.request.request_editor import RequestEditorWidget
    from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel
    from ui.request.response_viewer import ResponseViewerWidget
    from ui.sidebar import RightSidebar

from ui.main_window.send_pipeline_debug import (
    _debug_hover_root_objects as _debug_hover_root_objects,
    _ensure_script_host_materialized as _ensure_script_host_materialized,
    _merge_debug_hover_values as _merge_debug_hover_values,
)
from ui.main_window.send_pipeline_debug_session import (
    end_debug_ui as _impl_end_debug_ui,
    end_inline_script_debug as _impl_end_inline_script_debug,
    on_debug_error as _impl_on_debug_error,
    on_debug_finished as _impl_on_debug_finished,
    on_debug_paused as _impl_on_debug_paused,
    on_debug_step as _impl_on_debug_step,
)
from ui.main_window.send_pipeline_postresponse import (
    on_send_finished as _impl_on_send_finished,
    run_post_response_script_with_live_response as _impl_run_post_response,
)

logger = logging.getLogger(__name__)


def _resolve_post_response_language(
    editor: RequestEditorWidget,
    test_scripts: list[Any] | None,
) -> str:
    """Pick the language for compiled declarative assertions."""
    scripts = editor.get_request_data().get("scripts") or {}
    if isinstance(scripts, dict):
        lang = scripts.get("test_language") or scripts.get("language")
        if lang:
            return str(lang).lower()
    if test_scripts:
        return str(test_scripts[0].get("language", "javascript")).lower()
    return "javascript"


def _build_declarative_test_script(
    request_id: int,
    editor: RequestEditorWidget,
    test_scripts: list[Any] | None,
) -> Any:
    """Compile DB-backed declarative assertions for the send worker."""
    from services.assertion_service import AssertionService

    language = _resolve_post_response_language(editor, test_scripts)
    return AssertionService.build_declarative_script_entry(request_id, language)


def _scripts_enabled() -> bool:
    """Return ``True`` if the global scripting toggle is on."""
    from ui.styling.theme_manager import _APP, _ORG

    val = QSettings(_ORG, _APP).value("scripting/enabled", True)
    if isinstance(val, str):
        return val.lower() not in {"0", "false", "no", "off", ""}
    return bool(val)


class _SendPipelineMixin:
    """Mixin that adds the HTTP send/cancel/cleanup pipeline.

    Expects the host class to provide ``_tabs``, ``_tab_bar``,
    ``_send_thread``, ``_send_worker``, ``request_widget``,
    ``response_widget``, ``_env_selector`` (``EnvironmentSidebarPanel``),
    and ``_history_panel``.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _send_thread: QThread | None
    _send_worker: HttpSendWorker | None
    _tab_bar: RequestTabBar
    _env_selector: EnvironmentSidebarPanel
    _history_panel: HistoryPanel
    _right_sidebar: RightSidebar
    request_widget: RequestEditorWidget
    response_widget: ResponseViewerWidget
    _debug_protocol: DebugProtocol | None
    _inline_test_run: dict[str, Any] | None

    def _current_tab_context(self) -> TabContext | None: ...

    if TYPE_CHECKING:

        def _refresh_sidebar(self, ctx: TabContext | None = None) -> None: ...

    def _on_send_request(self) -> None:
        """Send the current request on a background thread."""
        ctx: TabContext | None = self._current_tab_context()

        # Folder tabs cannot send requests
        if ctx is not None and ctx.tab_type in ("folder", "environments", "local_script"):
            return

        # If already sending, treat as cancel
        if ctx is not None and ctx.is_sending:
            self._cancel_send()
            if getattr(self, "_inline_test_run", None) is not None:
                self._inline_test_run = None
            return
        if self._send_thread is not None and self._send_thread.isRunning():
            self._cancel_send()
            if getattr(self, "_inline_test_run", None) is not None:
                self._inline_test_run = None
            return

        # 1. Gather request data from the current editor
        if ctx is not None:
            editor = ctx.require_editor()
            viewer = ctx.require_response_viewer()
        else:
            editor = self.request_widget
            viewer = self.response_widget

        method = editor._method_combo.currentText()
        url = editor._url_input.text().strip()
        if not url:
            viewer.show_error("URL is empty")
            inline_test = getattr(self, "_inline_test_run", None)
            if inline_test is not None:
                panel = inline_test.get("panel")
                for btn in (inline_test.get("run_btn"), inline_test.get("debug_btn")):
                    if btn is not None:
                        btn.setEnabled(True)
                self._inline_test_run = None
                if panel is not None:
                    panel.show_error("Live-response send failed: URL is empty")
            return

        headers = editor.get_headers_text()
        body = editor.get_request_data().get("body") or None

        # 2. Gather auth (with inheritance) and env_id for worker thread
        from services.collection_service import CollectionService

        auth_data = editor._get_auth_data()
        if ctx and ctx.request_id and auth_data is None:
            inherited = CollectionService.get_request_inherited_auth(ctx.request_id)
            if inherited:
                auth_data = inherited

        env_id = self._env_selector.current_environment_id()

        request_id = ctx.request_id if ctx else None

        # 3. Tear down any previous send thread
        if ctx is not None:
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()

        # 4. Show loading state, spinner, and toggle button to Cancel
        viewer.show_loading()
        self._set_send_button_cancel(True)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=True)

        # 5. Create worker — variable resolution + auth on worker thread
        # 5a. Resolve script chain for this request
        from services.script_service import ScriptService
        from ui.request.http_worker import HttpSendWorker

        inline_test = getattr(self, "_inline_test_run", None)
        pre_scripts = None
        test_scripts = None
        declarative_test_script = None
        if _scripts_enabled() and inline_test is None:
            if request_id:
                pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
                declarative_test_script = _build_declarative_test_script(
                    request_id,
                    editor,
                    test_scripts,
                )
            else:
                # Draft: use inline scripts from the editor
                scripts_data = editor.get_request_data().get("scripts")
                if scripts_data:
                    pre_scripts, test_scripts = ScriptService.build_collection_script_chain(
                        scripts_data, name="Draft"
                    )

        worker = HttpSendWorker()
        worker.set_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            env_id=env_id,
            request_id=request_id,
            auth_data=auth_data,
            local_overrides={k: v["value"] for k, v in ctx.local_overrides.items()}
            if ctx
            else None,
            pre_scripts=pre_scripts,
            test_scripts=test_scripts,
            declarative_test_script=declarative_test_script,
        )

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_send_finished)
        worker.error.connect(self._on_send_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        if ctx is not None:
            ctx.thread = thread
            ctx.worker = worker
            ctx.is_sending = True
        else:
            self._send_thread = thread
            self._send_worker = worker
        thread.start()

    def run_post_response_script_with_live_response(
        self,
        *,
        editor: RequestEditorWidget,
        panel: ScriptOutputPanel,
        script: str,
        language: str,
        run_btn: Any,
        debug_btn: Any,
    ) -> None:
        """Send the active request first, then run one post-response script inline."""
        _impl_run_post_response(
            self,
            editor=editor,
            panel=panel,
            script=script,
            language=language,
            run_btn=run_btn,
            debug_btn=debug_btn,
        )

    def _on_send_finished(self, data: dict) -> None:
        """Handle a successful HTTP response from the worker thread."""
        _impl_on_send_finished(self, data)

    def _on_send_error(self, message: str) -> None:
        """Handle an error from the HTTP send worker."""
        inline_test = getattr(self, "_inline_test_run", None)
        ctx = self._current_tab_context()
        viewer = ctx.require_response_viewer() if ctx is not None else self.response_widget
        viewer.show_error(message)
        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add error entry to history panel
        editor = ctx.require_editor() if ctx is not None else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
        )
        self._refresh_sidebar()
        if inline_test is not None:
            panel = inline_test.get("panel")
            for btn in (inline_test.get("run_btn"), inline_test.get("debug_btn")):
                if btn is not None:
                    btn.setEnabled(True)
            self._inline_test_run = None
            if panel is not None:
                panel.show_error(f"Live-response send failed: {message}")

    def _cancel_send(self) -> None:
        """Cancel the in-flight HTTP request."""
        inline_test = getattr(self, "_inline_test_run", None)
        if inline_test is not None:
            for btn in (inline_test.get("run_btn"), inline_test.get("debug_btn")):
                if btn is not None:
                    btn.setEnabled(True)
            self._inline_test_run = None
        ctx = self._current_tab_context()
        if ctx is not None:
            ctx.cancel_send()
            if ctx.tab_type not in ("folder", "environments", "local_script"):
                ctx.require_response_viewer().show_error("Request cancelled")
        else:
            if self._send_worker is not None:
                self._send_worker.cancel()
            self.response_widget.show_error("Request cancelled")
            self._cleanup_send_thread()
        self._set_send_button_cancel(False)

    def _set_send_button_cancel(self, is_cancel: bool) -> None:
        """Toggle the Send button between Send and Cancel states."""
        ctx = self._current_tab_context()
        if ctx is not None and ctx.tab_type in ("folder", "environments", "local_script"):
            return
        editor = ctx.require_editor() if ctx is not None else self.request_widget
        btn = editor._send_btn
        if is_cancel:
            btn.setText("Cancel")
            btn.setObjectName("dangerButton")
        else:
            btn.setText("Send")
            btn.setObjectName("primaryButton")
        # Force style recalculation after objectName change
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _cleanup_send_thread(self) -> None:
        """Clean up the background send thread and worker."""
        if self._send_thread is not None:
            if self._send_thread.isRunning():
                self._send_thread.quit()
                self._send_thread.wait(3000)
            self._send_thread.deleteLater()
            self._send_thread = None
        if self._send_worker is not None:
            self._send_worker.deleteLater()
            self._send_worker = None

    # ------------------------------------------------------------------
    # Debug pipeline
    # ------------------------------------------------------------------
    def _clear_debug_breakpoint_listeners(self) -> None:
        """Disconnect live breakpoint sync slots from a previous debug session."""
        conns: list = getattr(self, "_debug_breakpoint_connections", None) or []
        for w, slot in conns:
            with contextlib.suppress(TypeError, RuntimeError):
                w.breakpoints_changed.disconnect(slot)  # type: ignore[union-attr]
        self._debug_breakpoint_connections: list[tuple[Any, Any]] = []

    def _active_script_host(self) -> Any:
        """Request or folder editor for the current tab; hosts script UI.

        For **folder** tabs, :meth:`_current_editor` is still the
        (hidden) :class:`RequestEditorWidget` while the user sees
        :class:`FolderEditorWidget` — script pause highlights must
        target the visible host.
        """
        ctx = self._current_tab_context()
        if ctx is None:
            return self.request_widget
        if ctx.tab_type == "folder" and ctx.folder_editor is not None:
            return ctx.folder_editor
        if ctx.tab_type == "local_script" and ctx.local_script_editor is not None:
            return ctx.local_script_editor
        if ctx.tab_type == "request" and ctx.editor is not None:
            return ctx.editor
        return self.request_widget

    def _resolve_debug_script_host(self) -> Any:
        """Return the widget that started the current inline debug session."""
        pinned = getattr(self, "_debug_script_host", None)
        if pinned is not None:
            return pinned
        return self._active_script_host()

    def _clear_debug_script_host_pin(self) -> None:
        """Drop the inline-debug host pin (see :meth:`_resolve_debug_script_host`)."""
        self._debug_script_host = None

    def _on_debug_paused(self, info: dict) -> None:
        """Handle a debug pause event from the worker thread."""
        _impl_on_debug_paused(self, info)

    def _on_debug_step(self, mode_name: str) -> None:
        """Handle a step request from the debug panel."""
        _impl_on_debug_step(self, mode_name)

    def _on_debug_finished(self, data: dict) -> None:
        """Handle completion of a debug send."""
        _impl_on_debug_finished(self, data)

    def _on_debug_error(self, message: str) -> None:
        """Handle an error during a debug send."""
        _impl_on_debug_error(self, message)

    def _end_debug_ui(self) -> None:
        """Clean up debug UI state after a session ends."""
        _impl_end_debug_ui(self)

    def end_inline_script_debug(self) -> None:
        """Clear inline script debug state when :class:`ScriptDebugWorker` ends."""
        _impl_end_inline_script_debug(self)

    def _current_editor(self) -> RequestEditorWidget:
        """Return the editor for the active tab."""
        ctx = self._current_tab_context()
        if ctx is not None and ctx.editor is not None:
            return ctx.editor
        return self.request_widget
