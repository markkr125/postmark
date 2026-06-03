"""Background worker for provider test + model listing."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:
    from ui.dialogs.settings.ai_page import AiPageController

from services.ai.ai_logging import log as ai_log
from services.ai.ops.connection import setup_provider
from services.ai.sdk_env import CONNECTION_TEST_TIMEOUT_SEC, MODEL_LIST_TIMEOUT_SEC
from services.ai.provider_catalog import ModelSpec


class AiProviderSetupWorker(QObject):
    """List models (HTTP) or API ping + catalog, within the connection timeout."""

    finished = Signal(bool, str, object)
    log_line = Signal(str)

    def __init__(self) -> None:
        """Create a worker; call :meth:`set_params` before starting."""
        super().__init__()
        self._provider_key = ""
        self._base_url = ""
        self._api_version = ""
        self._auth_kind = "none"
        self._auth_ref = ""
        self._entry_id = "probe"
        self._ollama_default_context = 0

    def set_params(
        self,
        *,
        provider_key: str,
        base_url: str,
        api_version: str,
        auth_kind: str,
        auth_ref: str,
        entry_id: str,
        ollama_default_context: int = 0,
    ) -> None:
        """Configure provider credentials."""
        self._provider_key = provider_key
        self._base_url = base_url
        self._api_version = api_version
        self._auth_kind = auth_kind
        self._auth_ref = auth_ref
        self._entry_id = entry_id
        self._ollama_default_context = ollama_default_context

    def _emit_log(self, line: str) -> None:
        """Stderr from the worker thread; UI via ``log_line`` (queued to GUI)."""
        ai_log(line)
        self.log_line.emit(line)

    @Slot()
    def run(self) -> None:
        """Validate provider and load models. Never raises."""
        ok, detail, models = setup_provider(
            provider_key=self._provider_key,
            base_url=self._base_url,
            api_version=self._api_version,
            auth_kind=self._auth_kind,
            auth_ref=self._auth_ref,
            entry_id=self._entry_id,
            timeout_sec=CONNECTION_TEST_TIMEOUT_SEC,
            bulk=True,
            ollama_default_context=self._ollama_default_context,
        )
        count = len(models) if ok else 0
        if ok:
            self._emit_log(f"Found {count} model(s).")
            summary = detail if "Found" in detail else f"Connected — {count} model(s) found"
        else:
            summary = detail
        thread = QThread.currentThread()
        if thread.isInterruptionRequested():
            return
        self.finished.emit(ok, summary, models if ok else ())


def release_provider_setup_thread(
    thread: QThread | None,
    worker: AiProviderSetupWorker | None,
    *,
    set_test_running: Callable[[bool], None],
) -> tuple[None, None]:
    """Drop worker/thread refs and schedule Qt deletion (thread must be stopped)."""
    set_test_running(False)
    if worker is not None:
        worker.deleteLater()
    if thread is not None:
        thread.deleteLater()
    return None, None


def cancel_provider_setup_thread(
    thread: QThread | None,
    worker: AiProviderSetupWorker | None,
    *,
    disconnect_worker: Callable[[AiProviderSetupWorker | None], None],
    set_test_running: Callable[[bool], None],
) -> tuple[None, None]:
    """Stop an in-flight test; blocks until the worker thread has exited."""
    if thread is None:
        return None, None
    disconnect_worker(worker)
    if thread.isRunning():
        thread.requestInterruption()
        thread.quit()
        wait_ms = int(max(CONNECTION_TEST_TIMEOUT_SEC, MODEL_LIST_TIMEOUT_SEC) + 5) * 1000
        if not thread.wait(wait_ms):
            thread.terminate()
            thread.wait(3000)
    return release_provider_setup_thread(thread, worker, set_test_running=set_test_running)


def disconnect_provider_setup_worker(
    worker: AiProviderSetupWorker | None,
    *,
    log_slot: Callable[[str], None],
    finished_slot: Callable[[bool, str, object], None],
) -> None:
    """Disconnect dialog slots from *worker* before thread teardown."""
    if worker is None:
        return
    with contextlib.suppress(RuntimeError, TypeError):
        worker.log_line.disconnect(log_slot)
        worker.finished.disconnect(finished_slot)


class AiRefreshUiBridge(QObject):
    """Deliver worker ``finished`` on the GUI thread (controller is not a QObject)."""

    def __init__(self, controller: AiPageController, parent: QObject) -> None:
        """Attach to *parent* so slots run on the main thread."""
        super().__init__(parent)
        self._controller = controller

    @Slot(bool, str, object)
    def deliver_finished(self, ok: bool, detail: str, models_obj: object) -> None:
        """Apply refresh results; never call from the worker thread."""
        self._controller._apply_refresh_result(ok, detail, models_obj)


__all__ = [
    "AiProviderSetupWorker",
    "AiRefreshUiBridge",
    "ModelSpec",
    "cancel_provider_setup_thread",
    "disconnect_provider_setup_worker",
    "release_provider_setup_thread",
]
