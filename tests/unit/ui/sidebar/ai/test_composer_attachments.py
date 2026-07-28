"""Tests for composing prompt text from composer attachments."""

from __future__ import annotations

from ui.sidebar.ai.chat_panel.composer.attachments import (
    ATTACHMENT_HEADER,
    attachment_references_from_prompt,
    compose_prompt_with_attachments,
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
