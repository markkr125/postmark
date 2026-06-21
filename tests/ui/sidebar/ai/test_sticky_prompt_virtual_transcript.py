"""Sticky user-prompt overlay with virtualized tail-loaded transcripts."""

from __future__ import annotations

import uuid
from typing import Any, cast

from PySide6.QtWidgets import QApplication

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.chat.session_service import AiChatSessionService
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.user_message.overlay import StickyUserPromptOverlay

_USER_PROMPT = "Is insomnia better then postman?"


def _long_table_markdown() -> str:
    """Return a long assistant answer with a markdown comparison table."""
    rows = [
        "| Feature | Insomnia | Postman |",
        "|---------|----------|---------|",
        "| UI & UX | Minimalist, tab-based, dark-theme-friendly. | Feature-heavy dashboard UI. |",
        "| Request building | One-window form. | Menu-driven panels. |",
        "| Collaboration | Limited built-in sharing. | Strong team workspaces. |",
        "| Scripting | Plugin ecosystem. | Built-in pre-request and test scripts. |",
        "| Pricing | Generous free tier. | Free tier with paid team features. |",
    ]
    body = "\n".join(rows)
    # Repeat sections so the answer exceeds the viewport.
    sections = [f"## Comparison section {index}\n\n{body}\n" for index in range(12)]
    return "\n".join(sections)


class _Host(_AiChatControllerMixin):
    """Minimal controller host for session tail loads."""

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
        self._manual_ai_session_titles = set()
        from PySide6.QtWidgets import QWidget

        self._session_loader = AiChatSessionLoader(QWidget())


def _seed_session_with_long_tail(*, filler_turns: int) -> str:
    """Persist filler turns plus one long user/assistant tail turn."""
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Sticky virtual", model_id=None, mode="agent")
    for index in range(filler_turns):
        append_message(session_id=session_id, role="user", content=f"filler user {index}")
        append_message(session_id=session_id, role="assistant", content=f"filler answer {index}")
    append_message(session_id=session_id, role="user", content=_USER_PROMPT)
    append_message(session_id=session_id, role="assistant", content=_long_table_markdown())
    return session_id


def _sticky_turn_prompt(panel: AiChatPanel) -> StickyUserPromptOverlay | None:
    """Return the sticky overlay on the transcript viewport, if any."""
    viewport = panel._scroll.viewport()
    for child in viewport.children():
        if isinstance(child, StickyUserPromptOverlay):
            return child
    return None


def _last_user_bubble(panel: AiChatPanel) -> ChatMessageBubble:
    """Return the chronologically last user bubble."""
    last: ChatMessageBubble | None = None
    for bubble in panel.findChildren(ChatMessageBubble):
        if bubble.role == "user":
            last = bubble
    assert last is not None
    return last


def _scroll_until_sticky_shows(
    panel: AiChatPanel,
    qapp: QApplication,
    *,
    prompt: str,
    force_render: bool = False,
) -> StickyUserPromptOverlay:
    """Scroll down until the sticky overlay shows *prompt*."""
    bar = panel._scroll.verticalScrollBar()
    for _ in range(400):
        if force_render:
            panel._render_visible_lazy_markdown(force=True)
        else:
            panel._render_visible_lazy_markdown()
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_turn_prompt(panel)
        if sticky is not None and sticky.isVisible() and sticky.text() == prompt:
            return sticky
        if bar.value() >= bar.maximum():
            break
        bar.setValue(min(bar.maximum(), bar.value() + 28))
        qapp.processEvents()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None, "sticky overlay was never created"
    assert sticky.isVisible(), "sticky overlay stayed hidden"
    assert sticky.text() == prompt
    return sticky


def test_sticky_shows_when_scrolling_long_virtual_tail_table(
    qapp: QApplication,
    qtbot,
) -> None:
    """Tail-loaded lazy markdown sessions still pin the user prompt while scrolling."""
    session_id = _seed_session_with_long_tail(filler_turns=40)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None
    assert tail["page"]["has_older"]

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
    panel._finish_transcript_bottom_scroll()
    qapp.processEvents()

    user = _last_user_bubble(panel)
    assert user.text() == _USER_PROMPT
    assert panel._turn_scroll_anchor is user

    sticky = _scroll_until_sticky_shows(panel, qapp, prompt=_USER_PROMPT, force_render=False)
    assert sticky.text() == _USER_PROMPT


def test_sticky_shows_with_deferred_assistant_before_lazy_render(
    qapp: QApplication,
    qtbot,
) -> None:
    """Sticky must appear while the assistant body is still lazy-rendered."""
    session_id = _seed_session_with_long_tail(filler_turns=40)
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
    qapp.processEvents()

    # Avoid bottom pin so the tail assistant stays lazy-rendered.
    panel._turn_scroll_anchor = panel._find_last_turn_user_bubble()
    bar = panel._scroll.verticalScrollBar()
    bar.setValue(0)
    panel._scroll_lock_enabled = False
    qapp.processEvents()

    user = _last_user_bubble(panel)
    assistants = [b for b in panel.findChildren(ChatMessageBubble) if b.role == "assistant"]
    last_assistant = assistants[-1]
    body = last_assistant._markdown_body
    assert body is not None

    for _ in range(400):
        panel._render_visible_lazy_markdown()
        bar.setValue(min(bar.maximum(), bar.value() + 28))
        qapp.processEvents()
        if panel._widget_top_in_viewport(user) < -4 and panel._bubble_intersects_viewport(
            last_assistant
        ):
            break

    assert panel._widget_top_in_viewport(user) < 0
    assert panel._bubble_intersects_viewport(last_assistant)

    panel._sync_sticky_turn_prompt()
    sticky = _sticky_turn_prompt(panel)
    assert sticky is not None
    assert sticky.isVisible()
    assert sticky.text() == _USER_PROMPT


def _user_bubble_with_text(panel: AiChatPanel, text: str) -> ChatMessageBubble:
    """Return the user bubble whose text matches *text*."""
    for bubble in panel.findChildren(ChatMessageBubble):
        if bubble.role == "user" and bubble.text() == text:
            return bubble
    msg = f"user bubble with text {text!r} not found"
    raise AssertionError(msg)


def test_sticky_works_when_user_bubble_was_evicted(
    qapp: QApplication,
    qtbot,
) -> None:
    """Sticky still pins the prompt when virtualization evicted the user row."""
    session_id = _seed_session_with_long_tail(filler_turns=40)
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
    panel._finish_transcript_bottom_scroll()
    qapp.processEvents()

    tail_user = _user_bubble_with_text(panel, _USER_PROMPT)
    tail_assistant = panel._assistant_bubble_for_turn(tail_user)
    assert tail_assistant is not None

    bar = panel._scroll.verticalScrollBar()
    for _ in range(400):
        panel._render_visible_lazy_markdown()
        bar.setValue(min(bar.maximum(), bar.value() + 28))
        qapp.processEvents()
        if panel._widget_top_in_viewport(tail_user) < -4:
            break

    panel._destroy_virtual_bubble(tail_user)
    qapp.processEvents()
    assert panel._assistant_bubble_for_turn(tail_user) is None
    assert tail_assistant.isVisible()

    sticky = _scroll_until_sticky_shows(panel, qapp, prompt=_USER_PROMPT, force_render=False)
    assert sticky.text() == _USER_PROMPT
