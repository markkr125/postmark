"""UI tests for agent-execute result cards in the chat transcript."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.ai.chat.execute_events import ExecuteRunRecord
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.execute.card import ExecuteResultCard


def test_execute_card_click_emits_history_deeplink(qapp: QApplication, qtbot) -> None:
    """Clicking an execute card requests history open with focus=response."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    record: ExecuteRunRecord = {
        "id": "ex1",
        "operation": "send_request",
        "label": "Sent GET Ping",
        "status": "completed",
        "status_code": 200,
        "url": "https://example.com/ping",
        "history_entry_id": 42,
        "request_id": 7,
        "local_script_id": None,
        "collection_id": None,
        "script_phase": None,
    }
    bubble.set_execute_records([record])
    cards = bubble.findChildren(ExecuteResultCard)
    assert len(cards) == 1
    seen: list[tuple[str, int, str]] = []
    bubble.workspace_target_requested.connect(
        lambda kind, eid, focus: seen.append((kind, eid, focus))
    )
    cards[0].clicked.emit("ex1")
    assert seen == [("history", 42, "response")]


def test_execute_card_falls_back_to_request(qapp: QApplication, qtbot) -> None:
    """Without history_entry_id, click opens the request tab."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    record: ExecuteRunRecord = {
        "id": "ex2",
        "operation": "run_scripts",
        "label": "Ran scripts",
        "status": "completed",
        "status_code": None,
        "url": "",
        "history_entry_id": None,
        "request_id": 11,
        "local_script_id": None,
        "collection_id": None,
        "script_phase": "both",
    }
    bubble.upsert_execute_record(record)
    seen: list[tuple[str, int, str]] = []
    bubble.workspace_target_requested.connect(
        lambda kind, eid, focus: seen.append((kind, eid, focus))
    )
    bubble._on_execute_card_clicked("ex2")
    assert seen == [("request", 11, "test")]


def test_execute_card_run_scripts_pre_phase(qapp: QApplication, qtbot) -> None:
    """run_scripts with pre phase focuses the pre-request Scripts sub-tab."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    record: ExecuteRunRecord = {
        "id": "ex3",
        "operation": "run_scripts",
        "label": "Ran pre scripts",
        "status": "completed",
        "status_code": None,
        "url": "",
        "history_entry_id": None,
        "request_id": 5,
        "local_script_id": None,
        "collection_id": None,
        "script_phase": "pre",
    }
    bubble.set_execute_records([record])
    seen: list[tuple[str, int, str]] = []
    bubble.workspace_target_requested.connect(
        lambda kind, eid, focus: seen.append((kind, eid, focus))
    )
    bubble._on_execute_card_clicked("ex3")
    assert seen == [("request", 5, "pre_request")]


def test_execute_card_run_local_script(qapp: QApplication, qtbot) -> None:
    """run_local_script card opens the script tab."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    record: ExecuteRunRecord = {
        "id": "ex4",
        "operation": "run_local_script",
        "label": "Ran local script",
        "status": "completed",
        "status_code": None,
        "url": "",
        "history_entry_id": None,
        "request_id": None,
        "local_script_id": 99,
        "collection_id": None,
        "script_phase": None,
    }
    bubble.set_execute_records([record])
    seen: list[tuple[str, int, str]] = []
    bubble.workspace_target_requested.connect(
        lambda kind, eid, focus: seen.append((kind, eid, focus))
    )
    bubble._on_execute_card_clicked("ex4")
    assert seen == [("script", 99, "")]


def test_execute_card_run_collection(qapp: QApplication, qtbot) -> None:
    """run_collection card opens the folder Runs panel."""
    bubble = ChatMessageBubble("assistant", "")
    qtbot.addWidget(bubble)
    record: ExecuteRunRecord = {
        "id": "ex5",
        "operation": "run_collection",
        "label": "Ran collection",
        "status": "completed",
        "status_code": None,
        "url": "",
        "history_entry_id": None,
        "request_id": None,
        "local_script_id": None,
        "collection_id": 15,
        "script_phase": None,
    }
    bubble.set_execute_records([record])
    seen: list[tuple[str, int, str]] = []
    bubble.workspace_target_requested.connect(
        lambda kind, eid, focus: seen.append((kind, eid, focus))
    )
    bubble._on_execute_card_clicked("ex5")
    assert seen == [("collection", 15, "runs")]
