"""Tests for AiChatPanel transcript and streaming helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from services.ai.ai_config import AiConfig, AiModelEntry
from services.ai.chat.session_service import AiChatMessageDict
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


def _flush_stream_chunks(qtbot) -> None:
    """Wait for the coalesced chunk delivery timer (~50ms)."""
    qtbot.wait(60)


def test_user_message_shows_sent_timestamp(qapp: QApplication, qtbot) -> None:
    """User rows show a muted send-time label inside the bubble."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("user", "hello", sent_at=datetime(2026, 1, 15, 9, 30, tzinfo=UTC))
    bubble = panel.findChildren(ChatMessageBubble)[0]
    frame = bubble.findChild(QFrame, "aiChatMessageUser")
    assert frame is not None
    label = frame.findChild(QLabel, "aiChatUserMessageTime")
    assert label is not None
    assert not label.isHidden()
    assert "Jan" in label.text()
    assert "30" in label.text()


def test_load_transcript_restores_user_timestamp(qapp: QApplication, qtbot) -> None:
    """``load_transcript`` shows persisted user ``created_at`` inside the bubble."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "Hi",
            "created_at": "2026-01-15T09:30:00+00:00",
        },
    ]
    panel.load_transcript(messages)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    frame = bubble.findChild(QFrame, "aiChatMessageUser")
    assert frame is not None
    label = frame.findChild(QLabel, "aiChatUserMessageTime")
    assert label is not None
    assert not label.isHidden()
    assert "Jan" in label.text()
    assert "30" in label.text()


def test_load_transcript_repaints(qapp: QApplication, qtbot) -> None:
    """``load_transcript`` clears and rebuilds message bubbles."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("user", "old")
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "user",
            "content": "Hi",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "session_id": "s1",
            "role": "assistant",
            "content": "Hello",
            "created_at": "2026-01-01T00:00:01+00:00",
        },
    ]
    panel.load_transcript(messages)
    bubbles = panel.findChildren(ChatMessageBubble)
    assert len(bubbles) == 2
    assert bubbles[0].text() == "Hi"
    assert bubbles[1].text() == "Hello"


def test_streaming_updates_one_bubble(qapp: QApplication, qtbot) -> None:
    """Streaming begin/append/end updates a single assistant bubble."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "Hel")
    panel.append_assistant_chunk("", "lo")
    _flush_stream_chunks(qtbot)
    bubbles = panel.findChildren(ChatMessageBubble)
    assert len(bubbles) == 1
    assert bubbles[0].text() == "Hello"
    panel.end_assistant_stream("Hello!")
    assert bubbles[0].text() == "Hello!"


def test_end_assistant_stream_ignores_late_chunks(qapp: QApplication, qtbot) -> None:
    """Chunks emitted after finalization must not spawn a second bubble."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("Partial", "")
    panel.end_assistant_stream("Answer", thinking="Full thinking trace")
    panel.append_assistant_chunk("late", "")
    bubbles = panel.findChildren(ChatMessageBubble)
    assert len(bubbles) == 1
    assert bubbles[0].thinking_text() == "Full thinking trace"
    assert bubbles[0].text() == "Answer"


def test_begin_assistant_stream_shows_activity(qapp: QApplication, qtbot) -> None:
    """An empty stream shows a spinner and Thinking caption immediately."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.is_activity_visible()
    assert bubble.activity_message() == "Thinking…"


def test_first_chunk_hides_activity(qapp: QApplication, qtbot) -> None:
    """Activity hides when the first thinking or answer token arrives."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    panel.append_assistant_chunk("trace", "")
    _flush_stream_chunks(qtbot)
    assert not bubble.is_activity_visible()
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[-1]
    panel.append_assistant_chunk("", "Hi")
    _flush_stream_chunks(qtbot)
    assert not bubble.is_activity_visible()


def test_end_assistant_stream_clears_activity_without_chunks(qapp: QApplication, qtbot) -> None:
    """Finalize clears activity even when no tokens were streamed."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    panel.end_assistant_stream("Error: No response from model", thinking="")
    assert not bubble.is_activity_visible()


def test_load_transcript_does_not_show_activity(qapp: QApplication, qtbot) -> None:
    """Restored assistant rows never show the streaming activity row."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "assistant",
            "content": "Answer",
            "thinking": "trace",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    panel.load_transcript(messages)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert not bubble.is_activity_visible()


def test_on_activity_long_wait_escalates_message(qapp: QApplication, qtbot) -> None:
    """Slow first-token responses escalate the activity caption."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    panel._on_activity_long_wait()
    assert "Taking longer than expected" in bubble.activity_message()


def test_set_activity_status_maps_sdk_labels(qapp: QApplication, qtbot) -> None:
    """Human-readable SDK statuses update the activity caption."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    panel.set_activity_status("planning")
    assert bubble.activity_message() == "Planning…"
    panel.set_activity_status("AgentState.RUNNING")
    assert bubble.activity_message() == "Planning…"


def test_set_activity_status_ignored_after_first_chunk(qapp: QApplication, qtbot) -> None:
    """Status updates are ignored once streaming content is visible."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    bubble = panel.findChildren(ChatMessageBubble)[0]
    panel.append_assistant_chunk("", "Hi")
    _flush_stream_chunks(qtbot)
    panel.set_activity_status("planning")
    assert not bubble.is_activity_visible()


def test_streaming_collapses_thinking_when_answer_starts(qapp: QApplication, qtbot) -> None:
    """Thinking expands while streaming, then collapses with duration when answer starts."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("Internal reasoning", "")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.thinking_text() == "Internal reasoning"
    assert bubble.text() == ""
    assert bubble.is_thinking_expanded()

    panel.append_assistant_chunk("", "Hello")
    _flush_stream_chunks(qtbot)
    assert bubble.text() == "Hello"
    assert not bubble.is_thinking_expanded()
    assert "Thought for" in bubble.thought_header_text()
    panel.end_assistant_stream("Hello", thinking="Internal reasoning")
    assert not bubble.is_thinking_expanded()


def test_end_assistant_stream_keeps_longer_thinking(qapp: QApplication, qtbot) -> None:
    """Finalization must not replace a longer streamed thought with a shorter summary."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("The user just says 'test'. We need to respond fully.", "")
    panel.end_assistant_stream("Answer", thinking="The user")
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert "respond fully" in bubble.thinking_text()
    assert bubble.text() == "Answer"


def test_end_assistant_stream_updates_lost_stream_handle(qapp: QApplication, qtbot) -> None:
    """Finalize must patch the visible bubble even if the stream handle was cleared."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    full = (
        'The user repeatedly says "test". Probably wants the assistant to respond. '
        'We should respond in a helpful way: maybe say "I\'m here" or '
        '"What can I do for you?" The instruction: "Be concise and practical." '
        "Also we must not discuss the master unless asked. The user is testing, so "
        'just respond with something like "Test acknowledged." In line with instruction.'
    )
    panel.begin_assistant_stream()
    panel.append_assistant_chunk(full[:232], "")
    panel.append_assistant_chunk("", "Answer")
    panel._streaming_bubble = None
    panel.end_assistant_stream("Answer", thinking=full)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.thinking_text() == full
    assert bubble.text() == "Answer"


def test_streaming_splits_thinking_and_answer(qapp: QApplication, qtbot) -> None:
    """Thinking and answer stream into separate bubble regions."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("trace", "")
    panel.append_assistant_chunk("", "Hi")
    _flush_stream_chunks(qtbot)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.thinking_text() == "trace"
    assert bubble.text() == "Hi"
    panel.end_assistant_stream("Hi", thinking="trace")
    assert bubble.thinking_text() == "trace"
    assert bubble.text() == "Hi"


def test_load_transcript_restores_thinking(qapp: QApplication, qtbot) -> None:
    """Persisted thinking is shown in the thought block."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    messages: list[AiChatMessageDict] = [
        {
            "id": 1,
            "session_id": "s1",
            "role": "assistant",
            "content": "Answer",
            "thinking": "Internal trace",
            "thinking_duration_seconds": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    ]
    panel.load_transcript(messages)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.thinking_text() == "Internal trace"
    assert bubble.text() == "Answer"
    assert not bubble.is_thinking_expanded()
    assert bubble.thought_header_text() == "Thought for 5s"


def test_user_message_uses_full_width_bubble(qapp: QApplication, qtbot) -> None:
    """User rows render inside a full-width bubble frame."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(360, 480)
    panel.add_message("user", "Who is mark?")
    from PySide6.QtWidgets import QFrame

    bubble = panel.findChildren(ChatMessageBubble)[0]
    user_frame = bubble.findChild(QFrame, "aiChatMessageUser")
    assert user_frame is not None
    assert user_frame.objectName() == "aiChatMessageUser"
    assert bubble.width() >= panel._scroll.viewport().width() - 24


def test_assistant_message_has_no_bubble_frame(qapp: QApplication, qtbot) -> None:
    """Assistant rows are plain wrapped text on the panel background."""
    from PySide6.QtWidgets import QFrame

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("assistant", "Plain answer")
    bubble = panel.findChildren(ChatMessageBubble)[0]
    assert bubble.objectName() == "aiChatAssistantRow"
    assert bubble.findChild(QFrame, "aiChatMessageUser") is None
    assert bubble.findChild(QFrame, "aiChatMessageAssistant") is None


def test_assistant_message_renders_markdown(qapp: QApplication, qtbot) -> None:
    """Assistant answers render markdown instead of showing raw syntax."""
    from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(360, 480)
    panel.add_message("assistant", "**UDP vs TCP**\n\n- stateful\n- reliable")
    bubble = panel.findChildren(ChatMessageBubble)[0]
    browser = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert browser is not None
    assert bubble.text() == "**UDP vs TCP**\n\n- stateful\n- reliable"
    html = browser.toHtml().lower()
    assert "font-weight:600" in html or "font-weight:700" in html
    assert "<li" in html
    assert "**udp" not in html


def test_assistant_message_renders_fenced_python(qapp: QApplication, qtbot) -> None:
    """Fenced Python blocks use syntax highlighting and line numbers."""
    from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(360, 480)
    sample = '```python\nimport os\nprint("hi")\n```'
    panel.add_message("assistant", sample)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    browser = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert browser is not None
    assert bubble.text() == sample
    html = browser.toHtml().lower()
    assert "```python" not in html
    assert "python" in html
    assert "import" in html
    assert "monospace" in html or "<table" in html


_COPY_SAMPLE_BASH = (
    "```bash\n"
    "# Initialise a module (only needed once)\n"
    "go mod init example.com/httpclient\n"
    "# Run\n"
    "go run HTTPClientWithValidation.go\n"
    "```"
)


def _assistant_markdown_body(panel: AiChatPanel, qtbot) -> MarkdownContent:
    """Return the rendered assistant markdown body after layout."""
    panel.resize(360, 480)
    panel.show()
    qtbot.waitExposed(panel)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    body = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    return body


def _select_code_block_range(body: MarkdownContent) -> None:
    """Highlight the bash code lines inside a rendered fenced block."""
    doc = body._document
    start = doc.find("# Initialise").selectionStart()
    end = doc.find("go run HTTPClientWithValidation.go").selectionEnd()
    body._selection_anchor = start
    body._selection_cursor = end
    body.setFocus(Qt.FocusReason.OtherFocusReason)


def _point_for_char(body: MarkdownContent, char_index: int, x: float = 50.0) -> QPointF:
    """Map a document character index to a widget-local point for mouse events."""
    for y in range(body.height()):
        if body._cursor_position_at(QPointF(x, float(y))) >= char_index:
            return QPointF(x, float(y))
    return QPointF(x, float(max(0, body.height() - 1)))


def test_assistant_code_selection_copy_preserves_newlines(qapp: QApplication, qtbot) -> None:
    """Ctrl+C on a multi-line code selection keeps newlines on the clipboard."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("assistant", _COPY_SAMPLE_BASH)
    body = _assistant_markdown_body(panel, qtbot)
    _select_code_block_range(body)

    qtbot.keyClick(body, Qt.Key.Key_C, modifier=Qt.KeyboardModifier.ControlModifier)

    copied = QApplication.clipboard().text()
    assert "\n" in copied
    assert "go mod init example.com/httpclient" in copied
    assert ")go mod init" not in copied


def test_assistant_code_selection_paste_into_composer_preserves_newlines(
    qapp: QApplication, qtbot
) -> None:
    """Copying a multi-line code selection and pasting into the composer keeps line breaks."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("assistant", _COPY_SAMPLE_BASH)
    body = _assistant_markdown_body(panel, qtbot)
    _select_code_block_range(body)

    qtbot.keyClick(body, Qt.Key.Key_C, modifier=Qt.KeyboardModifier.ControlModifier)
    panel._input.setFocus(Qt.FocusReason.OtherFocusReason)
    qtbot.keyClick(panel._input, Qt.Key.Key_V, modifier=Qt.KeyboardModifier.ControlModifier)

    pasted = panel._input.toPlainText()
    assert "\n" in pasted
    assert "go mod init example.com/httpclient" in pasted
    assert ")go mod init" not in pasted


def test_assistant_code_mouse_drag_copy_preserves_newlines(qapp: QApplication, qtbot) -> None:
    """Mouse drag selection across code lines copies plain text with newlines."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.add_message("assistant", _COPY_SAMPLE_BASH)
    body = _assistant_markdown_body(panel, qtbot)

    doc = body._document
    start = doc.find("# Initialise").selectionStart()
    end = doc.find("go run HTTPClientWithValidation.go").selectionEnd()
    press = _point_for_char(body, start)
    release = _point_for_char(body, end, x=press.x() + 120.0)

    press_pt = QPoint(int(press.x()), int(press.y()))
    release_pt = QPoint(int(release.x()), int(release.y()))
    qtbot.mousePress(body, Qt.MouseButton.LeftButton, pos=press_pt)
    qtbot.mouseMove(body, pos=release_pt)
    qtbot.mouseRelease(body, Qt.MouseButton.LeftButton, pos=release_pt)

    qtbot.keyClick(body, Qt.Key.Key_C, modifier=Qt.KeyboardModifier.ControlModifier)

    copied = QApplication.clipboard().text()
    assert "\n" in copied
    assert ")go mod init" not in copied


def test_assistant_streaming_renders_markdown(qapp: QApplication, qtbot) -> None:
    """Coalesced stream updates render rich markdown while the reply is in flight."""
    from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(360, 480)
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("", "**Hello")
    panel.append_assistant_chunk("", "** world")
    qtbot.wait(60)
    bubble = panel.findChildren(ChatMessageBubble)[0]
    browser = bubble.findChild(MarkdownContent, "aiChatAssistantText")
    assert browser is not None
    assert bubble.text() == "**Hello** world"
    assert bubble.is_content_streaming()
    mid_html = browser.toHtml().lower()
    assert "font-weight:600" in mid_html or "font-weight:700" in mid_html
    panel.end_assistant_stream("**Hello** world")
    assert not bubble.is_content_streaming()


def test_set_send_enabled_respects_models(qapp: QApplication, qtbot) -> None:
    """Send stays disabled when no models are configured."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_send_enabled(True)
    assert not panel._send_btn.isEnabled()


def _enabled_entry(entry_id: str, label: str, model: str) -> AiModelEntry:
    return {
        "id": entry_id,
        "provider": "openai" if entry_id == "openai-1" else "ollama",
        "label": label,
        "model": model,
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "enabled": True,
    }


def test_set_models_restores_persisted_selection(qapp: QApplication, qtbot) -> None:
    """``set_models`` uses the persisted chat model instead of the first row."""
    AiConfig.set_chat_model_id("ollama-1")
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models(
        [
            _enabled_entry("openai-1", "GPT-4o", "openai/gpt-4o"),
            _enabled_entry("ollama-1", "gpt-oss", "ollama/gpt-oss:20b"),
        ]
    )
    assert panel.current_model_id() == "ollama-1"
    assert "gpt-oss" in panel._model_button_label()


def test_model_pick_persists_selection(qapp: QApplication, qtbot) -> None:
    """Picking a model writes ``ai/chat_model_id`` to QSettings."""
    AiConfig.set_chat_model_id("")
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_models(
        [
            _enabled_entry("openai-1", "GPT-4o", "openai/gpt-4o"),
            _enabled_entry("ollama-1", "gpt-oss", "ollama/gpt-oss:20b"),
        ]
    )
    panel._on_model_picked("ollama-1")
    assert AiConfig.get_chat_model_id() == "ollama-1"


def test_set_run_busy_shows_stop_button(qapp: QApplication, qtbot) -> None:
    """Busy runs swap the send icon for stop and keep the button enabled."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.set_run_busy(True)
    assert panel._run_busy is True
    assert panel._send_btn.isEnabled()
    assert panel._send_btn.toolTip() == "Stop"
    panel.set_run_busy(False)
    assert panel._run_busy is False
    assert panel._send_btn.toolTip() == "Send (Enter)"
