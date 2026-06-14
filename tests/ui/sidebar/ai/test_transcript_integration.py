"""Integration tests for virtualized transcript loading against real SQLite data."""

from __future__ import annotations

import uuid
from typing import Any, cast
from unittest.mock import MagicMock
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.chat.session_service import AiChatSessionService
from services.ai.chat.transcript_window import INITIAL_TAIL_TURNS
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _seed_long_session(turns: int) -> str:
    """Persist a long alternating user/assistant session."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Long", model_id=None, mode="agent")
    for index in range(turns):
        append_message(session_id=session_id, role="user", content=f"user {index}")
        append_message(
            session_id=session_id,
            role="assistant",
            content=f"assistant {index}\n```python\nprint({index})\n```",
        )
    return session_id


class _Host(_AiChatControllerMixin):
    """Controller host wired to a panel."""

    def __init__(self, panel: AiChatPanel) -> None:
        """Attach panel."""
        from types import SimpleNamespace

        from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader

        self._right_sidebar = cast(
            Any,
            SimpleNamespace(
                ai_chat_panel=panel,
                set_ai_session_title=lambda _title: None,
                set_ai_session_title_rename_enabled=lambda _enabled: None,
            ),
        )
        self._active_ai_session_id = None
        self._session_load_generation = 0
        from PySide6.QtWidgets import QWidget

        self._session_loader = AiChatSessionLoader(QWidget())


def _bubble_count(panel: AiChatPanel) -> int:
    """Return rendered bubble widgets."""
    return len(panel.findChildren(ChatMessageBubble))


def test_real_tail_load_bounds_widgets(qapp: QApplication, qtbot) -> None:
    """Opening a long session materializes only the tail page from SQLite."""
    session_id = _seed_long_session(40)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)

    host = _Host(panel)
    host._session_load_generation = 1
    host._on_session_load_finished(1, ("tail", tail))
    panel.flush_transcript_load()
    qtbot.wait(50)

    assert _bubble_count(panel) == len(tail["page"]["messages"])
    assert _bubble_count(panel) <= INITIAL_TAIL_TURNS * 2 + 2
    assert _bubble_count(panel) < 80


def test_bottom_pin_does_not_chain_load_entire_history(qapp: QApplication, qtbot) -> None:
    """Pinned-to-bottom tail load must not prefetch every older page."""
    session_id = _seed_long_session(40)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None
    assert tail["page"]["has_older"]

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)

    callback = MagicMock()
    panel.set_window_load_callback(callback)

    host = _Host(panel)
    host._session_load_generation = 1
    host._on_session_load_finished(1, ("tail", tail))
    panel.flush_transcript_load()
    qtbot.wait(50)
    panel._finish_transcript_bottom_scroll()
    qapp.processEvents()

    for _ in range(5):
        panel._run_virtual_transcript_pass()
        qapp.processEvents()

    callback.assert_not_called()
    assert _bubble_count(panel) <= INITIAL_TAIL_TURNS * 2 + 2


def test_scroll_near_top_prefetches_older_page(qapp: QApplication, qtbot) -> None:
    """Scrolling the first bubble into the top margin requests one older page."""
    session_id = _seed_long_session(40)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)

    callback = MagicMock()
    panel.set_window_load_callback(callback)

    host = _Host(panel)
    host._session_load_generation = 1
    host._on_session_load_finished(1, ("tail", tail))
    panel.flush_transcript_load()
    qtbot.wait(50)

    first = panel._first_loaded_bubble()
    assert first is not None
    first_y = first.mapTo(panel._messages, QPoint(0, 0)).y()
    panel._scroll.verticalScrollBar().setValue(max(0, first_y - 40))
    qapp.processEvents()
    panel._scroll_lock_enabled = False
    panel._run_virtual_transcript_pass()

    callback.assert_called_once()
    assert callback.call_args.args[0] == "older"


def test_scrollbar_drag_to_top_prefetches_older_page(qapp: QApplication, qtbot) -> None:
    """Jumping the scrollbar to the top and releasing requests one older page."""
    session_id = _seed_long_session(40)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)

    callback = MagicMock()
    panel.set_window_load_callback(callback)

    host = _Host(panel)
    host._session_load_generation = 1
    host._on_session_load_finished(1, ("tail", tail))
    panel.flush_transcript_load()
    qtbot.wait(50)
    panel._finish_transcript_bottom_scroll()
    qapp.processEvents()

    bar = panel._scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(0)
    qapp.processEvents()
    panel._scroll_lock_enabled = False
    panel._on_scrollbar_slider_released()

    callback.assert_called_once()
    assert callback.call_args.args[0] == "older"
