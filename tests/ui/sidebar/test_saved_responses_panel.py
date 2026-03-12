"""Tests for the SavedResponsesPanel widget."""

from __future__ import annotations

from typing import cast

from PySide6.QtWidgets import QApplication

from services.collection_service import SavedResponseDict
from ui.sidebar.saved_responses.delegate import (ROLE_RESPONSE_CODE,
                                                 ROLE_RESPONSE_META,
                                                 ROLE_RESPONSE_NAME)
from ui.sidebar.saved_responses.helpers import detect_body_language
from ui.sidebar.saved_responses.panel import SavedResponsesPanel


class TestSavedResponsesPanel:
    """Tests for the saved responses list/detail sidebar panel."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Panel can be instantiated and starts in a request-required state."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        assert "Open a saved request" in panel._state_label.text()

    def test_set_saved_responses_populates_list(self, qapp: QApplication, qtbot) -> None:
        """Saved response items populate the list and first detail entry."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Success",
                    "status": "OK",
                    "code": 200,
                    "headers": [{"key": "Content-Type", "value": "application/json"}],
                    "body": '{"ok": true}',
                    "preview_language": "json",
                    "original_request": {"method": "GET", "url": "https://example.com"},
                    "created_at": "2026-03-12 10:00",
                    "body_size": 12,
                }
            ]
        )
        assert panel._list_widget.count() == 1
        assert "Success" in panel._detail_name.text()
        assert '"ok": true' in panel._body_edit.toPlainText()

    def test_body_view_can_switch_between_pretty_and_raw(self, qapp: QApplication, qtbot) -> None:
        """Saved response body can switch between pretty and raw display."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Success",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": '{"ok":true}',
                    "preview_language": "json",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 11,
                }
            ]
        )

        assert "\n" in panel._body_edit.toPlainText()
        panel._body_view_combo.setCurrentText("Raw")
        assert panel._body_edit.toPlainText() == '{"ok":true}'

    def test_empty_examples_state(self, qapp: QApplication, qtbot) -> None:
        """Persisted request with no examples shows the empty examples state."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses([])
        assert "No saved responses" in panel._state_label.text()

    def test_legacy_dict_headers_do_not_crash(self, qapp: QApplication, qtbot) -> None:
        """Legacy saved responses with dict-shaped headers still render safely."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                cast(
                    SavedResponseDict,
                    {
                        "id": 11,
                        "request_id": 1,
                        "name": "Legacy",
                        "status": "OK",
                        "code": 200,
                        "headers": {"Content-Type": "application/json"},
                        "body": "ok",
                        "preview_language": "json",
                        "original_request": {
                            "method": "GET",
                            "url": "https://example.com",
                            "headers": {"Accept": "application/json"},
                        },
                        "created_at": "2026-03-12 10:00",
                        "body_size": 2,
                    },
                )
            ]
        )
        assert "Content-Type: application/json" in panel._headers_edit.toPlainText()
        assert '"Accept": "application/json"' in panel._snapshot_edit.toPlainText()

    def test_snapshot_view_can_switch_between_pretty_and_raw(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Saved request snapshot can switch between pretty and compact JSON."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 12,
                    "request_id": 1,
                    "name": "Snapshot",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": "ok",
                    "preview_language": "text",
                    "original_request": {"method": "GET", "url": "https://example.com"},
                    "created_at": "2026-03-12 10:00",
                    "body_size": 2,
                }
            ]
        )

        assert "\n" in panel._snapshot_edit.toPlainText()
        panel._snapshot_view_combo.setCurrentText("Raw")
        assert panel._snapshot_edit.toPlainText() == '{"method":"GET","url":"https://example.com"}'

    def test_view_modes_persist_across_saved_response_selection(
        self, qapp: QApplication, qtbot
    ) -> None:
        """Body and snapshot view modes stay on the user's last chosen mode."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 12,
                    "request_id": 1,
                    "name": "First",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": '{"first":true}',
                    "preview_language": "json",
                    "original_request": {"method": "GET", "url": "https://example.com/a"},
                    "created_at": "2026-03-12 10:00",
                    "body_size": 14,
                },
                {
                    "id": 13,
                    "request_id": 1,
                    "name": "Second",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": '{"second":true}',
                    "preview_language": "json",
                    "original_request": {"method": "GET", "url": "https://example.com/b"},
                    "created_at": "2026-03-12 10:01",
                    "body_size": 15,
                },
            ]
        )

        panel._body_view_combo.setCurrentText("Raw")
        panel._snapshot_view_combo.setCurrentText("Raw")

        panel.select_response(13)

        assert panel._body_view_combo.currentText() == "Raw"
        assert panel._snapshot_view_combo.currentText() == "Raw"
        assert panel._body_edit.toPlainText() == '{"second":true}'
        assert (
            panel._snapshot_edit.toPlainText() == '{"method":"GET","url":"https://example.com/b"}'
        )

    def test_save_current_signal(self, qapp: QApplication, qtbot) -> None:
        """Save Current button emits its signal when enabled."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_live_response_available(True)
        with qtbot.waitSignal(panel.save_current_requested, timeout=1000):
            panel._save_current_btn.click()

    def test_status_badge_shows_code_and_colour(self, qapp: QApplication, qtbot) -> None:
        """Status badge displays the HTTP code with a coloured background."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Success",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": "ok",
                    "preview_language": "text",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 2,
                }
            ]
        )
        assert panel._status_badge.text() == "200"
        assert "background:" in panel._status_badge.styleSheet()

    def test_delete_button_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """Delete icon button emits delete_requested for the current item."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Success",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": "ok",
                    "preview_language": "text",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 2,
                }
            ]
        )
        with qtbot.waitSignal(panel.delete_requested, timeout=1000) as blocker:
            panel._delete_btn.click()
        assert blocker.args == [10]

    def test_rename_and_duplicate_buttons_emit_signals(self, qapp: QApplication, qtbot) -> None:
        """Rename and Duplicate icon buttons emit their respective signals."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Item",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": "ok",
                    "preview_language": "text",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 2,
                }
            ]
        )
        with qtbot.waitSignal(panel.rename_requested, timeout=1000) as blocker:
            panel._rename_btn.click()
        assert blocker.args == [10]
        with qtbot.waitSignal(panel.duplicate_requested, timeout=1000) as blocker:
            panel._duplicate_btn.click()
        assert blocker.args == [10]

    def test_copy_body_button_copies_to_clipboard(self, qapp: QApplication, qtbot) -> None:
        """Body copy button puts editor text onto the system clipboard."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Item",
                    "status": "OK",
                    "code": 200,
                    "headers": [{"key": "X", "value": "Y"}],
                    "body": '{"a":1}',
                    "preview_language": "json",
                    "original_request": {"method": "GET", "url": "https://x.com"},
                    "created_at": "2026-03-12 10:00",
                    "body_size": 7,
                }
            ]
        )
        panel._body_copy_btn.click()
        clipboard = QApplication.clipboard()
        assert clipboard is not None
        assert "a" in clipboard.text()

    def test_empty_body_shows_empty_label(self, qapp: QApplication, qtbot) -> None:
        """Empty body hides the editor and shows the empty-state label."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Empty",
                    "status": "No Content",
                    "code": 204,
                    "headers": [],
                    "body": "",
                    "preview_language": "text",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 0,
                }
            ]
        )
        assert not panel._body_empty_label.isHidden()
        assert panel._body_edit.isHidden()

    def test_delegate_data_roles_on_list_items(self, qapp: QApplication, qtbot) -> None:
        """List items carry custom data roles for the delegate to paint."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Check",
                    "status": "OK",
                    "code": 201,
                    "headers": [],
                    "body": "ok",
                    "preview_language": "text",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 2,
                }
            ]
        )
        item = panel._list_widget.item(0)
        assert item.data(ROLE_RESPONSE_CODE) == 201
        assert item.data(ROLE_RESPONSE_NAME) == "Check"
        assert isinstance(item.data(ROLE_RESPONSE_META), str)

    def test_enriched_detail_metadata(self, qapp: QApplication, qtbot) -> None:
        """Detail metadata shows status, date, language, and body size."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Rich",
                    "status": "OK",
                    "code": 200,
                    "headers": [],
                    "body": "ok",
                    "preview_language": "json",
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 1024,
                }
            ]
        )
        meta = panel._detail_meta.text()
        assert "OK" in meta
        assert "JSON" in meta
        assert "1.0" in meta  # 1024 bytes → "1.0 KB"

    def test_body_language_detected_from_json_body(self, qapp: QApplication, qtbot) -> None:
        """When preview_language is None, JSON body gets syntax detected."""
        panel = SavedResponsesPanel()
        qtbot.addWidget(panel)
        panel.set_request_context(1, "Search")
        panel.set_saved_responses(
            [
                {
                    "id": 10,
                    "request_id": 1,
                    "name": "Auto",
                    "status": "Bad Request",
                    "code": 400,
                    "headers": [],
                    "body": '{"error": "bad"}',
                    "preview_language": None,
                    "original_request": None,
                    "created_at": "2026-03-12 10:00",
                    "body_size": 16,
                }
            ]
        )
        assert panel._body_language == "json"


class TestDetectBodyLanguage:
    """Unit tests for the detect_body_language helper."""

    def test_json_object(self) -> None:
        """Detect JSON object body."""
        assert detect_body_language('{"key": "value"}') == "json"

    def test_json_array(self) -> None:
        """Detect JSON array body."""
        assert detect_body_language("[1, 2, 3]") == "json"

    def test_invalid_json_starting_with_brace(self) -> None:
        """Brace-prefixed non-JSON returns None."""
        assert detect_body_language("{not json at all") is None

    def test_xml_body(self) -> None:
        """Detect XML body."""
        assert detect_body_language("<?xml version='1.0'?><root/>") == "xml"

    def test_html_doctype(self) -> None:
        """Detect HTML with DOCTYPE."""
        assert detect_body_language("<!DOCTYPE html><html></html>") == "html"

    def test_html_tag(self) -> None:
        """Detect HTML starting with <html tag."""
        assert detect_body_language("<html><body></body></html>") == "html"

    def test_plain_text(self) -> None:
        """Plain text returns None."""
        assert detect_body_language("hello world") is None

    def test_empty_body(self) -> None:
        """Empty string returns None."""
        assert detect_body_language("") is None

    def test_whitespace_json(self) -> None:
        """Whitespace-padded JSON is still detected."""
        assert detect_body_language('  \n  {"ok": true}  ') == "json"
