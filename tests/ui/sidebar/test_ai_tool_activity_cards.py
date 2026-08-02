"""UI tests for main-agent tool activity cards."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy

from services.ai.chat.tool_activity_events import ToolActivityRecord
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.tool_activity.card import ToolActivityCard
from ui.sidebar.ai.message_bubble.tool_activity.group import ToolActivityGroup
from ui.widgets.busy_spinner import BrailleSpinner


def test_tool_activity_cards_render_and_hide_running_on_complete(
    qapp: QApplication,
    qtbot,
) -> None:
    """Running tool cards appear, then leave the layout when completed."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "running",
            }
        ]
    )
    cards = bubble.findChildren(ToolActivityCard)
    assert len(cards) == 1
    assert cards[0].status() == "running"
    detail = cards[0].findChild(QLabel, "aiChatToolActivityDetail")
    assert detail is not None
    assert detail.text() == "overview"
    # A running row opens the group to show live progress so the turn reads as alive.
    group = bubble._tool_activity_groups[0]
    assert group.is_expanded()
    assert group._row_visible(cards[0])
    assert cards[0].sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed

    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "completed",
            }
        ]
    )
    cards = bubble.findChildren(ToolActivityCard)
    assert len(cards) == 1
    assert cards[0].status() == "completed"

    bubble.set_tool_activity_records([])
    assert bubble._tool_activity_records == {}
    qtbot.wait(10)
    assert bubble.findChildren(ToolActivityCard) == []


def test_tool_activity_card_expands_full_output(qapp: QApplication, qtbot) -> None:
    """Terminal rows with observation output expand to readable, compact prose."""
    from PySide6.QtCore import Qt

    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.resize(420, 600)
    full_output = (
        "ok: false\n"
        "error: too_many_responses\n"
        "hint: Use at most 12 saved response examples per request.\n"
    )
    bubble.set_tool_activity_records(
        [
            {
                "id": "draft-1",
                "tool_name": "postmark_collection_draft",
                "title": "Build collection",
                "detail": "Failed: too_many_responses — trimmed",
                "status": "error",
                "output": full_output,
            }
        ]
    )
    card = bubble.findChildren(ToolActivityCard)[0]
    bubble.show()
    assert card.can_expand()
    assert not card._output_frame.isVisible()
    card._expand_btn.setChecked(True)
    qtbot.wait(10)
    assert card._output_frame.isVisible()
    shown = card._output.text()
    assert "Failed — Too many saved responses" in shown
    assert "Use at most 12 saved response examples per request." in shown
    assert "ok: false" not in shown
    # Short errors hug the text — no tall empty panel and no scrollbar.
    assert card._output_frame.height() < 100
    assert card._output_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_tool_activity_card_scrolls_long_output(qapp: QApplication, qtbot) -> None:
    """Long observation bodies scroll inside the bordered frame."""
    from PySide6.QtCore import Qt

    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.resize(420, 800)
    body = "\n".join(f"line {i}: " + ("x" * 40) for i in range(80))
    bubble.set_tool_activity_records(
        [
            {
                "id": "doc-1",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "chunk 3",
                "status": "completed",
                "output": f"ok: true\ndocument: spec.pdf\nchunk: 3 of 7\n\n{body}\n\nnext_step: continue\n",
            }
        ]
    )
    card = bubble.findChildren(ToolActivityCard)[0]
    group = bubble._tool_activity_groups[0]
    # Completed rows are hidden while the group summary is collapsed.
    group.set_expanded(True)
    bubble.show()
    card._expand_btn.setChecked(True)
    qtbot.wait(10)
    assert card.isVisible()
    assert card._output_frame.isVisible()
    assert "line 0:" in card._output.text()
    assert "line 79:" in card._output.text()
    assert card._output_frame.height() == 220
    assert card._output_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert card._output.height() > card._output_scroll.height()
    # Label width must reserve scrollbar space so wrapped height matches scroll range.
    assert card._output.width() < card._output_frame.width()
    bar = card._output_scroll.verticalScrollBar()
    assert bar.maximum() + card._output_scroll.viewport().height() >= card._output.height() - 1


def test_format_tool_activity_output_empty_batch() -> None:
    """Empty add_requests soft no-ops read as a note, not a failure."""
    from ui.sidebar.ai.message_bubble.tool_activity.format_output import (
        format_tool_activity_output,
    )

    text = format_tool_activity_output(
        "ok: true\nadded: []\nrequests: 1\nnote: No endpoints in this chunk — draft unchanged.\n"
    )
    assert "No endpoints in this chunk" in text
    assert "Failed" not in text
    assert "Added 0" not in text


def test_format_tool_activity_output_humanizes_errors() -> None:
    """Structured observation bodies become readable prose for the expand panel."""
    from ui.sidebar.ai.message_bubble.tool_activity.format_output import (
        format_tool_activity_output,
    )

    text = format_tool_activity_output(
        "ok: false\n"
        "error: bad_request\n"
        "hint: Request 1 (too_many_responses): 'Hotel Booking': use at most 12.\n"
    )
    assert text.startswith("Failed — Bad request")
    assert "Hotel Booking" in text
    assert "ok: false" not in text


def test_format_tool_activity_output_keeps_document_body() -> None:
    """Document-import chunks keep the freeform body under a short status header."""
    from ui.sidebar.ai.message_bubble.tool_activity.format_output import (
        format_tool_activity_output,
    )

    raw = (
        "ok: true\n"
        "document: Agoda.pdf\n"
        "uri: postmark://uploaded/Agoda.md\n"
        "chunk: 3 of 7\n"
        "pages: 10-14\n"
        "\n"
        '{"cancellationPolicy": {"policies": [{"type": "flexible"}]}}\n'
        "\n"
        "next_step: read chunk=4\n"
    )
    text = format_tool_activity_output(raw)
    assert text.startswith("Succeeded")
    assert "document: Agoda.pdf" in text
    assert "cancellationPolicy" in text
    assert "Next: read chunk=4" in text


def test_auto_executing_import_closes_thought_and_animates(
    qapp: QApplication,
    qtbot,
) -> None:
    """A LOW-risk SDK import alias shows a live card and closes prior thinking."""
    from ui.sidebar.ai import AiChatPanel

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.begin_assistant_stream()
    panel.append_assistant_chunk("Plan import.", "")
    panel.flush_pending_assistant_chunks()
    bubble = panel._streaming_bubble
    assert bubble is not None
    primary = bubble._thought_section
    assert primary is not None and primary.is_expanded()

    panel.deliver_tool_activity_update(
        [
            {
                "id": "sdk-import",
                "tool_name": "postmark_workspace_import",
                "title": "Import workspace",
                "detail": "OpenAPI-Hotel-BookingAPI-3.0.yaml",
                "status": "running",
            }
        ]
    )
    assert not primary.is_expanded()
    card = bubble.findChild(ToolActivityCard)
    spinner = card.findChild(BrailleSpinner) if card is not None else None
    assert card is not None and card.status() == "running"
    assert spinner is not None and not spinner.isHidden()
    frame = spinner.frame_index()
    qtbot.wait(120)
    assert spinner.frame_index() != frame

    panel.deliver_tool_activity_update(
        [
            {
                "id": "sdk-import",
                "tool_name": "postmark_workspace_import",
                "title": "Import workspace",
                "detail": "OpenAPI-Hotel-BookingAPI-3.0.yaml",
                "status": "completed",
            }
        ]
    )
    assert bubble.is_activity_visible()
    assert bubble.activity_message() == "Thinking…"
    group = bubble._tool_activity_groups[0]
    activity = bubble._activity_row
    outer = bubble._assistant_outer
    assert activity is not None and outer is not None
    assert outer.indexOf(group) < outer.indexOf(activity)
    panel.append_assistant_chunk("", "Imported.")
    panel.flush_pending_assistant_chunks()
    assert not bubble.is_activity_visible()
    panel.end_assistant_stream("Imported.", thinking="Plan import.")
    assert not primary.is_expanded()


def test_tool_group_sync_reorders_existing_cards(qapp: QApplication, qtbot) -> None:
    """A full-state refresh applies incoming record order to existing widgets."""
    group = ToolActivityGroup()
    qtbot.addWidget(group)
    first: ToolActivityRecord = {
        "id": "a",
        "tool_name": "postmark_workspace_query",
        "title": "First",
        "detail": "one",
        "status": "completed",
    }
    second: ToolActivityRecord = {
        "id": "b",
        "tool_name": "postmark_workspace_query",
        "title": "Second",
        "detail": "two",
        "status": "completed",
    }
    group.sync_records([first, second])
    group.sync_records([second, first])
    rows_layout = group.rows_widget().layout()
    assert rows_layout is not None
    widgets = [
        item.widget() if (item := rows_layout.itemAt(index)) is not None else None
        for index in range(rows_layout.count())
    ]
    assert widgets == [group._cards["b"], group._cards["a"]]


def _compact_card(qtbot, detail: str) -> ToolActivityCard:
    """Build an activated import card carrying *detail*."""
    card = ToolActivityCard()
    qtbot.addWidget(card)
    card.resize(370, 200)
    card.apply_record(
        {
            "id": "long-import",
            "tool_name": "postmark_workspace_import",
            "title": "Import workspace",
            "detail": detail,
            "status": "completed",
        }
    )
    layout = card.layout()
    assert layout is not None
    layout.activate()
    return card


def test_long_tool_detail_card_stays_compact(qapp: QApplication, qtbot) -> None:
    """Long import URLs stay on a single line without inflating the compact row.

    Bounds are expressed in the card's own font metrics: absolute pixel numbers
    differ between display backends and would make this assertion flaky.
    """
    detail = (
        "Import https://bitbucket.org/ApiPortalHotelbeds/apitude-openapi/raw/master/"
        "OpenAPI-Hotel-BookingAPI-3.0.yaml; append '11' to root name"
    )
    card = _compact_card(qtbot, detail)

    detail_line = card._detail.fontMetrics().lineSpacing()
    # The detail is clamped to a single line; the row height never grows with length.
    assert card._detail.maximumHeight() <= detail_line + 2

    ten_times_longer = _compact_card(qtbot, detail * 10)
    assert ten_times_longer.sizeHint().height() == card.sizeHint().height()
    assert card._detail.toolTip() == detail


def test_execute_handoff_removes_matching_tool_activity_card(
    qapp: QApplication,
    qtbot,
) -> None:
    """Execute result upsert clears the in-flight execute tool activity row."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "exec-1",
                "tool_name": "postmark_workspace_execute",
                "title": "Send request",
                "detail": "GET https://example.com",
                "status": "running",
            }
        ]
    )
    assert len(bubble.findChildren(ToolActivityCard)) == 1
    bubble.upsert_execute_record(
        {
            "id": "exec-1",
            "operation": "send_request",
            "label": "GET https://example.com -> 200",
            "status": "completed",
            "status_code": 200,
            "url": "https://example.com",
            "history_entry_id": 42,
            "request_id": 7,
            "local_script_id": None,
            "collection_id": None,
            "script_phase": None,
        }
    )
    assert bubble._tool_activity_records == {}
    qtbot.wait(10)
    assert bubble.findChildren(ToolActivityCard) == []


def test_post_tool_thinking_uses_new_block_below_cards(qapp: QApplication, qtbot) -> None:
    """After tool activity completes, synthesis thinking goes in a new block under cards."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Early planning only.")
    primary = bubble._thought_section
    assert primary is not None
    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "openapi.yaml",
                "status": "running",
            }
        ]
    )
    assert primary.duration_seconds() is not None
    assert not bubble._subagents_all_complete
    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "openapi.yaml",
                "status": "error",
            }
        ]
    )
    assert bubble._subagents_all_complete
    bubble.append_thinking("Synthesizing after import failure.")
    post = bubble._post_subagent_thought_section
    assert post is not None
    assert "Early planning only." in primary.text()
    assert "Synthesizing" in post.text()
    assert "Synthesizing" not in primary.text()
    outer = bubble._assistant_outer
    assert outer is not None
    assert outer.indexOf(bubble._tool_activity_group) < outer.indexOf(post)  # type: ignore[arg-type]
    assert outer.indexOf(post) < outer.indexOf(bubble._markdown_body)  # type: ignore[arg-type]


def test_frozen_primary_thought_stays_collapsed_during_tool_run(
    qapp: QApplication,
    qtbot,
) -> None:
    """Continued thinking while a tool runs must not re-open the frozen primary block."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Planning import.")
    primary = bubble._thought_section
    assert primary is not None
    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "openapi.yaml",
                "status": "running",
            }
        ]
    )
    assert primary.duration_seconds() is not None
    assert not primary.is_expanded()
    bubble.append_thinking(" continued deliberation while tool is still running")
    assert not primary.is_expanded()
    assert primary.duration_seconds() is not None


def test_pending_confirmation_closes_thinking_before_approval_card(
    qapp: QApplication,
    qtbot,
) -> None:
    """Approval chrome closes the current thought as soon as it interrupts reasoning."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Pre-tool planning.")
    primary = bubble._thought_section
    assert primary is not None
    bubble.show_pending_confirmation({"actions": [{"tool_call_id": "import-1"}]})
    bubble.set_tool_activity_records(
        [
            {
                "id": "import-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "openapi.yaml",
                "status": "running",
            }
        ]
    )
    assert primary.duration_seconds() is not None
    assert not primary.is_expanded()
    bubble.clear_pending_confirmation()
    assert primary.duration_seconds() is not None


def test_multiple_tool_cycles_keep_strict_chronological_order(
    qapp: QApplication,
    qtbot,
) -> None:
    """Each thought/tool cycle appends below the preceding cycle."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()

    bubble.append_thinking("Plan first tool.")
    first_thought = bubble._thought_section
    assert first_thought is not None
    bubble.show_pending_confirmation({"actions": [{"tool_call_id": "tool-1"}]})
    assert first_thought.duration_seconds() is not None
    bubble.set_tool_activity_records(
        [
            {
                "id": "tool-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "first.yaml",
                "status": "running",
            }
        ]
    )
    bubble.clear_pending_confirmation()
    bubble.set_tool_activity_records(
        [
            {
                "id": "tool-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "first.yaml",
                "status": "completed",
            }
        ]
    )
    bubble.append_thinking("Evaluate first result.")
    second_thought = bubble._active_thought_section_ref
    assert second_thought is not None

    bubble.show_pending_confirmation({"actions": [{"tool_call_id": "tool-2"}]})
    assert second_thought.duration_seconds() is not None
    bubble.set_tool_activity_records(
        [
            {
                "id": "tool-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "first.yaml",
                "status": "completed",
            },
            {
                "id": "tool-2",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "running",
            },
        ]
    )
    bubble.clear_pending_confirmation()
    bubble.set_tool_activity_records(
        [
            {
                "id": "tool-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "first.yaml",
                "status": "completed",
            },
            {
                "id": "tool-2",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "completed",
            },
        ]
    )
    bubble.append_thinking("Evaluate second result.")
    third_thought = bubble._active_thought_section_ref
    assert third_thought is not None

    outer = bubble._assistant_outer
    assert outer is not None
    first_group, second_group = bubble._tool_activity_groups
    assert outer.indexOf(first_thought) < outer.indexOf(first_group)
    assert outer.indexOf(first_group) < outer.indexOf(second_thought)
    assert outer.indexOf(second_thought) < outer.indexOf(second_group)
    assert outer.indexOf(second_group) < outer.indexOf(third_thought)


def test_clear_tool_activity_cards_resets_thinking_phase(qapp: QApplication, qtbot) -> None:
    """Clearing tool cards resets phase state for a fresh interrupt cycle."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("First phase.")
    bubble.set_tool_activity_records(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "completed",
            }
        ]
    )
    bubble.append_thinking("Second phase.")
    assert bubble._post_subagent_thought_section is not None
    bubble.clear_tool_activity_cards()
    assert bubble._tool_activity_records == {}
    assert not bubble._subagents_all_complete
    assert bubble._post_subagent_thought_section is None
    bubble.append_thinking("After clear.")
    assert bubble._post_subagent_thought_section is None
    assert "After clear." in bubble._thought_section.text()  # type: ignore[union-attr]


def test_begin_assistant_stream_clears_tool_activity_cards(qapp: QApplication, qtbot) -> None:
    """A new assistant stream starts without stale tool activity cards."""
    from ui.sidebar.ai import AiChatPanel

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.begin_assistant_stream()
    panel.deliver_tool_activity_update(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "openapi.yaml",
                "status": "running",
            }
        ]
    )
    qtbot.wait(10)
    bubble = panel._streaming_bubble
    assert bubble is not None
    assert len(bubble.findChildren(ToolActivityCard)) == 1
    panel.begin_assistant_stream()
    qtbot.wait(10)
    bubble = panel._streaming_bubble
    assert bubble is not None
    assert bubble._tool_activity_records == {}
    assert bubble.findChildren(ToolActivityCard) == []


def test_coalesce_flush_routes_post_tool_thinking_to_second_block(
    qapp: QApplication,
    qtbot,
) -> None:
    """Thinking flushed after a completed tool routes to the post-interrupt block."""
    from ui.sidebar.ai import AiChatPanel

    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.begin_assistant_stream()
    bubble = panel._streaming_bubble
    assert bubble is not None
    bubble.append_thinking("Pre-tool planning.")
    panel.deliver_tool_activity_update(
        [
            {
                "id": "tc-1",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "openapi.yaml",
                "status": "completed",
            }
        ]
    )
    panel.append_assistant_chunk("Post-tool synthesis.", "")
    panel._flush_pending_chunks()
    qtbot.wait(10)
    post = bubble._post_subagent_thought_section
    assert post is not None
    assert "Post-tool synthesis." in post.text()
    assert "Post-tool synthesis." not in bubble._thought_section.text()  # type: ignore[union-attr]


def test_restored_tool_cycles_interleave_persisted_thought_sections(
    qapp: QApplication,
    qtbot,
) -> None:
    """Reloaded contiguous tool records collapse into one group, chronology intact."""
    bubble = ChatMessageBubble("assistant", "", thinking="Plan first tool.")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "restore-tool-1",
                "tool_name": "postmark_workspace_query",
                "title": "Query workspace",
                "detail": "overview",
                "status": "completed",
            },
            {
                "id": "restore-tool-2",
                "tool_name": "postmark_import",
                "title": "Import workspace",
                "detail": "api.yaml",
                "status": "completed",
            },
        ]
    )
    # A contiguous run (no thought between the two calls) is one collapsed group.
    assert len(bubble._tool_activity_groups) == 1
    group = bubble._tool_activity_groups[0]
    assert set(group._cards) == {"restore-tool-1", "restore-tool-2"}

    bubble.restore_additional_thinking_sections(["Inspect first result."])
    first_thought, second_thought = bubble._thought_sections
    outer = bubble._assistant_outer
    assert outer is not None
    assert outer.indexOf(first_thought) < outer.indexOf(group)
    assert outer.indexOf(group) < outer.indexOf(second_thought)


def test_document_import_card_uses_file_text_icon(qapp: QApplication, qtbot) -> None:
    """Document import tool cards show the file-text icon and title."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "doc-1",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "Read messy-api.pdf",
                "status": "completed",
            }
        ]
    )
    cards = bubble.findChildren(ToolActivityCard)
    assert len(cards) == 1
    title = cards[0].findChild(QLabel, "aiChatToolActivityTitle")
    assert title is not None
    assert title.text() == "Read document"
    assert cards[0]._title_icon.pixmap() is not None  # type: ignore[attr-defined]


def test_every_tool_icon_name_exists_in_the_icon_font(qapp: QApplication) -> None:
    """A misspelled glyph name renders an empty square, which is easy to miss."""
    from ui.styling import icons
    from ui.sidebar.ai.message_bubble.tool_activity.card import _TOOL_ICONS

    icons.phi("file-text")
    missing = [name for name in _TOOL_ICONS.values() if name not in icons._charmap]
    assert missing == []


def test_collection_draft_card_uses_its_own_icon_and_title(qapp: QApplication, qtbot) -> None:
    """Building a collection is a distinct step and must read as one."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.set_tool_activity_records(
        [
            {
                "id": "draft-1",
                "tool_name": "postmark_collection_draft",
                "title": "Build collection",
                "detail": "Add POST booking",
                "status": "completed",
            }
        ]
    )
    cards = bubble.findChildren(ToolActivityCard)
    assert len(cards) == 1
    title = cards[0].findChild(QLabel, "aiChatToolActivityTitle")
    assert title is not None
    assert title.text() == "Build collection"


def _group_with_records(qtbot, records: list[dict[str, object]]) -> ToolActivityGroup:
    """Build a group synced with *records*."""
    group = ToolActivityGroup()
    qtbot.addWidget(group)
    group.sync_records(records)  # type: ignore[arg-type]
    return group


def _timing_records() -> list[dict[str, object]]:
    """Return three completed records with known start/completion times."""
    return [
        {
            "id": "a",
            "tool_name": "postmark_workspace_query",
            "title": "Query A",
            "detail": "one",
            "status": "completed",
            "started_at": 100.0,
            "completed_at": 101.2,
        },
        {
            "id": "b",
            "tool_name": "postmark_document_import",
            "title": "Read document",
            "detail": "chunk 1",
            "status": "completed",
            "started_at": 101.2,
            "completed_at": 102.4,
        },
        {
            "id": "c",
            "tool_name": "postmark_collection_draft",
            "title": "Add requests",
            "detail": "3 endpoints",
            "status": "completed",
            "started_at": 102.4,
            "completed_at": 103.0,
        },
    ]


def test_group_collapses_to_a_summary_line(qapp: QApplication, qtbot) -> None:
    """Adjacent tool calls collapse into one summary row that hides their detail."""
    group = _group_with_records(qtbot, _timing_records())
    assert not group.is_expanded()
    summary = group.header().findChild(QLabel, "aiChatToolActivityGroupSummary")
    assert summary is not None
    assert summary.text() == "3 tool calls"
    # Collapsed: completed rows are hidden; the summary carries the glanceable state.
    for card in group._cards.values():
        assert not group._row_visible(card)


def test_group_summary_shows_total_duration(qapp: QApplication, qtbot) -> None:
    """The collapsed summary carries the real elapsed time across the run."""
    group = _group_with_records(qtbot, _timing_records())
    timing = group.header().findChild(QLabel, "aiChatToolActivityGroupTiming")
    assert timing is not None
    assert timing.text() == "3.0s"  # 1.2 + 1.2 + 0.6


def test_expanding_the_group_reveals_rows(qapp: QApplication, qtbot) -> None:
    """Toggling the header shows every row; collapsing hides them again."""
    group = _group_with_records(qtbot, _timing_records())
    group.set_expanded(True)
    for card in group._cards.values():
        assert group._row_visible(card)
    assert group.is_expanded()
    group.set_expanded(False)
    assert not group.is_expanded()
    for card in group._cards.values():
        assert not group._row_visible(card)


def test_failed_rows_stay_visible_when_collapsed(qapp: QApplication, qtbot) -> None:
    """A failed call must not be hidden behind a collapsed summary."""
    records = _timing_records()
    records[1]["status"] = "error"
    group = _group_with_records(qtbot, records)
    assert not group.is_expanded()
    assert group._row_visible(group._cards["b"])
    assert not group._row_visible(group._cards["a"])
    summary = group.header().findChild(QLabel, "aiChatToolActivityGroupSummary")
    assert summary is not None
    assert "1 failed" in summary.text()


def test_group_auto_expands_while_running_then_collapses_on_done(qapp: QApplication, qtbot) -> None:
    """A group opens to show live progress, then folds back to the summary when done."""
    records = _timing_records()
    records[2]["status"] = "running"
    group = _group_with_records(qtbot, records)
    assert group.is_expanded()  # auto-expanded while a row is running
    records[2]["status"] = "completed"
    group.sync_records(records)  # type: ignore[arg-type]
    assert not group.is_expanded()  # auto-collapsed once the run is terminal


def test_manually_expanded_group_stays_open_after_completion(qapp: QApplication, qtbot) -> None:
    """A user's own choice to open the group wins over auto-collapse."""
    records = _timing_records()
    records[2]["status"] = "running"
    group = _group_with_records(qtbot, records)
    group.on_header_toggled(True)
    assert group.is_expanded()
    records[2]["status"] = "completed"
    group.sync_records(records)  # type: ignore[arg-type]
    assert group.is_expanded()


def test_contiguous_live_run_batches_into_one_group(qapp: QApplication, qtbot) -> None:
    """Adjacent tool calls in a run collapse into one collapsible group, not a wall of boxes."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Plan import.")
    bubble.set_tool_activity_records(
        [
            {
                "id": "t1",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "chunk 1",
                "status": "running",
            }
        ]
    )
    bubble.set_tool_activity_records(
        [
            {
                "id": "t1",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "chunk 1",
                "status": "completed",
            },
            {
                "id": "t2",
                "tool_name": "postmark_collection_draft",
                "title": "Start draft",
                "detail": "Agoda",
                "status": "running",
            },
        ]
    )
    # Both calls in the same contiguous run share one group (auto-open while running).
    assert len(bubble._tool_activity_groups) == 1
    group = bubble._tool_activity_groups[0]
    assert set(group._cards) == {"t1", "t2"}


def test_thought_between_calls_starts_a_new_group(qapp: QApplication, qtbot) -> None:
    """A new thought phase between tool calls keeps each cycle in its own group."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    bubble.show()
    bubble.append_thinking("Plan first tool.")
    bubble.set_tool_activity_records(
        [
            {
                "id": "t1",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "chunk 1",
                "status": "completed",
            }
        ]
    )
    bubble.append_thinking("Evaluate first chunk.")
    bubble.set_tool_activity_records(
        [
            {
                "id": "t1",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "chunk 1",
                "status": "completed",
            },
            {
                "id": "t2",
                "tool_name": "postmark_document_import",
                "title": "Read document",
                "detail": "chunk 2",
                "status": "completed",
            },
        ]
    )
    assert len(bubble._tool_activity_groups) == 2


def test_reload_collapses_contiguous_records_into_one_group(qapp: QApplication, qtbot) -> None:
    """Transcript reload collapses a contiguous run of tool calls into one group.

    A restored run must match the live-streaming layout: contiguous tool calls share
    one collapsed group, and only a restored thought phase between two calls starts
    a fresh group so each thought/tool cycle stays in chronological order.
    """
    bubble = ChatMessageBubble("assistant", "", thinking="Plan.")
    qtbot.addWidget(bubble)
    bubble.upsert_tool_activity_record(
        {
            "id": "r1",
            "tool_name": "postmark_workspace_query",
            "title": "Query",
            "detail": "a",
            "status": "completed",
        }
    )
    bubble.upsert_tool_activity_record(
        {
            "id": "r2",
            "tool_name": "postmark_import",
            "title": "Import",
            "detail": "b",
            "status": "completed",
        }
    )
    # A contiguous run (no thought between the two calls) is one collapsed group.
    assert len(bubble._tool_activity_groups) == 1
    assert set(bubble._tool_activity_groups[0]._cards) == {"r1", "r2"}

    # A restored thought phase between cycles starts a new group for later calls.
    bubble.append_thinking("Evaluate first result.")
    bubble.upsert_tool_activity_record(
        {
            "id": "r3",
            "tool_name": "postmark_workspace_query",
            "title": "Query",
            "detail": "c",
            "status": "completed",
        }
    )
    assert len(bubble._tool_activity_groups) == 2
    assert set(bubble._tool_activity_groups[1]._cards) == {"r3"}
