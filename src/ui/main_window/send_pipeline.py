"""HTTP send pipeline mixin for the main window.

Provides ``_SendPipelineMixin`` with background HTTP request execution,
cancel, debug mode, and cleanup methods.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, QThread

if TYPE_CHECKING:
    from services.scripting.debug import DebugProtocol
    from ui.environments.environment_selector import EnvironmentSelector
    from ui.panels.history_panel import HistoryPanel
    from ui.request.http_worker import HttpSendWorker
    from ui.request.navigation.request_tab_bar import RequestTabBar
    from ui.request.navigation.tab_manager import TabContext
    from ui.request.request_editor import RequestEditorWidget
    from ui.request.response_viewer import ResponseViewerWidget
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)


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
    ``response_widget``, ``_env_selector``, and ``_history_panel``.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _send_thread: QThread | None
    _send_worker: HttpSendWorker | None
    _tab_bar: RequestTabBar
    _env_selector: EnvironmentSelector
    _history_panel: HistoryPanel
    _right_sidebar: RightSidebar
    request_widget: RequestEditorWidget
    response_widget: ResponseViewerWidget
    _debug_protocol: DebugProtocol | None

    def _current_tab_context(self) -> TabContext | None: ...

    if TYPE_CHECKING:

        def _refresh_sidebar(self, ctx: TabContext | None = None) -> None: ...

    def _on_send_request(self) -> None:
        """Send the current request on a background thread."""
        ctx: TabContext | None = self._current_tab_context()

        # Folder tabs cannot send requests
        if ctx is not None and ctx.tab_type == "folder":
            return

        # If already sending, treat as cancel
        if ctx is not None and ctx.is_sending:
            self._cancel_send()
            return
        if self._send_thread is not None and self._send_thread.isRunning():
            self._cancel_send()
            return

        # 1. Gather request data from the current editor
        editor = ctx.editor if ctx else self.request_widget
        viewer = ctx.response_viewer if ctx else self.response_widget

        method = editor._method_combo.currentText()
        url = editor._url_input.text().strip()
        if not url:
            viewer.show_error("URL is empty")
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

        pre_scripts = None
        test_scripts = None
        if _scripts_enabled():
            if request_id:
                pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
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

    def _on_send_finished(self, data: dict) -> None:
        """Handle a successful HTTP response from the worker thread."""
        ctx = self._current_tab_context()
        viewer = ctx.response_viewer if ctx else self.response_widget

        # Remember if the user was on the Pre-request tab before reload.
        was_on_pre_request = (
            hasattr(viewer, "_pre_tab_index")
            and viewer._tabs.currentIndex() == viewer._pre_tab_index
            and viewer._tabs.isTabVisible(viewer._pre_tab_index)
        )

        viewer.load_response(data)

        # Pass test results to response viewer (if present)
        test_results = data.get("test_results", [])
        console_logs = data.get("console_logs", [])
        if test_results:
            viewer.load_test_results(test_results)

        # Populate the Pre-request tab when scripts ran.
        if data.get("has_pre_request_scripts"):
            viewer.load_pre_request_data(
                console_logs=data.get("pre_request_console_logs", []),
                variable_changes=data.get("pre_request_variable_changes", {}),
                errors=data.get("pre_request_errors", []),
            )
            # If the user was already viewing the Pre-request tab, stay.
            if was_on_pre_request:
                viewer._tabs.setCurrentIndex(viewer._pre_tab_index)

        # Route console logs to the console panel
        if console_logs:
            from ui.panels.console_panel import ConsolePanel

            panel: ConsolePanel | None = getattr(self, "_console_panel", None)
            if panel is not None:
                for log_entry in console_logs:
                    message = log_entry.get("message", "")
                    level = log_entry.get("level", "log")
                    if level == "error":
                        panel.append_error(f"[Script] {message}")
                    else:
                        panel.append_message(f"[Script] {message}")

        # Apply variable changes to local overrides
        var_changes = data.get("variable_changes", {})
        if ctx and var_changes:
            for key, value in var_changes.items():
                ctx.local_overrides[key] = {
                    "value": str(value),
                    "original_source": "script",
                    "original_source_id": 0,
                }

        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add to history panel
        editor = ctx.editor if ctx else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
            data.get("status_code"),
            data.get("elapsed_ms", 0),
        )
        self._refresh_sidebar()

    def _on_send_error(self, message: str) -> None:
        """Handle an error from the HTTP send worker."""
        ctx = self._current_tab_context()
        viewer = ctx.response_viewer if ctx else self.response_widget
        viewer.show_error(message)
        self._set_send_button_cancel(False)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=False)
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()
        # Add error entry to history panel
        editor = ctx.editor if ctx else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
        )
        self._refresh_sidebar()

    def _cancel_send(self) -> None:
        """Cancel the in-flight HTTP request."""
        ctx = self._current_tab_context()
        if ctx is not None:
            ctx.cancel_send()
            ctx.response_viewer.show_error("Request cancelled")
        else:
            if self._send_worker is not None:
                self._send_worker.cancel()
            self.response_widget.show_error("Request cancelled")
            self._cleanup_send_thread()
        self._set_send_button_cancel(False)

    def _set_send_button_cancel(self, is_cancel: bool) -> None:
        """Toggle the Send button between Send and Cancel states."""
        ctx = self._current_tab_context()
        if ctx is not None and ctx.tab_type == "folder":
            return
        editor = ctx.editor if ctx else self.request_widget
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
    def _on_debug_request(self) -> None:
        """Send the current request with debug mode enabled."""
        from services.scripting.debug import DebugProtocol

        ctx: TabContext | None = self._current_tab_context()

        if ctx is not None and ctx.tab_type == "folder":
            return

        if ctx is not None and ctx.is_sending:
            self._cancel_send()
            return

        editor = ctx.editor if ctx else self.request_widget
        viewer = ctx.response_viewer if ctx else self.response_widget

        method = editor._method_combo.currentText()
        url = editor._url_input.text().strip()
        if not url:
            viewer.show_error("URL is empty")
            return

        headers = editor.get_headers_text()
        body = editor.get_request_data().get("body") or None

        from services.collection_service import CollectionService

        auth_data = editor._get_auth_data()
        if ctx and ctx.request_id and auth_data is None:
            inherited = CollectionService.get_request_inherited_auth(ctx.request_id)
            if inherited:
                auth_data = inherited

        env_id = self._env_selector.current_environment_id()
        request_id = ctx.request_id if ctx else None

        if ctx is not None:
            ctx.cleanup_thread()
        else:
            self._cleanup_send_thread()

        # Build script chains
        from services.script_service import ScriptService
        from ui.request.http_worker import HttpSendWorker

        pre_scripts = None
        test_scripts = None
        if _scripts_enabled():
            if request_id:
                pre_scripts, test_scripts = ScriptService.build_script_chain(request_id)
            else:
                scripts_data = editor.get_request_data().get("scripts")
                if scripts_data:
                    pre_scripts, test_scripts = ScriptService.build_collection_script_chain(
                        scripts_data, name="Draft"
                    )

        if not pre_scripts and not test_scripts:
            viewer.show_error("No scripts to debug")
            return

        # Collect breakpoints from script editors
        pre_bp = editor._pre_request_edit.breakpoints
        test_bp = editor._test_script_edit.breakpoints

        # Create debug protocol
        protocol = DebugProtocol()
        protocol.set_breakpoints(pre_bp | test_bp)
        self._debug_protocol = protocol

        # Enable breakpoint gutter debug lines in editors
        editor._pre_request_edit.set_breakpoint_gutter_visible(True)
        editor._test_script_edit.set_breakpoint_gutter_visible(True)

        viewer.show_loading()
        self._set_send_button_cancel(True)
        if ctx is not None:
            idx = self._tab_bar.currentIndex()
            self._tab_bar.update_tab(idx, is_sending=True)

        # Show debug sidebar
        self._right_sidebar.show_debug_panel()

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
        )
        worker.set_debug_mode(protocol)

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_debug_finished)
        worker.error.connect(self._on_debug_error)
        worker.debug_paused.connect(self._on_debug_paused)
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

    def _on_debug_paused(self, info: dict) -> None:
        """Handle a debug pause event from the worker thread."""
        from services.scripting.debug import DebugPauseInfo

        editor = self._current_editor()
        pause_info: DebugPauseInfo = info  # type: ignore[assignment]

        script_type = pause_info.get("script_type", "pre_request")
        line = pause_info.get("line", 0)

        # Highlight current line in the appropriate editor
        target = (
            editor._pre_request_edit if script_type == "pre_request" else editor._test_script_edit
        )
        target.set_debug_line(line)

        # Switch to the Scripts tab so the user sees the paused line
        scripts_idx = editor._tabs.indexOf(editor._scripts_tab)
        if scripts_idx >= 0:
            editor._tabs.setCurrentIndex(scripts_idx)

        self._right_sidebar.debug_panel.update_pause(pause_info)

    def _on_debug_step(self, mode_name: str) -> None:
        """Handle a step request from the debug panel."""
        if self._debug_protocol is None:
            return
        from services.scripting.debug import StepMode

        mode_map = {
            "continue": StepMode.CONTINUE,
            "step_over": StepMode.STEP_OVER,
            "step_into": StepMode.STEP_INTO,
            "step_out": StepMode.STEP_OUT,
            "stop": StepMode.STOP,
        }
        mode = mode_map.get(mode_name, StepMode.CONTINUE)

        # Clear debug line highlight before resuming
        editor = self._current_editor()
        editor._pre_request_edit.set_debug_line(None)
        editor._test_script_edit.set_debug_line(None)

        if mode == StepMode.STOP:
            self._debug_protocol.stop()
        else:
            self._debug_protocol.resume(mode)

    def _on_debug_finished(self, data: dict) -> None:
        """Handle completion of a debug send."""
        self._debug_protocol = None
        self._on_send_finished(data)
        self._end_debug_ui()

    def _on_debug_error(self, message: str) -> None:
        """Handle an error during a debug send."""
        self._debug_protocol = None
        self._on_send_error(message)
        self._end_debug_ui()

    def _end_debug_ui(self) -> None:
        """Clean up debug UI state after a session ends."""
        editor = self._current_editor()
        editor._pre_request_edit.set_debug_line(None)
        editor._test_script_edit.set_debug_line(None)
        self._right_sidebar.debug_panel.clear_session()

    def _current_editor(self) -> RequestEditorWidget:
        """Return the editor for the active tab."""
        ctx = self._current_tab_context()
        return ctx.editor if ctx else self.request_widget
