"""UI tests for the subagent detail dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from services.ai.chat.subagent_events import SubagentRunRecord
from ui.sidebar.ai.subagent_detail_dialog import SubagentDetailDialog


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
    close_btn = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == "Close"
    )
    assert close_btn.objectName() == "outlineButton"
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
