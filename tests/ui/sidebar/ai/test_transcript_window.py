"""Tests for virtualized AI transcript window behavior."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from services.ai.chat.session_service import AiChatTranscriptPageDict
from services.ai.chat.transcript_window import INITIAL_TAIL_TURNS
from tests.ui.sidebar.ai.conftest import load_transcript_sync
from tests.ui.sidebar.ai.test_session_transcript_load import _long_messages, _tail_payload
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.transcript.window import _VirtualTranscriptSpacer


class _Host(_AiChatControllerMixin):
    """Controller host with session loader wiring."""

    def __init__(self, panel: AiChatPanel) -> None:
        """Attach panel and loader."""
        from types import SimpleNamespace

        from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader

        self._right_sidebar = cast(
            Any,
            SimpleNamespace(
                ai_chat_panel=panel,
                set_ai_session_title=lambda _title: None,
            ),
        )
        self._active_ai_session_id = None
        self._session_load_generation = 0
        from PySide6.QtWidgets import QWidget

        self._session_loader = AiChatSessionLoader(QWidget())


def _bubble_count(panel: AiChatPanel) -> int:
    """Count rendered transcript bubbles."""
    return len(panel.findChildren(ChatMessageBubble))


def test_tail_load_sets_has_older_and_message_ids(qapp: QApplication, qtbot) -> None:
    """Tail session load records window state and message ids on bubbles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    messages = _long_messages(INITIAL_TAIL_TURNS * 4)
    payload = _tail_payload("sess", "Tail", messages[-INITIAL_TAIL_TURNS * 2 :], has_older=True)
    host._session_load_generation = 1
    host._on_session_load_finished(1, payload)
    panel.flush_transcript_load()
    qtbot.wait(10)
    assert panel._has_older
    bubbles = panel.findChildren(ChatMessageBubble)
    assert bubbles
    assert all(bubble.message_id is not None for bubble in bubbles)


def test_prepend_older_page_preserves_anchor(qapp: QApplication, qtbot) -> None:
    """Silent older prepend keeps the first visible bubble anchored."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 320)
    tail = _long_messages(8)[-4:]
    page = AiChatTranscriptPageDict(
        messages=tail,
        has_older=True,
        has_newer=False,
        oldest_id=tail[0]["id"],
        newest_id=tail[-1]["id"],
    )
    panel.begin_virtual_session("sess", page)
    load_transcript_sync(panel, tail, qtbot)
    anchor = panel._first_loaded_bubble()
    assert anchor is not None
    before_y = panel._widget_top_in_viewport(anchor)
    older = _long_messages(8)[:4]
    panel.apply_older_page(
        AiChatTranscriptPageDict(
            messages=older,
            has_older=False,
            has_newer=True,
            oldest_id=older[0]["id"],
            newest_id=older[-1]["id"],
        ),
        generation=panel._window_page_generation,
    )
    qtbot.wait(10)
    after_y = panel._widget_top_in_viewport(anchor)
    assert abs(after_y - before_y) <= 4


def test_virtual_spacers_exist_without_visible_label(qapp: QApplication, qtbot) -> None:
    """Virtual spacers are present but there is no loading sentinel row."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_virtual_session(
        "sess",
        AiChatTranscriptPageDict(
            messages=[],
            has_older=False,
            has_newer=False,
            oldest_id=None,
            newest_id=None,
        ),
    )
    panel._ensure_virtual_spacers()
    spacers = panel.findChildren(_VirtualTranscriptSpacer)
    assert len(spacers) == 2


def test_scroll_up_requests_older_load(qapp: QApplication, qtbot) -> None:
    """Prefetch callback fires when older history is available near the top."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    callback = MagicMock()
    panel.set_window_load_callback(callback)
    panel.begin_virtual_session(
        "sess",
        AiChatTranscriptPageDict(
            messages=[],
            has_older=True,
            has_newer=False,
            oldest_id=1,
            newest_id=2,
        ),
    )
    panel._has_older = True
    panel._oldest_loaded_id = 1
    dummy = panel.add_message("user", "anchor")
    with (
        patch.object(panel, "_first_loaded_bubble", return_value=dummy),
        patch.object(panel, "_is_pinned_to_bottom", return_value=False),
        patch.object(panel, "_widget_top_in_viewport", return_value=20),
    ):
        panel._maybe_prefetch_older_page()
    assert callback.called
