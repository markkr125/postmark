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

logger = logging.getLogger(__name__)


def _merge_debug_hover_values(pause_info: dict) -> dict[str, Any]:
    """Merge values for ``set_debug_locals`` hover. Later sources override on name clash.

    Precedence: ``globals`` snapshot, then ``pm`` snapshot, then CDP ``locals``,
    then env/workspace changes (last wins on name clash for the latter two).
    """
    merged: dict[str, Any] = {}
    lv = pause_info.get("local_vars") or {}
    if (
        "globals" in lv
        and "pm" in lv
        and isinstance(lv.get("pm"), dict)
        and isinstance(lv.get("globals"), dict)
    ):
        merged.update(lv.get("globals", {}))
        merged.update(lv.get("pm", {}))
    else:
        flat = {k: v for k, v in lv.items() if k not in {"locals", "scopes"}}
        merged.update(flat)
    locals_ = lv.get("locals")
    if isinstance(locals_, dict):
        merged.update(locals_)
    merged.update(pause_info.get("env_changes") or {})
    merged.update(pause_info.get("global_changes") or {})
    return merged


def _debug_hover_root_objects(pause_info: dict) -> dict[str, Any]:
    """Whole-object snapshots for hover when the flat merge omits the root name.

    When ``globals`` and ``pm`` dicts are present, :func:`_merge_debug_hover_values`
    flattens ``pm`` keys, so the identifier ``pm`` is not in the merged map.
    """
    roots: dict[str, Any] = {}
    lv = pause_info.get("local_vars") or {}
    pm = lv.get("pm")
    if isinstance(pm, dict):
        roots["pm"] = pm
    gl = lv.get("globals")
    if isinstance(gl, dict):
        con = gl.get("console")
        if isinstance(con, dict):
            roots["console"] = con
    return roots


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
        if ctx is not None and ctx.tab_type in ("folder", "environments"):
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
        if _scripts_enabled() and inline_test is None:
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
        for btn in (run_btn, debug_btn):
            if btn is not None:
                btn.setEnabled(False)
        self._inline_test_run = {
            "editor": editor,
            "panel": panel,
            "script": script,
            "language": language,
            "run_btn": run_btn,
            "debug_btn": debug_btn,
        }
        panel.show_error("Sending request to fetch live response…")
        self._on_send_request()

    def _on_send_finished(self, data: dict) -> None:
        """Handle a successful HTTP response from the worker thread."""
        inline_test = getattr(self, "_inline_test_run", None)
        ctx = self._current_tab_context()
        viewer = ctx.require_response_viewer() if ctx is not None else self.response_widget

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

            console_panel: ConsolePanel | None = getattr(self, "_console_panel", None)
            if console_panel is not None:
                for log_entry in console_logs:
                    message = log_entry.get("message", "")
                    level = log_entry.get("level", "log")
                    if level == "error":
                        console_panel.append_error(f"[Script] {message}")
                    else:
                        console_panel.append_message(f"[Script] {message}")

        # Apply variable changes to local overrides
        var_changes = data.get("variable_changes", {})
        if ctx and ctx.tab_type not in ("folder", "environments") and var_changes:
            _ = ctx.require_editor()
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
        editor = ctx.require_editor() if ctx is not None else self.request_widget
        self._history_panel.add_entry(
            editor._method_combo.currentText(),
            editor._url_input.text(),
            data.get("status_code"),
            data.get("elapsed_ms", 0),
        )
        self._refresh_sidebar()

        if inline_test is not None:
            from ui.request.request_editor.scripts.script_run_worker import build_inline_context

            panel = inline_test.get("panel")
            script = str(inline_test.get("script", ""))
            language = str(inline_test.get("language", "javascript"))
            run_btn = inline_test.get("run_btn")
            debug_btn = inline_test.get("debug_btn")
            self._inline_test_run = None
            if script and panel is not None and hasattr(panel, "run_script"):
                response_payload = {
                    "code": int(data.get("status_code", 0) or 0),
                    "status": f"{data.get('status_code', '')} {data.get('status_text', '')}".strip(),
                    "headers": data.get("headers", []),
                    "body": str(data.get("body", "")),
                    "responseTime": float(data.get("elapsed_ms", 0.0) or 0.0),
                    "responseSize": int(data.get("size_bytes", 0) or 0),
                }
                context = build_inline_context(script_type="test", response_data=response_payload)
                panel.run_script(
                    script=script,
                    language=language,
                    context=context,
                    run_btn=run_btn,
                    debug_btn=debug_btn,
                )
            else:
                for btn in (run_btn, debug_btn):
                    if btn is not None:
                        btn.setEnabled(True)

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
            if ctx.tab_type not in ("folder", "environments"):
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
        if ctx is not None and ctx.tab_type in ("folder", "environments"):
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
        if ctx.tab_type == "request" and ctx.editor is not None:
            return ctx.editor
        return self.request_widget

    def _on_debug_paused(self, info: dict) -> None:
        """Handle a debug pause event from the worker thread."""
        from services.scripting.debug import DebugPauseInfo

        editor: Any = self._active_script_host()
        pause_info: DebugPauseInfo = info  # type: ignore[assignment]

        script_type = pause_info.get("script_type", "pre_request")
        line = pause_info.get("line", 0)

        # Highlight current line in the appropriate editor
        target = (
            editor._pre_request_edit if script_type == "pre_request" else editor._test_script_edit
        )
        other = (
            editor._test_script_edit if script_type == "pre_request" else editor._pre_request_edit
        )
        target.set_debug_line(line)
        merged = _merge_debug_hover_values(dict(pause_info))
        roots = _debug_hover_root_objects(dict(pause_info))
        target.set_debug_locals(merged, root_values=roots)
        other.set_debug_locals({})

        # Switch to the Scripts tab, then the correct sub-tab
        scripts_idx = editor._tabs.indexOf(editor._scripts_tab)
        if scripts_idx >= 0:
            editor._tabs.setCurrentIndex(scripts_idx)
        editor._scripts_sub_tabs.setCurrentIndex(
            0 if script_type == "pre_request" else 1,
        )

        pre = getattr(editor, "_pre_output_panel", None)
        testp = getattr(editor, "_test_output_panel", None)
        if pre is not None and testp is not None:
            if script_type == "pre_request":
                pre.show_debug_controls(pause_info)
                testp.hide_debug_controls()
            else:
                testp.show_debug_controls(pause_info)
                pre.hide_debug_controls()

        controls_map = getattr(editor, "_debug_controls", None)
        if isinstance(controls_map, dict):
            active_key = "pre_request" if script_type == "pre_request" else "test"
            for key, ctrl in controls_map.items():
                if key == active_key:
                    ctrl.update_pause(pause_info)
                    ctrl.show()
                    pbar = ctrl.parentWidget()
                    if pbar is not None:
                        pbar.show()
                else:
                    ctrl.clear_session()
                    ctrl.hide()
                    pbar = ctrl.parentWidget()
                    if pbar is not None:
                        pbar.hide()

        sched = getattr(editor, "_schedule_refresh_script_split_full_width_line", None)
        if callable(sched):
            sched()

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
        host: Any = self._active_script_host()
        host._pre_request_edit.set_debug_line(None)
        host._test_script_edit.set_debug_line(None)
        host._pre_request_edit.set_debug_locals({})
        host._test_script_edit.set_debug_locals({})

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
        self._clear_debug_breakpoint_listeners()
        host: Any = self._active_script_host()
        host._pre_request_edit.set_debug_line(None)
        host._test_script_edit.set_debug_line(None)
        host._pre_request_edit.set_debug_locals({})
        host._test_script_edit.set_debug_locals({})
        for name in ("_pre_output_panel", "_test_output_panel"):
            p = getattr(host, name, None)
            if p is not None and hasattr(p, "hide_debug_controls"):
                p.hide_debug_controls()
        controls_map = getattr(host, "_debug_controls", None)
        if isinstance(controls_map, dict):
            for ctrl in controls_map.values():
                ctrl.clear_session()
                ctrl.hide()
                pbar = ctrl.parentWidget()
                if pbar is not None:
                    pbar.hide()
        sched = getattr(host, "_schedule_refresh_script_split_full_width_line", None)
        if callable(sched):
            sched()

    def end_inline_script_debug(self) -> None:
        """Clear inline script debug state when :class:`ScriptDebugWorker` ends."""
        self._debug_protocol = None
        self._end_debug_ui()

    def _current_editor(self) -> RequestEditorWidget:
        """Return the editor for the active tab."""
        ctx = self._current_tab_context()
        if ctx is not None and ctx.editor is not None:
            return ctx.editor
        return self.request_widget
