"""Integration tests for the AI chat context ring, popup, and transcript hooks."""

from __future__ import annotations

import uuid
from typing import cast

from PySide6.QtWidgets import QApplication

from database.models.ai_chat.ai_chat_repository import append_message, create_session
from services.ai.ai_config import AiModelEntry
from services.ai.chat.context_usage import ContextUsageSdkMetrics, ContextUsageService
from services.ai.chat.session_service import AiChatSessionService
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.chat_context_popup import AiChatContextUsagePopup
from ui.sidebar.ai.model_picker_popup import AiModelPickerPopup
from ui.sidebar.sidebar_widget import RightSidebar


def _entry(model_id: str, *, context: int) -> AiModelEntry:
    return {
        "id": model_id,
        "provider": "openai",
        "label": model_id,
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "context": context,
        "enabled": True,
    }


def _seed_session(turns: int) -> str:
    session_id = str(uuid.uuid4())
    create_session(session_id=session_id, title="Usage", model_id="m1", mode="agent")
    for index in range(turns):
        append_message(session_id=session_id, role="user", content=f"user {index}")
        append_message(
            session_id=session_id,
            role="assistant",
            content=f"assistant {index}",
            thinking=f"trace {index}",
        )
    return session_id


def _wait_for_breakdown(panel: AiChatPanel, qtbot) -> None:
    qtbot.waitUntil(lambda: panel._context_breakdown is not None, timeout=10000)


def test_session_load_refreshes_ring_from_sqlite(qapp: QApplication, qtbot) -> None:
    """Loading a persisted session produces non-zero context usage from full SQLite rows."""
    session_id = _seed_session(6)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=128_000)])

    def _sync_refresh(sdk_metrics: object | None = None) -> None:
        session = AiChatSessionService.get_session(session_id)
        breakdown = ContextUsageService.build_breakdown_for_session(
            session_id,
            entry=panel.current_model_entry(),
            agent_id=session["agent_id"] if session is not None else "postmark-assistant",
            draft_text=panel._input.toPlainText(),
            sdk_metrics=cast(ContextUsageSdkMetrics | None, sdk_metrics)
            if isinstance(sdk_metrics, dict)
            else None,
        )
        panel.set_context_breakdown(breakdown)

    panel.refresh_context_usage = _sync_refresh  # type: ignore[method-assign]
    panel.show()
    qtbot.waitExposed(panel)
    panel.begin_virtual_session(session_id, tail["page"])
    panel.load_transcript_async(
        tail["page"]["messages"],
        generation=1,
        lazy_markdown=True,
        page=tail["page"],
    )
    panel.flush_transcript_load()
    _wait_for_breakdown(panel, qtbot)

    assert panel._context_breakdown is not None
    assert panel._context_breakdown["used_tokens"] > 0
    labels = {category["label"] for category in panel._context_breakdown["categories"]}
    assert "Conversation" in labels
    assert "System prompt" in labels
    panel._shutdown_context_usage_worker()
    panel._shutdown_context_usage_worker()


def test_composer_typing_debounced_refresh_updates_used_tokens(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """Typing in the composer increases the conversation bucket without sending."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=128_000)])
    monkeypatch.setattr(
        "services.ai.chat.context_usage.estimate_text_tokens",
        lambda text, _model, **_kw: len(text),
    )
    panel.refresh_context_usage()
    qtbot.wait(400)
    before = panel._context_ring.used_tokens()
    panel._input.setPlainText("x" * 200)
    qtbot.wait(400)
    panel._shutdown_context_usage_worker()
    assert panel._context_ring.used_tokens() >= before


def test_model_change_updates_context_total(qapp: QApplication, qtbot) -> None:
    """Picking a model with a different context window updates the ring total."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=64_000), _entry("m2", context=256_000)])

    panel._on_model_picked("m2")

    assert panel._context_ring.total_tokens() == 256_000
    panel._shutdown_context_usage_worker()


def test_context_popup_is_mutually_exclusive_with_model_picker(qapp: QApplication, qtbot) -> None:
    """Opening the model picker closes the context popup."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=128_000)])
    panel.show()
    qtbot.waitExposed(panel)
    panel.set_context_breakdown(
        {
            "used_tokens": 10_000,
            "total_tokens": 128_000,
            "categories": [
                {"id": "system_prompt", "label": "System prompt", "tokens": 1000},
                {"id": "tools", "label": "Tools", "tokens": 0},
                {"id": "rules", "label": "Rules", "tokens": 0},
                {"id": "skills", "label": "Skills", "tokens": 0},
                {"id": "mcp", "label": "MCP", "tokens": 0},
                {"id": "subagents", "label": "Subagents", "tokens": 0},
                {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 0},
                {"id": "conversation", "label": "Conversation", "tokens": 9000},
            ],
            "has_summarized": False,
            "is_estimated": True,
        }
    )

    panel._toggle_context_popup()
    assert AiChatContextUsagePopup.instance().isVisible()

    panel._open_model_picker()

    assert not AiChatContextUsagePopup.instance().isVisible()
    assert AiModelPickerPopup.instance().isVisible()
    AiModelPickerPopup.instance().hidePopup()
    panel._shutdown_context_usage_worker()


def test_context_popup_explains_high_estimated_usage(qapp: QApplication, qtbot) -> None:
    """High fallback estimates tell users the SDK model context is not loaded yet."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=1000)])
    panel.show()
    qtbot.waitExposed(panel)
    panel.set_context_breakdown(
        {
            "used_tokens": 750,
            "total_tokens": 1000,
            "categories": [
                {"id": "system_prompt", "label": "System prompt", "tokens": 50},
                {"id": "tools", "label": "Tools", "tokens": 0},
                {"id": "rules", "label": "Rules", "tokens": 0},
                {"id": "skills", "label": "Skills", "tokens": 0},
                {"id": "mcp", "label": "MCP", "tokens": 0},
                {"id": "subagents", "label": "Subagents", "tokens": 0},
                {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 0},
                {"id": "conversation", "label": "Conversation", "tokens": 700},
            ],
            "has_summarized": False,
            "is_estimated": True,
        }
    )

    panel._toggle_context_popup()
    popup = AiChatContextUsagePopup.instance()

    assert popup._hint.isVisible()
    assert "estimated until the model context is available" in popup._hint.text()
    popup.hide_popup()
    panel._shutdown_context_usage_worker()


def test_context_popup_closes_model_picker(qapp: QApplication, qtbot) -> None:
    """Opening the context popup closes the model picker."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=128_000)])
    panel.show()
    qtbot.waitExposed(panel)
    panel.set_context_breakdown(
        {
            "used_tokens": 5000,
            "total_tokens": 128_000,
            "categories": [
                {"id": "system_prompt", "label": "System prompt", "tokens": 1000},
                {"id": "tools", "label": "Tools", "tokens": 0},
                {"id": "rules", "label": "Rules", "tokens": 0},
                {"id": "skills", "label": "Skills", "tokens": 0},
                {"id": "mcp", "label": "MCP", "tokens": 0},
                {"id": "subagents", "label": "Subagents", "tokens": 0},
                {"id": "summarized_conversation", "label": "Summarized conversation", "tokens": 0},
                {"id": "conversation", "label": "Conversation", "tokens": 4000},
            ],
            "has_summarized": False,
            "is_estimated": True,
        }
    )

    panel._open_model_picker()
    assert AiModelPickerPopup.instance().isVisible()

    panel._toggle_context_popup()

    assert not AiModelPickerPopup.instance().isVisible()
    assert AiChatContextUsagePopup.instance().isVisible()
    AiChatContextUsagePopup.instance().hide_popup()
    panel._shutdown_context_usage_worker()


def test_ring_follows_sdk_count_when_sqlite_estimate_is_higher(
    qapp: QApplication, qtbot, monkeypatch
) -> None:
    """When SQLite rows outpace SDK events, the ring follows the SDK view count."""
    from services.ai.chat.context_usage_sdk import SdkViewSnapshot

    session_id = _seed_session(8)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None

    monkeypatch.setattr(
        "services.ai.chat.context_usage.count_transcript_messages",
        lambda _messages, _model, **_kw: 90_000,
    )
    monkeypatch.setattr(
        "services.ai.chat.context_usage.measure_sdk_view",
        lambda *_args, **_kw: SdkViewSnapshot(
            event_count=2,
            view_tokens=12_000,
            summarized_tokens=0,
            has_summarized=False,
            condenser_max_size=45,
            condenser_max_tokens=92_160,
            condenser_minimum_progress=0.05,
            condensation_reasons=[],
        ),
    )

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=128_000)])

    def _sync_refresh(sdk_metrics: object | None = None) -> None:
        session = AiChatSessionService.get_session(session_id)
        breakdown = ContextUsageService.build_breakdown_for_session(
            session_id,
            entry=panel.current_model_entry(),
            agent_id=session["agent_id"] if session is not None else "postmark-assistant",
            sdk_metrics=cast(ContextUsageSdkMetrics | None, sdk_metrics)
            if isinstance(sdk_metrics, dict)
            else None,
        )
        panel.set_context_breakdown(breakdown)

    panel.refresh_context_usage = _sync_refresh  # type: ignore[method-assign]
    panel.begin_virtual_session(session_id, tail["page"])
    panel.load_transcript_async(
        tail["page"]["messages"],
        generation=1,
        lazy_markdown=True,
        page=tail["page"],
    )
    panel.flush_transcript_load()
    panel.refresh_context_usage()
    _wait_for_breakdown(panel, qtbot)

    assert panel._context_breakdown is not None
    assert panel._context_breakdown["used_tokens"] < 20_000
    assert panel._context_breakdown["is_estimated"] is False
    assert panel._context_breakdown["transcript_larger_than_sdk"] is True
    panel._shutdown_context_usage_worker()


def test_compaction_activity_shows_summarizing_caption(qapp: QApplication, qtbot) -> None:
    """SDK compaction status replaces the generic Thinking caption."""
    from ui.sidebar.ai.message_bubble import ChatMessageBubble

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.activity_message() == "Thinking…"

    panel.deliver_activity_status("Summarizing earlier messages…")

    assert bubble.is_activity_visible()
    assert bubble.activity_message() == "Summarizing earlier messages…"
    panel._shutdown_context_usage_worker()


def test_set_context_breakdown_inserts_summarized_notice(qapp: QApplication, qtbot) -> None:
    """``has_summarized`` on the breakdown triggers the transcript notice row."""
    from PySide6.QtWidgets import QWidget

    from services.ai.chat.session_service import AiChatSessionService

    session_id = _seed_session(1)
    tail = AiChatSessionService.get_session_tail(session_id)
    assert tail is not None

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models([_entry("m1", context=128_000)])
    panel.begin_virtual_session(session_id, tail["page"])
    panel.load_transcript_async(
        tail["page"]["messages"],
        generation=1,
        lazy_markdown=True,
        page=tail["page"],
    )
    panel.flush_transcript_load()

    panel.set_context_breakdown(
        {
            "used_tokens": 1000,
            "total_tokens": 128_000,
            "categories": [],
            "has_summarized": True,
            "is_estimated": True,
        }
    )

    notices = [
        widget
        for widget in panel._messages.findChildren(QWidget)
        if widget.objectName() == "aiChatSummarizedNotice"
    ]
    assert len(notices) == 1
    panel._shutdown_context_usage_worker()


def test_flyout_hide_closes_context_popup(qapp: QApplication, qtbot) -> None:
    """Collapsing the right flyout hides the context popup."""
    sidebar = RightSidebar()
    qtbot.addWidget(sidebar)
    sidebar.open_panel("ai")
    panel = sidebar.ai_chat_panel
    panel.set_models([_entry("m1", context=128_000)])
    popup = AiChatContextUsagePopup.instance()
    popup.show_for(panel._context_ring, None)
    qtbot.waitExposed(popup)
    sidebar._close_panel()
    qtbot.waitUntil(lambda: not popup.isVisible(), timeout=2000)
    panel._shutdown_context_usage_worker()
    panel._shutdown_context_usage_worker()
    panel._shutdown_context_usage_worker()
