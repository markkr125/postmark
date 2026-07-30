"""Tests for composing prompt text from composer attachments."""

from __future__ import annotations

from pathlib import Path

from ui.sidebar.ai.chat_panel.composer.attachments import (
    ATTACHMENT_HEADER,
    LEGACY_ATTACHMENT_HEADER,
    attachment_references_from_prompt,
    attachment_sizes_from_session,
    attachment_sizes_from_sources,
    compose_prompt_with_attachments,
    split_prompt_attachments,
)

_LONG_PATH = "/home/marik/Downloads/Agoda Standard Pull Spec v1.34 (5) (3).pdf"


def test_no_attachments_leaves_text_untouched() -> None:
    """Plain messages are forwarded verbatim."""
    assert compose_prompt_with_attachments("hello", []) == "hello"


def test_attachments_reach_the_agent_by_uploaded_uri() -> None:
    """The agent identifies the document by URI, keeping its real name visible."""
    prompt = compose_prompt_with_attachments(
        "Can you turn this PDF into a collection?", [_LONG_PATH]
    )
    assert prompt.startswith("Can you turn this PDF into a collection?")
    assert ATTACHMENT_HEADER in prompt
    assert "Agoda Standard Pull Spec v1.34 (5) (3).pdf" in prompt
    assert "postmark://uploaded/Agoda_Standard_Pull_Spec_v1.34_5_3.md" in prompt


def test_uploaded_uri_has_no_characters_that_break_a_reference() -> None:
    """Spaces and brackets would make the end of the URI ambiguous in prose."""
    prompt = compose_prompt_with_attachments("read it", [_LONG_PATH])
    uri = next(line for line in prompt.splitlines() if "postmark://uploaded/" in line)
    document = uri.split("postmark://uploaded/", 1)[1]
    assert document.endswith(".md")
    assert not any(char in document for char in " ()[]'\"")


def test_absolute_path_is_withheld() -> None:
    """The path is persisted in the transcript and sent to the provider.

    It is also the value models truncate when asked to repeat it as a tool
    argument, which previously failed the whole run.
    """
    prompt = compose_prompt_with_attachments("read it", [_LONG_PATH])
    assert "/home/marik/Downloads" not in prompt


def test_multiple_attachments_get_distinct_uris() -> None:
    """Each attachment needs its own reference so the model can pick one."""
    prompt = compose_prompt_with_attachments("read these", ["/a/one.pdf", "/b/two.docx"])
    assert prompt.splitlines()[-2:] == [
        "- one.pdf -> postmark://uploaded/one.md",
        "- two.docx -> postmark://uploaded/two.md",
    ]
    assert attachment_references_from_prompt(prompt) == [
        "postmark://uploaded/one.md",
        "postmark://uploaded/two.md",
    ]


def test_attachment_only_message_still_names_the_document() -> None:
    """Sending an attachment without typing is a valid send."""
    prompt = compose_prompt_with_attachments("", ["/a/spec.pdf"])
    assert prompt == f"{ATTACHMENT_HEADER}\n- spec.pdf -> postmark://uploaded/spec.md"


def test_blank_paths_are_ignored() -> None:
    """Whitespace-only entries never produce empty bullet lines."""
    assert compose_prompt_with_attachments("hi", ["   ", ""]) == "hi"


def test_split_recovers_body_and_named_attachments() -> None:
    """The composed trailer splits back into prompt body and file references."""
    prompt = compose_prompt_with_attachments("turn this into a collection", ["/a/spec.pdf"])
    body, attachments = split_prompt_attachments(prompt)
    assert body == "turn this into a collection"
    assert attachments == [("spec.pdf", "postmark://uploaded/spec.md")]


def test_split_handles_an_attachment_only_prompt() -> None:
    """A send without typed text leaves an empty body and the chip list."""
    body, attachments = split_prompt_attachments(
        f"{ATTACHMENT_HEADER}\n- a.pdf -> postmark://uploaded/a.md"
    )
    assert body == ""
    assert [attachment.name for attachment in attachments] == ["a.pdf"]


def test_split_keeps_multiple_attachments_in_order() -> None:
    """Chips mirror the upload order of the composed trailer."""
    prompt = compose_prompt_with_attachments(
        "read these", ["/a/one.pdf", "/b/two.docx", "/c/shot.png"]
    )
    body, attachments = split_prompt_attachments(prompt)
    assert body == "read these"
    assert [attachment.name for attachment in attachments] == ["one.pdf", "two.docx", "shot.png"]


def test_split_reads_legacy_absolute_path_trailers() -> None:
    """Old transcripts named absolute paths; the chip shows the basename."""
    body, attachments = split_prompt_attachments(
        f"old turn\n\n{LEGACY_ATTACHMENT_HEADER}\n- /home/marik/Downloads/legacy.pdf"
    )
    assert body == "old turn"
    assert attachments == [("legacy.pdf", "/home/marik/Downloads/legacy.pdf")]


def test_split_ignores_plain_text_without_attachments() -> None:
    """A message with no trailer is returned untouched."""
    assert split_prompt_attachments("just words") == ("just words", [])


def test_split_never_eats_a_header_the_user_typed_mid_prompt() -> None:
    """The trailer is only stripped when bullets run to the end of the message."""
    text = f"what does {ATTACHMENT_HEADER} mean?\n- not the trailer\nmore prose after"
    assert split_prompt_attachments(text) == (text, [])


def test_split_tolerates_non_breaking_spaces_from_resaved_transcripts() -> None:
    """Trailers re-saved through edit paths carry NBSP variants; they still parse."""
    text = (
        "How about no? Read the file fully\n\nAttached files:\u00a0\n"
        "-\u00a0Swagger-Petstore (1).pdf\u00a0->\u00a0postmark://uploaded/Swagger-Petstore_1.md"
    )
    body, attachments = split_prompt_attachments(text)
    assert body == "How about no? Read the file fully"
    assert attachments == [
        ("Swagger-Petstore (1).pdf", "postmark://uploaded/Swagger-Petstore_1.md")
    ]


def test_split_strips_handle_era_prefix_from_the_display_name() -> None:
    """The ``doc:1`` era listed ``- doc:1 <name>``; the chip shows only the name."""
    body, attachments = split_prompt_attachments(
        f"read it\n\n{ATTACHMENT_HEADER}\n- doc:1 Agoda Standard Pull Spec v1.34 (5).pdf"
    )
    assert body == "read it"
    assert attachments == [
        ("Agoda Standard Pull Spec v1.34 (5).pdf", "doc:1 Agoda Standard Pull Spec v1.34 (5).pdf")
    ]


def test_sizes_from_sources_maps_uploaded_uris(tmp_path: Path) -> None:
    """Just-sent chips resolve their size from the picked source file."""
    source = tmp_path / "spec.pdf"
    source.write_bytes(b"x" * 2048)
    assert attachment_sizes_from_sources([str(source)]) == {"postmark://uploaded/spec.md": 2048}


def test_sizes_from_sources_skips_missing_files(tmp_path: Path) -> None:
    """A deleted source simply renders without a size label."""
    assert attachment_sizes_from_sources([str(tmp_path / "gone.pdf")]) == {}


def test_sizes_from_session_keys_uri_and_source_path(tmp_path: Path) -> None:
    """Restored transcripts resolve sizes for URI and legacy path references."""
    from uuid import uuid4

    from services.ai.chat.attachments.store import store_attachments

    fixture = Path(__file__).parents[3] / "services" / "document_import" / "fixtures" / "sample.pdf"
    session_id = uuid4().hex
    entries = store_attachments(session_id, [str(fixture)])
    assert entries, "fixture upload should store"
    sizes = attachment_sizes_from_session(session_id)
    assert sizes[entries[0]["uri"]] == entries[0]["size_bytes"]
    assert sizes[entries[0]["source_path"]] == entries[0]["size_bytes"]
    assert attachment_sizes_from_session("") == {}


def test_compose_prompt_attachments_round_trips_parsed_chips() -> None:
    """Edited prompts recompose from chip name/reference pairs, not source paths."""
    from ui.sidebar.ai.chat_panel.composer.attachments import (
        PromptAttachment,
        compose_prompt_with_prompt_attachments,
    )

    original = (
        "Turn this pdf into a collection please\n\n"
        "Attached files:\n"
        "- Agoda.pdf -> postmark://uploaded/Agoda.md"
    )
    body, attachments = split_prompt_attachments(original)
    assert body == "Turn this pdf into a collection please"
    assert attachments == [
        PromptAttachment("Agoda.pdf", "postmark://uploaded/Agoda.md"),
    ]
    assert compose_prompt_with_prompt_attachments(body, attachments) == original
