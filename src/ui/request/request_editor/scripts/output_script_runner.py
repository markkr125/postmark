"""Background script execution for :class:`ScriptOutputPanel`."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QThread
from shiboken6 import Shiboken

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPushButton

    from services.scripting import ScriptInput
    from services.scripting.debug import DebugProtocol

# Matches the send-pipeline QThread wait budget in tab_manager.
_THREAD_WAIT_MS = 3000


def run_script_iterations(
    panel: Any,
    *,
    script: str,
    language: str,
    context: ScriptInput,
    iteration_data: list[dict[str, Any]],
    iteration_count: int,
    run_btn: QPushButton | None = None,
    debug_btn: QPushButton | None = None,
) -> None:
    """Launch a background thread to run *script* once per data row."""
    from ui.request.request_editor.scripts.script_run_worker import ScriptRunWorker

    if panel._worker_thread is not None and panel._worker_thread.isRunning():
        return

    panel._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
    if panel._data_runner is not None:
        panel._busy_buttons.append(panel._data_runner._run_btn)
    for b in panel._busy_buttons:
        b.setEnabled(False)

    total = max(iteration_count, len(iteration_data))
    if panel._iterations_tab is not None:
        panel._iterations_tab.set_source_data(iteration_data)
        panel._iterations_tab.begin_run(iteration_count=total)
        tabs = getattr(panel, "_script_output_tabs", None)
        if tabs is not None and panel._iterations_tab is not None:
            tabs.setCurrentWidget(panel._iterations_tab)

    panel._iteration_run_active = True
    info = context.get("info", {})
    if isinstance(info, dict):
        req_name = info.get("requestName")
        if req_name:
            panel._export_suite_name = str(req_name)

    thread = QThread()
    worker = ScriptRunWorker()
    worker.set_params(script=script, language=language, context=context)
    worker.set_iteration_data(iteration_data, count=iteration_count)
    worker.moveToThread(thread)

    worker.iteration_finished.connect(panel._on_iteration_finished)
    worker.finished.connect(panel._on_iterations_worker_finished)
    worker.error.connect(panel._on_worker_error)
    thread.finished.connect(panel._on_thread_finished)
    thread.started.connect(worker.run)

    panel._worker_thread = thread
    panel._current_worker = worker
    thread.start()


def run_script(
    panel: Any,
    *,
    script: str,
    language: str,
    context: ScriptInput,
    run_btn: QPushButton | None = None,
    debug_btn: QPushButton | None = None,
    test_name_filter: str | None = None,
) -> None:
    """Launch a background thread to execute *script* and show results."""
    from ui.request.request_editor.scripts.script_run_worker import ScriptRunWorker

    if panel._worker_thread is not None and panel._worker_thread.isRunning():
        return

    panel.clear_inline_log_annotations()
    panel._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
    for b in panel._busy_buttons:
        b.setEnabled(False)

    panel._pending_test_filter = test_name_filter
    info = context.get("info", {})
    if isinstance(info, dict):
        req_name = info.get("requestName")
        if req_name:
            panel._export_suite_name = str(req_name)

    thread = QThread()
    worker = ScriptRunWorker()
    worker.set_params(
        script=script,
        language=language,
        context=context,
        test_name_filter=test_name_filter,
    )
    worker.moveToThread(thread)

    worker.finished.connect(panel._on_worker_finished)
    worker.error.connect(panel._on_worker_error)
    thread.finished.connect(panel._on_thread_finished)
    thread.started.connect(worker.run)

    panel._worker_thread = thread
    panel._current_worker = worker
    thread.start()


def run_script_chain(
    panel: Any,
    *,
    chain: list[Any],
    script_type: str,
    context: ScriptInput,
    run_btn: QPushButton | None = None,
    debug_btn: QPushButton | None = None,
) -> None:
    """Run an inherited script chain inline."""
    from ui.request.request_editor.scripts.script_run_worker import ScriptChainRunWorker

    if panel._worker_thread is not None and panel._worker_thread.isRunning():
        return

    panel.clear_inline_log_annotations()
    panel._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
    for b in panel._busy_buttons:
        b.setEnabled(False)

    thread = QThread()
    worker = ScriptChainRunWorker()
    worker.set_params(chain=chain, script_type=script_type, context=context)
    worker.moveToThread(thread)

    worker.finished.connect(panel._on_worker_finished)
    worker.error.connect(panel._on_worker_error)
    thread.finished.connect(panel._on_thread_finished)
    thread.started.connect(worker.run)

    panel._worker_thread = thread
    panel._current_worker = worker
    thread.start()


def run_script_debug(
    panel: Any,
    *,
    script: str,
    language: str,
    context: ScriptInput,
    protocol: DebugProtocol,
    script_type: str,
    run_btn: QPushButton | None = None,
    debug_btn: QPushButton | None = None,
) -> None:
    """Run *script* with :class:`DebugProtocol` and show output on completion."""
    from ui.request.request_editor.scripts.output_debug_bar import set_debug_protocol
    from ui.request.request_editor.scripts.script_run_worker import ScriptDebugWorker

    if panel._worker_thread is not None and panel._worker_thread.isRunning():
        return

    panel.clear_inline_log_annotations()
    panel._busy_buttons = [b for b in (run_btn, debug_btn) if b is not None]
    for b in panel._busy_buttons:
        b.setEnabled(False)
    panel._is_inline_debug = True
    set_debug_protocol(panel, protocol)

    thread = QThread()
    worker = ScriptDebugWorker()
    worker.set_params(
        script=script,
        language=language,
        context=context,
        protocol=protocol,
        script_type=script_type,
    )
    worker.moveToThread(thread)

    main = panel.window()
    on_pause = getattr(main, "_on_debug_paused", None)
    if callable(on_pause):
        worker.debug_paused.connect(on_pause)

    worker.finished.connect(panel._on_debug_worker_finished)
    worker.error.connect(panel._on_debug_worker_error)
    thread.finished.connect(panel._on_thread_finished)
    thread.started.connect(worker.run)

    panel._worker_thread = thread
    panel._current_worker = worker
    thread.start()


def _reenable_busy_buttons(panel: Any) -> None:
    """Re-enable run/debug buttons if the thread-finished hook did not run."""
    if not Shiboken.isValid(panel):
        return
    for btn in list(getattr(panel, "_busy_buttons", []) or []):
        if Shiboken.isValid(btn):
            btn.setEnabled(True)
    panel._busy_buttons = []


def on_debug_worker_finished(panel: Any, output: dict, elapsed_ms: float) -> None:
    """Handle successful inline debug run."""
    try:
        if Shiboken.isValid(panel):
            panel.show_results(output, elapsed_ms)
    finally:
        with contextlib.suppress(RuntimeError):
            end_inline_debug_if_current(panel)
        stop_worker_thread(panel)
        _reenable_busy_buttons(panel)


def on_debug_worker_error(panel: Any, msg: str) -> None:
    """Handle inline debug run error."""
    try:
        if Shiboken.isValid(panel):
            panel.show_error(msg)
    finally:
        with contextlib.suppress(RuntimeError):
            end_inline_debug_if_current(panel)
        stop_worker_thread(panel)
        _reenable_busy_buttons(panel)


def end_inline_debug_if_current(panel: Any) -> None:
    """Clear MainWindow inline debug state when this panel owned the session."""
    if not getattr(panel, "_is_inline_debug", False):
        return
    panel._is_inline_debug = False
    if not Shiboken.isValid(panel):
        return
    main = panel.window()
    if main is None or not Shiboken.isValid(main):
        return
    end = getattr(main, "end_inline_script_debug", None)
    if callable(end):
        end()


def on_worker_finished(panel: Any, output: dict, elapsed_ms: float) -> None:
    """Handle successful script execution on the main thread."""
    if panel._iteration_run_active:
        return
    panel.show_results(output, elapsed_ms)
    stop_worker_thread(panel)


def on_worker_error(panel: Any, msg: str) -> None:
    """Handle script execution error on the main thread."""
    panel._iteration_run_active = False
    panel.show_error(msg)
    stop_worker_thread(panel)


def stop_worker_thread(panel: Any) -> None:
    """Quit and join the worker QThread, if any."""
    thread = panel._worker_thread
    if thread is None:
        return
    thread.quit()
    thread.wait(_THREAD_WAIT_MS)


def cleanup_runner(panel: Any) -> None:
    """Tear down any running script/debug worker before the app closes."""
    worker = panel._current_worker
    if worker is not None:
        protocol = getattr(worker, "_protocol", None)
        if protocol is not None:
            with contextlib.suppress(Exception):
                protocol.stop()
    stop_worker_thread(panel)


def on_thread_finished(panel: Any) -> None:
    """Clean up worker and thread after completion."""
    if not Shiboken.isValid(panel):
        return
    if panel._current_worker:
        panel._current_worker.deleteLater()
        panel._current_worker = None
    if panel._worker_thread:
        panel._worker_thread.deleteLater()
        panel._worker_thread = None
    _reenable_busy_buttons(panel)
