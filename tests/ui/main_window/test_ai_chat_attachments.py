"""End-to-end tests that an attached document reaches the model."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas

from services.ai.chat.attachments.store import list_attachments, read_markdown
from ui.main_window.window import MainWindow


def _pdf(path: Path, text: str = "GET /hotels returns availability") -> Path:
    """Write a minimal one-page PDF at *path*."""
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def window(qapp: QApplication, qtbot) -> MainWindow:
    """Return a MainWindow with a model configured for the chat panel."""
    win = MainWindow()
    qtbot.addWidget(win)
    win._right_sidebar.ai_chat_panel.set_models(
        [
            {
                "id": "m1",
                "provider": "openai",
                "label": "GPT-4o",
                "model": "openai/gpt-4o",
                "base_url": "",
                "api_version": "",
                "auth_kind": "none",
                "auth_ref": "",
                "context": 128_000,
                "enabled": True,
            }
        ]
    )
    return win


def _send_with_attachment(window: MainWindow, source: Path) -> None:
    """Attach *source* in the docked composer and send."""
    panel = window._right_sidebar.ai_chat_panel
    composer = panel._docked_composer
    composer.restore_text("can you turn this pdf into a collection?")
    composer._attachments.append(str(source))
    composer._add_attachment_chip(str(source))
    panel._on_docked_send()


def test_attachment_is_stored_for_the_session_on_send(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The attachment must be copied in, or nothing downstream can read it."""
    started: list[str] = []
    monkeypatch.setattr(
        type(window),
        "_start_chat_run",
        lambda self, **kwargs: started.append(kwargs["session_id"]),
    )
    _send_with_attachment(window, _pdf(tmp_path / "spec.pdf"))

    assert started, "the send never reached the controller"
    entries = list_attachments(started[0])
    assert [e["name"] for e in entries] == ["spec.pdf"]
    assert Path(entries[0]["stored_path"]).is_file()


def test_upload_is_converted_to_markdown_the_agent_can_read(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The document must exist as Markdown before the agent tries to read it."""
    started: list[str] = []
    monkeypatch.setattr(
        type(window),
        "_start_chat_run",
        lambda self, **kwargs: started.append(kwargs["session_id"]),
    )
    _send_with_attachment(window, _pdf(tmp_path / "spec.pdf"))

    entry = list_attachments(started[0])[0]
    assert entry["uri"] == "postmark://uploaded/spec.md"
    assert "GET /hotels returns availability" in read_markdown(entry)


def test_prompt_carries_the_uri_and_not_the_document_body(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whole document in the message would not fit context; the URI is the handle."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        type(window),
        "_start_chat_run",
        lambda self, **kwargs: captured.update(kwargs),
    )
    _send_with_attachment(window, _pdf(tmp_path / "spec.pdf"))

    prompt = str(captured["text"])
    assert "postmark://uploaded/spec.md" in prompt
    assert "GET /hotels returns availability" not in prompt
    assert str(tmp_path) not in prompt
