"""Tests for :class:`AiChatComposer`."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from services.ai.ai_config import AiModelEntry
from ui.sidebar.ai.chat_panel.composer import AiChatComposer


def _entry(model_id: str) -> AiModelEntry:
    return {
        "id": model_id,
        "provider": "openai",
        "label": "Test",
        "model": "openai/gpt-4o",
        "base_url": "",
        "api_version": "",
        "auth_kind": "none",
        "auth_ref": "",
        "context": 128_000,
        "enabled": True,
    }


def test_apply_and_read_send_snapshot_round_trip(qapp: QApplication, qtbot) -> None:
    """Snapshot helpers round-trip model/mode/agent fields."""
    composer = AiChatComposer()
    qtbot.addWidget(composer)
    composer.set_models([_entry("m1")])
    composer.set_mode("plan")
    composer.apply_model_pick("m1")
    composer._agent_id = "postmark-assistant"
    snapshot = composer.read_send_snapshot()
    composer.apply_send_snapshot(snapshot)
    assert composer.current_mode() == "plan"
    assert composer.current_model_id() == "m1"


def test_edit_mode_escape_emits_cancel(qapp: QApplication, qtbot) -> None:
    """Escape in edit mode emits ``cancel_requested``."""
    composer = AiChatComposer()
    qtbot.addWidget(composer)
    composer.set_edit_mode(True)
    fired: list[str] = []
    composer.cancel_requested.connect(lambda: fired.append("cancel"))
    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(composer.input_widget(), event)
    assert fired == ["cancel"]


def test_set_embedded_strips_composer_chrome(qapp: QApplication, qtbot) -> None:
    """Embedded mode uses inline objectNames and zero outer margins."""
    composer = AiChatComposer()
    qtbot.addWidget(composer)
    composer.set_embedded(True)
    assert composer.objectName() == "aiChatComposerInline"
    assert composer.input_widget().objectName() == "aiChatInputInline"
    assert composer._root_layout.contentsMargins().left() == 0


def test_compact_hides_context_ring(qapp: QApplication, qtbot) -> None:
    """Compact mode hides context ring and attach controls."""
    composer = AiChatComposer()
    qtbot.addWidget(composer)
    composer.set_models([_entry("m1")])
    composer.set_compact(True)
    assert not composer.context_ring().isVisible()
    assert not composer._upload_btn.isVisible()


def test_set_models_disabled_entries_show_enable_hint(qapp: QApplication, qtbot) -> None:
    """Configured-but-disabled models show an enable hint instead of empty state."""
    composer = AiChatComposer()
    qtbot.addWidget(composer)
    disabled = _entry("m1")
    disabled["enabled"] = False
    composer.set_models([disabled])
    assert composer.model_button_label() == "Enable a model in Settings"
    assert composer.model_button().isEnabled()
    assert not composer.send_button().isEnabled()
