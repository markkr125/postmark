"""Tests for async session transcript loading."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from services.ai.chat.session_service import (
    AiChatMessageDict,
    AiChatSessionTailLoadDict,
    AiChatTranscriptPageDict,
)
from tests.ui.sidebar.ai.conftest import load_transcript_sync
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble


def _session_row(session_id: str, title: str) -> dict[str, Any]:
    """Build a minimal session dict for controller tests."""
    return {
        "id": session_id,
        "title": title,
        "model_id": "gpt-test",
        "mode": "agent",
        "agent_id": "postmark-assistant",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "last_preview": None,
        "archived": False,
    }


def _tail_payload(
    session_id: str,
    title: str,
    messages: list[AiChatMessageDict],
    *,
    has_older: bool = False,
) -> tuple[str, AiChatSessionTailLoadDict]:
    """Build a tail-load worker payload for controller tests."""
    oldest_id = messages[0]["id"] if messages else None
    newest_id = messages[-1]["id"] if messages else None
    return (
        "tail",
        AiChatSessionTailLoadDict(
            session=cast(Any, _session_row(session_id, title)),
            page=AiChatTranscriptPageDict(
                messages=messages,
                has_older=has_older,
                has_newer=False,
                oldest_id=oldest_id,
                newest_id=newest_id,
            ),
        ),
    )


def _long_messages(count: int) -> list[AiChatMessageDict]:
    """Build alternating turns with fenced code for load stress tests."""
    messages: list[AiChatMessageDict] = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        body = (
            f"{role} line {index}\n```python\nprint('block')\n```\n" * 2
            if role == "assistant"
            else f"Question {index}?"
        )
        messages.append(
            {
                "id": index,
                "session_id": "s1",
                "role": role,
                "content": body,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
    return messages


class _Host(_AiChatControllerMixin):
    """Minimal controller host for session-load tests."""

    def __init__(self, panel: AiChatPanel) -> None:
        """Wire a panel as the right-sidebar chat surface."""
        self._right_sidebar = cast(Any, SimpleNamespace(ai_chat_panel=panel))
        self._active_ai_session_id = None
        self._session_load_generation = 0
        from PySide6.QtWidgets import QWidget as _QWidget

        parent = _QWidget()
        from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader

        self._session_loader = AiChatSessionLoader(parent)


def test_lazy_markdown_defers_until_viewport_render(qapp: QApplication, qtbot) -> None:
    """Off-screen assistant rows defer Pygments until scrolled into view."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 120)
    messages = _long_messages(20)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    bodies = [
        bubble._markdown_body
        for bubble in panel.findChildren(ChatMessageBubble)
        if bubble.role == "assistant" and bubble._markdown_body is not None
    ]
    assert len(bodies) >= 4
    panel._scroll.verticalScrollBar().setValue(0)
    qapp.processEvents()
    panel._render_visible_lazy_markdown()
    assert any(body.is_render_deferred() for body in bodies)
    panel._scroll.verticalScrollBar().setValue(panel._scroll.verticalScrollBar().maximum())
    qapp.processEvents()
    panel._render_visible_lazy_markdown()
    assert any(not body.is_render_deferred() for body in bodies)


def test_activate_skips_reload_for_current_session(qapp: QApplication, qtbot) -> None:
    """Selecting the already-active session does not restart transcript load."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    host._active_ai_session_id = "sess-a"
    with patch.object(panel, "prepare_transcript_load") as prepare:
        host._activate_chat_session("sess-a")
    prepare.assert_not_called()


def test_activate_uses_tail_loader(qapp: QApplication, qtbot) -> None:
    """Session activation loads only the virtualized transcript tail."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    with patch.object(host._session_loader, "load_tail") as load_tail:
        host._activate_chat_session("sess-tail")
    load_tail.assert_called_once_with("sess-tail", 1)


def test_activate_cancels_session_loader(qapp: QApplication, qtbot) -> None:
    """Switching sessions cancels stale background loader results."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    host._active_ai_session_id = "sess-a"
    with (
        patch.object(host._session_loader, "cancel", autospec=True) as cancel_mock,
        patch.object(host._session_loader, "load_tail") as load_tail,
    ):
        host._activate_chat_session("sess-b")
    cancel_mock.assert_called_once()
    load_tail.assert_called_once_with("sess-b", 1)


def test_cancel_transcript_load_drops_stale_deferred_finish(qapp: QApplication, qtbot) -> None:
    """Cancelling transcript load ignores a previously queued finish callback."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    finished: list[int] = []
    panel.transcript_load_finished.connect(lambda: finished.append(1))
    messages = _long_messages(4)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.cancel_transcript_load()
    qtbot.wait(50)
    assert finished == []
    assert not panel.is_transcript_load_active()


def test_reset_transcript_window_bumps_page_generation(qapp: QApplication, qtbot) -> None:
    """Teardown invalidates in-flight virtual page fetch generations."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel._window_page_generation = 5
    panel.reset_transcript_window()
    assert panel._window_page_generation == 6


def test_session_load_finished_applies_chrome_before_transcript(qapp: QApplication, qtbot) -> None:
    """Worker completion updates title before incremental transcript build."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    payload = _tail_payload(
        "sess-b",
        "Rust HTTP",
        [
            {
                "id": 1,
                "session_id": "sess-b",
                "role": "user",
                "content": "hi",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ],
    )
    host._session_load_generation = 1
    with patch.object(host, "_apply_session_chrome") as chrome:
        host._on_session_load_finished(1, payload)
    chrome.assert_called_once()
    assert host._active_ai_session_id == "sess-b"
    panel.flush_transcript_load()
    assert len(panel.findChildren(ChatMessageBubble)) == 1


def test_stale_session_load_generation_is_ignored(qapp: QApplication, qtbot) -> None:
    """Out-of-date worker results do not replace a newer session selection."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    host = _Host(panel)
    host._session_load_generation = 2
    payload = _tail_payload("old", "Old", [])
    host._on_session_load_finished(1, payload)
    assert host._active_ai_session_id is None


def test_incremental_load_chunked_build_completes(qapp: QApplication, qtbot) -> None:
    """Chunked transcript load finishes with all rows present."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(12)
    load_transcript_sync(panel, messages, qtbot)
    assert len(panel.findChildren(ChatMessageBubble)) == 12


def test_load_transcript_pins_scroll_to_bottom(qapp: QApplication, qtbot) -> None:
    """Session transcript load keeps the viewport at the newest messages."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 240)
    messages = _long_messages(24)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    qtbot.wait(10)
    bar = panel._scroll.verticalScrollBar()
    assert bar.maximum() > 0
    assert panel._is_pinned_to_bottom()


def test_transcript_loading_overlay_until_layout_finishes(qapp: QApplication, qtbot) -> None:
    """The line loading overlay stays visible until the transcript fully settles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(8)
    panel.prepare_transcript_load(lazy_markdown=True)
    assert panel._transcript_loading.is_loading_visible()
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    qtbot.wait(10)
    assert not panel._transcript_loading.is_loading_visible()
    assert len(panel.findChildren(ChatMessageBubble)) == 8


def test_hidden_panel_defers_bottom_scroll_until_shown(qapp: QApplication, qtbot) -> None:
    """Startup-style restore pins the bottom once the transcript viewport is visible."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(16)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    assert panel._pending_transcript_bottom_scroll
    panel.show()
    panel.resize(360, 240)
    qtbot.waitExposed(panel)
    qapp.processEvents()
    panel._finish_transcript_bottom_scroll()
    qapp.processEvents()
    bar = panel._scroll.verticalScrollBar()
    assert panel._is_pinned_to_bottom(), f"val={bar.value()} max={bar.maximum()}"
    panel._end_post_load_bottom_settle()
    assert not panel._pending_transcript_bottom_scroll


def test_startup_restore_show_event_pins_bottom(qapp: QApplication, qtbot) -> None:
    """Deferred bottom pinning after a hidden startup load settles when the panel opens."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages = _long_messages(20)
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    assert panel._pending_transcript_bottom_scroll
    panel.show()
    panel.resize(360, 240)
    qtbot.waitExposed(panel)
    for _ in range(8):
        qapp.processEvents()
    qtbot.wait(200)
    bar = panel._scroll.verticalScrollBar()
    assert bar.maximum() > 0
    assert panel._is_pinned_to_bottom(), f"val={bar.value()} max={bar.maximum()}"


def test_post_load_settle_repins_when_transcript_grows_below(qapp: QApplication, qtbot) -> None:
    """Post-load settle re-pins when assistant rows grow before the settle window ends."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 240)
    messages = _long_messages(12)
    load_transcript_sync(panel, messages, qtbot)
    assert panel._post_load_bottom_settle_active
    bar = panel._scroll.verticalScrollBar()
    assert panel._is_pinned_to_bottom()
    last = panel._last_assistant_bubble()
    assert last is not None and last._markdown_body is not None
    last._markdown_body.set_markdown(
        last._markdown_body.document().toPlainText() + "\n\n```python\nprint('grow')\n```\n" * 6
    )
    panel._messages.updateGeometry()
    panel._scroll.updateGeometry()
    qapp.processEvents()
    assert panel._is_pinned_to_bottom(), f"val={bar.value()} max={bar.maximum()}"


def _assistant_tail_messages() -> list[AiChatMessageDict]:
    """Build one assistant turn with a table and em-dash tail for footer geometry tests."""
    tail = (
        "| OS | Notes |\n| --- | --- |\n| macOS | Unix-like |\n| Linux | Free |\n\n"
        + ("Wrap paragraph text. " * 30)
        + "primary target platform—and the tail must stay visible."
    )
    return [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "mac vs linux vs windows?",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": tail,
            "created_at": "2026-01-01T00:00:01+00:00",
            "model_id": "m1",
            "prompt_tokens": 10,
            "completion_tokens": 5,
        },
    ]


def _entry() -> AiModelEntry:
    return {
        "id": "m1",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "input_cost_per_token": 0.0000025,
        "output_cost_per_token": 0.00001,
    }


def test_lazy_session_restore_footer_below_assistant_tail(qapp: QApplication, qtbot) -> None:
    """Lazy session restore keeps the em-dash tail above the dashed footer separator."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitExposed(panel)
    panel.resize(360, 500)
    panel.set_models([_entry()])
    messages = _assistant_tail_messages()
    panel.prepare_transcript_load(lazy_markdown=True)
    panel.load_transcript_async(messages, generation=1, lazy_markdown=True)
    panel.flush_transcript_load()
    panel._scroll.verticalScrollBar().setValue(panel._scroll.verticalScrollBar().maximum())
    qapp.processEvents()
    panel._render_visible_lazy_markdown(force=True)
    qapp.processEvents()

    assistant: ChatMessageBubble | None = None
    for bubble in panel.findChildren(ChatMessageBubble):
        if bubble.role == "assistant":
            assistant = bubble
    assert assistant is not None
    body = assistant._markdown_body
    footer = assistant._assistant_footer
    assert body is not None
    assert footer is not None
    assert not body.is_render_deferred()
    assert "tail must stay visible" in body.markdown()

    doc_layout = body.document().documentLayout()
    max_bottom = doc_layout.documentSize().height()
    block = body.document().begin()
    while block != body.document().end():
        max_bottom = max(max_bottom, doc_layout.blockBoundingRect(block).bottom())
        block = block.next()
    assert body.height() >= int(max_bottom)

    content_bottom = body.mapTo(assistant, QPoint(0, body._painted_content_height_px)).y()
    footer_top = footer.mapTo(assistant, QPoint(0, 0)).y()
    assert footer_top >= content_bottom
    assert body._paint_footer_rule


def test_transcript_legacy_assistant_uses_session_model_for_footer(
    qapp: QApplication,
    qtbot,
    monkeypatch,
) -> None:
    """Assistant rows saved before per-message model ids use the session model."""
    entry: AiModelEntry = {
        "id": "gpt-test",
        "provider": "openai",
        "label": "GPT-4o",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
    }
    monkeypatch.setattr(
        "services.ai.chat.message_usage.AiConfig.get_models",
        lambda: [entry],
    )

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([entry])
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "assistant",
            "content": "Legacy answer",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    panel.prepare_transcript_load(lazy_markdown=False)
    panel.begin_virtual_session(
        "s1",
        AiChatTranscriptPageDict(
            messages=messages,
            has_older=False,
            has_newer=False,
            oldest_id=1,
            newest_id=1,
        ),
        session_model_id="gpt-test",
    )
    panel.load_transcript_async(messages, generation=1, lazy_markdown=False)
    panel.flush_transcript_load()
    qtbot.wait(10)

    assistant = panel.findChildren(ChatMessageBubble)[0]
    footer = assistant._assistant_footer
    assert footer is not None
    assert footer._usage_label.text() == "GPT-4o"


def test_history_popup_open_during_transcript_load(qapp: QApplication, qtbot) -> None:
    """History popover stays safe while transcript widgets are building."""
    import uuid

    from PySide6.QtCore import QObject, Signal
    from database.models.ai_chat.ai_chat_repository import append_message, create_session
    from ui.sidebar import RightSidebar
    from ui.sidebar.ai.chat_sessions.history_popup import AiSessionHistoryPopup

    session_ids: list[str] = []
    for index in range(3):
        session_id = str(uuid.uuid4())
        create_session(
            session_id=session_id,
            title=f"Popup stress {index}",
            model_id="gpt-test",
            mode="agent",
        )
        for turn in range(8):
            append_message(
                session_id=session_id,
                role="user" if turn % 2 == 0 else "assistant",
                content=f"turn {turn}",
            )
        session_ids.append(session_id)

    class _Host(QObject, _AiChatControllerMixin):
        _ai_assistant_finish_requested = Signal(str, str)
        _ai_chat_fail_requested = Signal(str, str, str)
        _ai_title_ready_requested = Signal(str)

        def __init__(self, sidebar: RightSidebar) -> None:
            super().__init__()
            self._right_sidebar = sidebar
            self._init_ai_chat_controller()

    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    sidebar.open_panel("ai")
    sidebar.show()
    qtbot.waitExposed(sidebar)
    panel = sidebar.ai_chat_panel
    panel.set_models(
        [
            AiModelEntry(
                id="gpt-test",
                provider="openai",
                label="GPT",
                model="openai/gpt-4o",
                base_url="",
                api_version="",
                auth_kind="none",
                auth_ref="",
                context=128_000,
                enabled=True,
            )
        ]
    )
    host = _Host(sidebar)
    popup = AiSessionHistoryPopup.instance()
    anchor = sidebar.ai_history_button

    try:
        for session_id in session_ids:
            host._activate_chat_session(session_id)
            popup.open_for(anchor, host._on_ai_session_selected, active_session_id=session_id)
            for _ in range(25):
                qapp.processEvents()
            popup.hide_popup()
            panel.cancel_transcript_load()
            for _ in range(10):
                qapp.processEvents()
    finally:
        popup.hide_popup()
        host._cleanup_ai_chat_threads()
        panel.cancel_transcript_load()
        panel._shutdown_context_usage_worker()
        qapp.processEvents()
