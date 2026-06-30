"""UI tests for the subagent detail dialog."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from services.ai.chat.subagent_events import SubagentRunRecord
from ui.sidebar.ai.subagent_detail_dialog import SubagentDetailDialog, _THOUGHT_BODY_MAX_PX


def test_detail_dialog_shows_task_and_streams_completed_answer(qapp: QApplication, qtbot) -> None:
    """Completed records render task prompt and markdown reply."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    record: SubagentRunRecord = {
        "id": "ts",
        "kind": "delegate",
        "label": "Find TypeScript scripting docs",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "Find TypeScript scripting docs in the Postmark wiki",
        "result_preview": "## TypeScript docs\n\nUse `pm.require`.",
    }
    dialog.open_record(record)
    qtbot.wait(10)
    assert dialog.isVisible()
    assert dialog._reply.objectName() == "aiChatAssistantText"
    assert dialog._task.text() == "Find TypeScript scripting docs in the Postmark wiki"
    assert "## TypeScript docs" in dialog._reply.markdown()
    assert not dialog._reply.is_streaming()


def test_detail_dialog_renders_bare_pm_lines_as_fenced_code(qapp: QApplication, qtbot) -> None:
    """Bare pm.request example lines use Pygments fenced blocks like the main chat."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    record: SubagentRunRecord = {
        "id": "py",
        "kind": "delegate",
        "label": "Find Python scripting docs",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "Find Python scripting docs",
        "result_preview": (
            "Example snippets:\n\n"
            'pm.request.headers["Authorization"] = f"Bearer {token}"\n\n'
            'pm.request.url.getHost()  # "127.0.0.1"\n'
        ),
    }
    dialog.open_record(record)
    qtbot.wait(10)
    html = dialog._reply.toHtml()
    assert "postmark-code-copy:0" in html
    assert "pm.request.url.getHost()" in dialog._reply.markdown()


def test_detail_dialog_renders_list_nested_code_as_fenced(qapp: QApplication, qtbot) -> None:
    """Wiki-style nested list examples still render as Pygments code blocks."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    record: SubagentRunRecord = {
        "id": "py",
        "kind": "delegate",
        "label": "Find Python scripting docs",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "Find Python scripting docs",
        "result_preview": (
            "◦ Request headers\n"
            "  # Pre-request: set auth header\n"
            '  pm.request.headers["Authorization"] = (\n'
            '      "Bearer " + pm.variables.get("token")\n'
            "  )\n"
        ),
    }
    dialog.open_record(record)
    qtbot.wait(10)
    assert "postmark-code-copy:0" in dialog._reply.toHtml()
    assert "Pre-request" in dialog._reply.markdown()


def test_detail_dialog_renders_indented_fences_in_lists(qapp: QApplication, qtbot) -> None:
    """Indented ``` fences under list items render with Copy controls."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    record: SubagentRunRecord = {
        "id": "py",
        "kind": "delegate",
        "label": "Find Python scripting docs",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "Find Python scripting docs",
        "result_preview": (
            "## Python scripting docs\n\n"
            "- **Request helpers**\n"
            "  - Auth header\n"
            "    ```python\n"
            "    # Pre-request: set auth header\n"
            '    pm.request.headers["Authorization"] = (\n'
            '        "Bearer " + pm.variables.get("token")\n'
            "    )\n"
            "    ```\n"
            "  - URL inspection\n"
            "    ```python\n"
            "    # URL inspection / mutation\n"
            "    print(pm.request.url.getHost())\n"
            '    pm.request.url.query.add({"key": "page", "value": "2"})\n'
            "    ```\n"
        ),
    }
    dialog.open_record(record)
    qtbot.wait(10)
    html = dialog._reply.toHtml()
    assert "postmark-code-copy:0" in html
    assert "postmark-code-copy:1" in html
    assert "getHost" in dialog._reply.markdown()


def test_detail_dialog_close_button_uses_outline_style(qapp: QApplication, qtbot) -> None:
    """Close lives at the bottom and uses the settings outline button styling."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    close_btn = dialog.findChild(QPushButton, "aiChatSubagentDetailClose")
    assert close_btn is not None
    assert close_btn.text() == "Close"
    assert not close_btn.icon().isNull()
    assert close_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_detail_dialog_refresh_updates_running_record(qapp: QApplication, qtbot) -> None:
    """An open running dialog picks up new preview text on refresh."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(
        {
            "id": "py",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": "Find Python scripting docs",
            "result_preview": "Searching…",
        }
    )
    assert dialog._reply.is_streaming()
    dialog.refresh_record(
        {
            "id": "py",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": "Find Python scripting docs",
            "result_preview": "Searching…\n\nFound quickref.",
        }
    )
    qtbot.wait(10)
    assert "Found quickref." in dialog._reply.markdown()


def test_detail_dialog_running_shows_working_activity_step(qapp: QApplication, qtbot) -> None:
    """Running records without disk show a Working… activity row."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(
        {
            "id": "run-a",
            "kind": "delegate",
            "label": "Find TypeScript scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": "Find TypeScript scripting docs",
        }
    )
    qtbot.wait(10)
    summaries = dialog.findChildren(QLabel, "aiChatSubagentDetailStepSummary")
    texts = [label.text() for label in summaries]
    assert "Working…" in texts


def test_detail_dialog_refresh_updates_activity_and_stops_poll_on_complete(
    qapp: QApplication, qtbot
) -> None:
    """Terminal refresh adds Read tool output with tooltip and stops polling."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(
        {
            "id": "run-b",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": "Find Python scripting docs",
        }
    )
    qtbot.wait(10)
    dialog.refresh_record(
        {
            "id": "run-b",
            "kind": "delegate",
            "label": "Find Python scripting docs",
            "subagent_type": "wiki-researcher",
            "status": "completed",
            "task_prompt": "Find Python scripting docs",
            "result_preview": "Found quickref for pm.require.",
        }
    )
    qtbot.wait(10)
    summaries = dialog.findChildren(QLabel, "aiChatSubagentDetailStepSummary")
    output_rows = [label for label in summaries if label.text() == "Read tool output"]
    assert output_rows
    assert "Found quickref for pm.require." in output_rows[0].toolTip()
    assert not dialog._poll_timer.isActive()


def test_detail_dialog_switching_records_clears_old_activity_steps(
    qapp: QApplication, qtbot
) -> None:
    """Opening a different record replaces activity rows from the prior one."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(
        {
            "id": "run-a",
            "kind": "delegate",
            "label": "Task A",
            "subagent_type": "general-purpose",
            "status": "running",
            "task_prompt": "Task A",
        }
    )
    qtbot.wait(10)
    dialog.open_record(
        {
            "id": "run-b",
            "kind": "wiki",
            "label": 'Searched wiki for "python"',
            "subagent_type": "wiki-researcher",
            "status": "running",
            "task_prompt": 'Searched wiki for "python"',
        }
    )
    qtbot.wait(10)
    summaries = dialog.findChildren(QLabel, "aiChatSubagentDetailStepSummary")
    texts = [label.text() for label in summaries]
    assert 'Searched wiki for "python"' in texts
    assert "Working…" not in texts


def test_detail_dialog_disk_refresh_uses_single_snapshot_read(qapp: QApplication, qtbot) -> None:
    """Poll refresh loads transcript and steps via one load_subagent_disk_snapshot call."""
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    snapshot = {
        "view": {
            "task_prompt": "Find TypeScript scripting docs",
            "answer_markdown": "Working on wiki results…",
            "event_count": 3,
        },
        "steps": [
            {
                "id": "search:1",
                "icon": "magnifying-glass",
                "summary": 'Searched wiki for "typescript"',
            },
            {"id": "obs:2", "icon": "article", "summary": "Read tool output", "detail": "Hit 1"},
        ],
    }
    with patch(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        return_value=snapshot,
    ) as load_snapshot:
        dialog.open_record(
            {
                "id": "disk-run",
                "kind": "delegate",
                "label": "Find TypeScript scripting docs",
                "subagent_type": "wiki-researcher",
                "status": "running",
                "task_prompt": "Find TypeScript scripting docs",
                "disk_path": "/tmp/subagents/disk-run",
            }
        )
        qtbot.wait(10)
        assert load_snapshot.call_count == 1
        dialog._poll_transcript()
        qtbot.wait(10)
        assert load_snapshot.call_count == 2
    summaries = dialog.findChildren(QLabel, "aiChatSubagentDetailStepSummary")
    texts = [label.text() for label in summaries]
    assert 'Searched wiki for "typescript"' in texts
    assert "Read tool output" in texts


def _snapshot(thinking: str) -> dict:
    """Build a SubagentDiskSnapshot-shaped dict with a chosen thinking string."""
    return {
        "view": {
            "task_prompt": "Find docs",
            "answer_markdown": "",
            "thinking_markdown": thinking,
            "event_count": 1,
        },
        "steps": [],
    }


def _running_record(record_id: str, disk_path: str) -> dict:
    return {
        "id": record_id,
        "kind": "delegate",
        "label": "Find docs",
        "subagent_type": "wiki-researcher",
        "status": "running",
        "task_prompt": "Find docs",
        "disk_path": disk_path,
    }


def test_detail_dialog_running_disk_thinking_shows_thought_block(
    qapp: QApplication, qtbot, tmp_path, monkeypatch
) -> None:
    """A running subagent's reasoning appears, expanded, in the thought block."""
    monkeypatch.setattr(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        lambda *a, **k: _snapshot("planning the search"),
    )
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(_running_record("t1", str(tmp_path)))
    qtbot.wait(10)
    assert dialog._thinking.has_text()
    assert "planning the search" in dialog._thinking.text()
    assert dialog._thinking.is_expanded()


def test_detail_dialog_no_thinking_hides_thought_block(
    qapp: QApplication, qtbot, tmp_path, monkeypatch
) -> None:
    """With no reasoning the thought block stays hidden."""
    monkeypatch.setattr(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        lambda *a, **k: _snapshot(""),
    )
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(_running_record("t2", str(tmp_path)))
    qtbot.wait(10)
    assert not dialog._thinking.has_text()
    assert not dialog._thinking.isVisible()


def test_detail_dialog_switching_records_clears_thinking(
    qapp: QApplication, qtbot, tmp_path, monkeypatch
) -> None:
    """Opening a second record clears the first record's reasoning."""
    monkeypatch.setattr(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        lambda *a, **k: _snapshot("first reasoning"),
    )
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(_running_record("a", str(tmp_path)))
    qtbot.wait(10)
    assert dialog._thinking.has_text()
    monkeypatch.setattr(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        lambda *a, **k: _snapshot(""),
    )
    dialog.open_record(_running_record("b", str(tmp_path)))
    qtbot.wait(10)
    assert not dialog._thinking.has_text()


def _completed_record(record_id: str, disk_path: str) -> dict:
    return {
        "id": record_id,
        "kind": "delegate",
        "label": "Find docs",
        "subagent_type": "wiki-researcher",
        "status": "completed",
        "task_prompt": "Find docs",
        "disk_path": disk_path,
    }


def test_detail_dialog_completed_disk_thinking_collapses_thought_block(
    qapp: QApplication, qtbot, tmp_path, monkeypatch
) -> None:
    """Completed records show reasoning in a collapsed thought block."""
    monkeypatch.setattr(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        lambda *a, **k: {
            "view": {
                "task_prompt": "Find docs",
                "answer_markdown": "Final answer.",
                "thinking_markdown": "completed reasoning trace",
                "event_count": 2,
            },
            "steps": [],
        },
    )
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(_completed_record("done-1", str(tmp_path)))
    qtbot.wait(10)
    assert dialog._thinking.has_text()
    assert "completed reasoning trace" in dialog._thinking.text()
    assert not dialog._thinking.is_expanded()


def test_detail_dialog_expanded_thinking_caps_scroll_height(
    qapp: QApplication, qtbot, tmp_path, monkeypatch
) -> None:
    """Long running reasoning is capped inside the thought scroll area."""
    long_thinking = "\n\n".join(f"Reasoning paragraph {i}. " * 30 for i in range(6))
    monkeypatch.setattr(
        "ui.sidebar.ai.subagent_detail_dialog.load_subagent_disk_snapshot",
        lambda *a, **k: _snapshot(long_thinking),
    )
    dialog = SubagentDetailDialog()
    qtbot.addWidget(dialog)
    dialog.open_record(_running_record("long-1", str(tmp_path)))
    qtbot.wait(10)
    assert dialog._thinking.has_text()
    assert dialog._thinking.is_expanded()
    assert dialog._thinking_scroll.isVisible()
    assert dialog._thinking_scroll.maximumHeight() == _THOUGHT_BODY_MAX_PX
