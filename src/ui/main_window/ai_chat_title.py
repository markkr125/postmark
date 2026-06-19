"""Off-GUI session title generation for :class:`_AiChatControllerMixin`."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, Qt, QThread, Slot

from services.ai.chat.session_service import AiChatSessionService
from ui.main_window.ai_chat_host_protocol import _AiChatHostProtocol
from ui.sidebar.ai.workers.title_worker import AiChatTitleWorker

if TYPE_CHECKING:
    from ui.sidebar import RightSidebar


class _AiChatTitleMixin:
    """Spawn title workers after the first user/assistant exchange."""

    _right_sidebar: RightSidebar
    _ai_title_thread: QThread | None
    _ai_title_worker: AiChatTitleWorker | None
    _title_run_session_id: str | None
    _ai_title_thread_generation: int
    _active_ai_session_id: str | None
    _manual_ai_session_titles: set[str]

    def _maybe_generate_session_title(self, session_id: str) -> None:
        """Generate a title off-GUI after the first user/assistant exchange."""
        messages = AiChatSessionService.get_messages(session_id)
        if len(messages) != 2:
            return

        session = AiChatSessionService.get_session(session_id)
        if session is None:
            return

        entry = self._right_sidebar.ai_chat_panel.current_model_entry()
        if entry is None:
            return
        if self._ai_title_thread is not None and self._ai_title_thread.isRunning():
            return

        self._title_run_session_id = session_id
        worker = AiChatTitleWorker()
        worker.set_run(
            session_id=session_id,
            entry=entry,
            agent_id=session["agent_id"],
        )
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        queued = Qt.ConnectionType.QueuedConnection
        worker.title_ready.connect(self._deliver_ai_title_worker_ready, queued)
        worker.title_ready.connect(thread.quit, queued)
        worker.failed.connect(thread.quit, queued)
        self._ai_title_thread_generation += 1
        title_generation = self._ai_title_thread_generation
        thread.finished.connect(
            lambda t=thread, w=worker, g=title_generation: self._release_ai_title_thread(t, w, g),
            queued,
        )

        self._ai_title_thread = thread
        self._ai_title_worker = worker
        thread.start()

    @Slot(str)
    def _deliver_ai_title_worker_ready(self, title: str) -> None:
        """Marshal generated title onto the GUI thread."""
        self_q = cast(QObject, self)
        if QThread.currentThread() != self_q.thread():
            self_q._ai_title_ready_requested.emit(title)  # type: ignore[attr-defined]
            return
        self._apply_ai_title_worker_ready(title)

    @Slot(str)
    def _apply_ai_title_worker_ready(self, title: str) -> None:
        """Apply a generated session title on the GUI thread."""
        session_id = self._title_run_session_id
        if session_id is None:
            return
        self._on_ai_title_ready(session_id, title)

    def _on_ai_title_ready(self, session_id: str, title: str) -> None:
        """Apply a generated title to the session row."""
        if session_id != self._active_ai_session_id:
            return
        if session_id in self._manual_ai_session_titles:
            return
        AiChatSessionService.rename_session(session_id, title)
        cast(_AiChatHostProtocol, self)._sync_ai_session_title()

    def _release_ai_title_thread(
        self,
        thread: QThread,
        worker: AiChatTitleWorker,
        generation: int,
    ) -> None:
        """Release one title worker/thread pair after ``finished``."""
        if generation != self._ai_title_thread_generation:
            return
        if self._ai_title_thread is not thread:
            return
        if self._ai_title_worker is worker:
            worker.deleteLater()
        thread.wait(100)
        thread.deleteLater()
        self._ai_title_thread = None
        self._ai_title_worker = None
        self._title_run_session_id = None

    def _cleanup_ai_title_thread(self) -> None:
        """Stop the title worker thread during window teardown."""
        thread = self._ai_title_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(5000)
        self._ai_title_thread = None
        self._ai_title_worker = None


__all__ = ["_AiChatTitleMixin"]
