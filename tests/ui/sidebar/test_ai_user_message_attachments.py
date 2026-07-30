"""User transcript bubbles render uploaded files as chips, not a URI dump."""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas
from PySide6.QtWidgets import QApplication, QLabel

from services.ai.chat.attachments.store import store_attachments
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.sidebar.ai.message_bubble.user_message.attachments import (
    AttachmentMarkdownDialog,
    UserMessageAttachmentRow,
    format_attachment_size,
)
from ui.sidebar.ai.message_bubble.user_message.attachments.row import _AttachmentChip

_PROMPT = "Import this API.\n\nAttached files:\n- spec.pdf -> postmark://uploaded/spec.md"


def _chip_names(bubble: ChatMessageBubble) -> list[str]:
    return [label.text() for label in bubble.findChildren(QLabel, "aiChatUserAttachmentChipName")]


def test_attachment_trailer_renders_as_chips_above_the_prompt(
    qapp: QApplication,
    qtbot,
) -> None:
    """The label shows only the prompt; the trailer becomes a chip row."""
    bubble = ChatMessageBubble("user", _PROMPT)
    qtbot.addWidget(bubble)

    label = bubble.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.text() == "Import this API."

    row = bubble.findChild(UserMessageAttachmentRow)
    assert row is not None
    assert not row.isHidden()
    assert _chip_names(bubble) == ["spec.pdf"]
    # No internal URI leaks into the visible transcript.
    assert not bubble.findChildren(QLabel, "aiChatUserMessageText")[0].text().count("postmark://")


def test_full_prompt_still_available_for_edit_and_fork(qapp: QApplication, qtbot) -> None:
    """Edit/fork must round-trip the attachment trailer with the prompt."""
    bubble = ChatMessageBubble("user", _PROMPT)
    qtbot.addWidget(bubble)
    assert bubble.user_message_text() == _PROMPT


def test_attachment_only_message_hides_the_empty_label(qapp: QApplication, qtbot) -> None:
    """A send with no typed text shows chips without a blank prose block."""
    prompt = "Attached files:\n- a.pdf -> postmark://uploaded/a.md"
    bubble = ChatMessageBubble("user", prompt)
    qtbot.addWidget(bubble)

    assert _chip_names(bubble) == ["a.pdf"]
    label = bubble.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.text() == ""
    host = label.parentWidget()
    assert host is not None
    assert label.isHidden() or not host.isVisibleTo(bubble)


def test_message_without_attachments_keeps_the_row_hidden(qapp: QApplication, qtbot) -> None:
    """Plain prompts render exactly as before — no chip row, no divider."""
    bubble = ChatMessageBubble("user", "no files here")
    qtbot.addWidget(bubble)

    row = bubble.findChild(UserMessageAttachmentRow)
    assert row is not None
    assert row.isHidden()
    label = bubble.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.text() == "no files here"


def test_chip_shows_size_when_known(qapp: QApplication, qtbot) -> None:
    """Sizes arrive keyed by the uploaded URI the trailer references."""
    bubble = ChatMessageBubble(
        "user",
        _PROMPT,
        attachment_sizes={"postmark://uploaded/spec.md": 2_500_000},
    )
    qtbot.addWidget(bubble)

    sizes = bubble.findChildren(QLabel, "aiChatUserAttachmentChipSize")
    assert [label.text() for label in sizes] == ["2.5 MB"]


def test_multiple_attachments_render_in_upload_order(qapp: QApplication, qtbot) -> None:
    """A multi-file send shows one chip per upload in trailer order."""
    prompt = (
        "read these\n\nAttached files:\n"
        "- one.pdf -> postmark://uploaded/one.md\n"
        "- two.docx -> postmark://uploaded/two.md"
    )
    bubble = ChatMessageBubble("user", prompt)
    qtbot.addWidget(bubble)
    assert _chip_names(bubble) == ["one.pdf", "two.docx"]


def test_legacy_path_trailer_shows_the_basename(qapp: QApplication, qtbot) -> None:
    """Old transcripts carried absolute paths; the chip shows the file name."""
    prompt = "old turn\n\nAttached files (absolute paths):\n- /home/marik/Downloads/legacy.pdf"
    bubble = ChatMessageBubble("user", prompt)
    qtbot.addWidget(bubble)
    assert _chip_names(bubble) == ["legacy.pdf"]


def test_handle_era_trailer_hides_the_doc_prefix(qapp: QApplication, qtbot) -> None:
    """The ``doc:1`` era must not leak its handle into the chip label."""
    prompt = "read it\n\nAttached files:\n- doc:1 swagger-petstore.pdf"
    bubble = ChatMessageBubble("user", prompt)
    qtbot.addWidget(bubble)
    assert _chip_names(bubble) == ["swagger-petstore.pdf"]


def test_resaved_trailer_with_nbsp_still_renders_as_chips(qapp: QApplication, qtbot) -> None:
    """Transcripts re-saved with non-breaking spaces must not fall back to raw text."""
    prompt = (
        "How about no? Read the file fully\n\nAttached files:\u00a0\n"
        "-\u00a0Swagger-Petstore (1).pdf\u00a0->\u00a0postmark://uploaded/Swagger-Petstore_1.md"
    )
    bubble = ChatMessageBubble("user", prompt)
    qtbot.addWidget(bubble)
    assert _chip_names(bubble) == ["Swagger-Petstore (1).pdf"]
    label = bubble.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.text() == "How about no? Read the file fully"


def test_editing_the_text_refreshes_the_chips(qapp: QApplication, qtbot) -> None:
    """set_user_message_text re-parses the trailer so chips track the prompt."""
    bubble = ChatMessageBubble("user", _PROMPT)
    qtbot.addWidget(bubble)
    bubble.set_user_message_text("plain now")
    row = bubble.findChild(UserMessageAttachmentRow)
    assert row is not None
    assert row.isHidden()
    label = bubble.findChild(QLabel, "aiChatUserMessageText")
    assert label is not None
    assert label.text() == "plain now"


def test_format_attachment_size_boundaries() -> None:
    """Chip sizes stay short: bytes, whole KB, one-decimal MB."""
    assert format_attachment_size(512) == "512 B"
    assert format_attachment_size(2048) == "2 KB"
    assert format_attachment_size(2_500_000) == "2.5 MB"


def test_row_height_reserves_space_for_the_chip_row(qapp: QApplication, qtbot) -> None:
    """The fixed row height must include the chip row above the prompt.

    Regression: the chrome height omitted the attachment row, so
    ``sync_user_message_height_constraint`` clamped the bubble too short and the
    chip row's hairline divider overlapped/clipped the prompt text below it.
    """
    body = "Turn this pdf into a collection please"
    with_att = f"{body}\n\nAttached files:\n- spec.pdf -> postmark://uploaded/spec.md"

    bubble_att = ChatMessageBubble("user", with_att)
    qtbot.addWidget(bubble_att)
    bubble_plain = ChatMessageBubble("user", body)
    qtbot.addWidget(bubble_plain)

    row = bubble_att.findChild(UserMessageAttachmentRow)
    assert row is not None
    assert not row.isHidden()
    chip_height = row.sizeHint().height()
    assert chip_height > 0

    hint_att = bubble_att._user_message_layout_hint().height()
    hint_plain = bubble_plain._user_message_layout_hint().height()

    # The attached row must be taller by at least the chip row height.
    assert hint_att >= hint_plain + chip_height


def test_chip_click_propagates_reference_to_the_bubble(qapp: QApplication, qtbot) -> None:
    """The chip signal chain surfaces the attachment reference on the bubble."""
    bubble = ChatMessageBubble("user", _PROMPT)
    qtbot.addWidget(bubble)

    received: list[str] = []
    bubble.attachment_clicked.connect(received.append)

    chips = bubble.findChildren(_AttachmentChip)
    assert len(chips) == 1
    chips[0].clicked.emit("postmark://uploaded/spec.md")
    assert received == ["postmark://uploaded/spec.md"]


def test_clicking_a_chip_opens_the_markdown_dialog(
    qapp: QApplication, qtbot, tmp_path: Path
) -> None:
    """A chip click resolves the stored attachment and shows its Markdown."""
    pdf = tmp_path / "spec.pdf"
    pdf_canvas = canvas.Canvas(str(pdf))
    pdf_canvas.drawString(72, 720, "GET /hotels returns availability")
    pdf_canvas.showPage()
    pdf_canvas.save()

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    session_id = "11111111-1111-4111-8111-111111111111"
    panel._context_session_id = session_id
    store_attachments(session_id, [str(pdf)])

    prompt = (
        "Turn this pdf into a collection please\n\n"
        "Attached files:\n- spec.pdf -> postmark://uploaded/spec.md"
    )
    panel.add_message("user", prompt)
    bubble = panel.findChildren(ChatMessageBubble)[0]

    chips = bubble.findChildren(_AttachmentChip)
    assert len(chips) == 1
    chips[0].clicked.emit("postmark://uploaded/spec.md")
    qtbot.wait(30)

    dialog = panel._attachment_markdown_dialog
    assert isinstance(dialog, AttachmentMarkdownDialog)
    assert dialog.windowTitle() == "spec.pdf"
    body = dialog.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    assert "GET /hotels returns availability" in body.markdown()


def test_attachment_markdown_dialog_renders_stored_markdown(qapp: QApplication, qtbot) -> None:
    """The viewer titles itself after the file and renders its Markdown body."""
    dialog = AttachmentMarkdownDialog()
    qtbot.addWidget(dialog)

    dialog.open_attachment("spec.pdf", "# Title\n\nbody text")
    assert dialog.windowTitle() == "spec.pdf"
    body = dialog.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    assert body.markdown() == "# Title\n\nbody text"


def test_attachment_markdown_dialog_handles_missing_markdown(qapp: QApplication, qtbot) -> None:
    """An upload that produced no Markdown shows a notice instead of a blank pane."""
    dialog = AttachmentMarkdownDialog()
    qtbot.addWidget(dialog)

    dialog.open_attachment("empty.pdf", "")
    body = dialog.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    assert "No Markdown" in body.markdown()


def test_attachment_dialog_pins_body_width_to_the_viewport(qapp: QApplication, qtbot) -> None:
    """The markdown body is sized to the scroll viewport so it actually renders.

    Regression: with a non-resizable scroll area the body started at width 0, so
    ``MarkdownContent`` laid its document out at zero width and the window read
    as blank. The sync must pin the body to the viewport width and re-render.
    """
    dialog = AttachmentMarkdownDialog()
    qtbot.addWidget(dialog)
    dialog.open_attachment("spec.pdf", "# Title\n\nbody text")

    viewport = dialog._scroll.viewport()
    assert viewport is not None
    viewport.setFixedWidth(600)
    dialog._sync_body_layout()

    body = dialog.findChild(MarkdownContent, "aiChatAssistantText")
    assert body is not None
    assert body.width() == 600
    assert body.height() > 0


def test_attachment_dialog_reuses_assistant_markdown_widget(qapp: QApplication, qtbot) -> None:
    """The viewer must host the same ``aiChatAssistantText`` MarkdownContent as replies.

    Overriding the objectName broke shared QSS and made the attachment pane a
    parallel renderer; keep the stock widget identity so paint/layout match the
    subagent detail reply pane.
    """
    dialog = AttachmentMarkdownDialog()
    qtbot.addWidget(dialog)
    assert dialog._body.objectName() == "aiChatAssistantText"


def test_markdown_content_paint_clears_exposed_region(qapp: QApplication, qtbot) -> None:
    """Opaque paint must fill the clip rect so partial updates never stack text.

    Regression: tall documents in a dialog scrolled with ``WA_OpaquePaintEvent``
    set but no background fill, so each partial paint stacked white glyphs onto
    black uninitialized pixels — the mangled attachment-viewer look.
    """
    from PySide6.QtGui import QColor

    from ui.styling.theme import current_palette

    # Empty body so a corner pixel is pure background, not antialiased text.
    body = MarkdownContent("")
    qtbot.addWidget(body)
    body.resize(400, 200)
    body.show()
    qtbot.waitExposed(body)
    qtbot.wait(10)

    pixmap = body.grab()
    sample = pixmap.toImage().pixelColor(2, 2)
    expected = QColor(current_palette()["bg"])
    assert sample == expected, f"paint left unfilled pixel {sample.name()} (bg={expected.name()})"
