"""Tests for assistant message footer and actions."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


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


def test_assistant_footer_visible_when_complete(qapp: QApplication) -> None:
    """Completed assistant rows always show the footer."""
    bubble = ChatMessageBubble("assistant", "Hello **world**")
    bubble.set_usage_metadata(
        model_id="m1",
        prompt_tokens=10,
        completion_tokens=5,
        entry=_entry(),
    )
    footer = bubble._assistant_footer
    assert footer is not None
    assert not footer.isHidden()
    assert "GPT-4o" in footer._usage_label.text()


def test_assistant_footer_hidden_during_streaming(qapp: QApplication) -> None:
    """Streaming assistant rows hide the footer until the turn completes."""
    bubble = ChatMessageBubble("assistant", "")
    bubble.begin_streaming()
    bubble.set_usage_metadata(model_id="m1", prompt_tokens=1, completion_tokens=1, entry=_entry())
    footer = bubble._assistant_footer
    body = bubble._markdown_body
    assert footer is not None
    assert body is not None
    assert footer.isHidden()
    assert not body._paint_footer_rule


def test_assistant_footer_hidden_while_activity_visible(qapp: QApplication) -> None:
    """Activity rows keep the footer hidden until the turn completes."""
    bubble = ChatMessageBubble("assistant", "Done")
    bubble.show_activity("Thinking…")
    bubble.set_usage_metadata(model_id="m1", prompt_tokens=1, completion_tokens=1, entry=_entry())
    footer = bubble._assistant_footer
    assert footer is not None
    assert footer.isHidden()


def _table_tail_markdown() -> str:
    """Long assistant body with a table and a distinctive em-dash tail clause."""
    return (
        "| OS | Notes |\n| --- | --- |\n| macOS | Unix-like |\n| Windows | Broad apps |\n\n"
        + ("Opening paragraph with enough text to wrap at narrow widths. " * 12)
        + "\n\nFinal paragraph about primary target platform—and the rest of this "
        "sentence must remain visible above the footer."
    )


def _last_block_bottom_y(body: MarkdownContent) -> float:
    """Return the bottom edge of the last non-empty document block in body coords."""
    document = body.document()
    layout = document.documentLayout()
    block = document.lastBlock()
    while block.isValid() and not block.text().strip():
        block = block.previous()
    if not block.isValid():
        return 0.0
    return layout.blockBoundingRect(block).bottom()


def test_assistant_footer_rule_below_message_content(qapp: QApplication, qtbot) -> None:
    """The dashed rule is painted below the markdown body, metadata row below that."""
    bubble = ChatMessageBubble("assistant", _table_tail_markdown())
    bubble.set_usage_metadata(
        model_id="m1",
        prompt_tokens=100,
        completion_tokens=50,
        entry=_entry(),
    )
    qtbot.addWidget(bubble)
    bubble.resize(360, 1200)
    bubble.show()
    qtbot.waitExposed(bubble)
    qapp.processEvents()

    body = bubble._markdown_body
    footer = bubble._assistant_footer
    assert body is not None
    assert footer is not None
    assert body._paint_footer_rule

    content_bottom = body.mapTo(bubble, QPoint(0, body._painted_content_height_px)).y()
    footer_top = footer.mapTo(bubble, QPoint(0, 0)).y()
    assert footer_top >= content_bottom

    tail_bottom = _last_block_bottom_y(body)
    assert tail_bottom <= float(body._painted_content_height_px)


def test_assistant_footer_tail_text_visible_above_rule(
    qapp: QApplication,
    qtbot,
) -> None:
    """The em-dash tail clause sits above the painted dashed rule."""
    bubble = ChatMessageBubble("assistant", _table_tail_markdown())
    bubble.set_usage_metadata(
        model_id="m1",
        prompt_tokens=10,
        completion_tokens=5,
        entry=_entry(),
    )
    qtbot.addWidget(bubble)
    bubble.resize(360, 1200)
    bubble.show()
    qtbot.waitExposed(bubble)
    qapp.processEvents()

    body = bubble._markdown_body
    assert body is not None
    assert body._paint_footer_rule

    document = body.document()
    tail_phrase = "sentence must remain visible"
    found = document.toPlainText().rfind(tail_phrase)
    assert found >= 0
    cursor = QTextCursor(document)
    cursor.setPosition(found + len(tail_phrase) - 1)
    layout = document.documentLayout()
    hit_y = layout.blockBoundingRect(cursor.block()).bottom()
    assert hit_y <= float(body._painted_content_height_px)


def test_assistant_menu_button_uses_hand_cursor(qapp: QApplication) -> None:
    """The three-dot menu button advertises clickability."""
    bubble = ChatMessageBubble("assistant", "Hi")
    footer = bubble._assistant_footer
    assert footer is not None
    assert footer.menu_button().cursor().shape() == Qt.CursorShape.PointingHandCursor
