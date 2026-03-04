"""Tests for the StatusPopup widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.popups.status_popup import (
    STATUS_DESCRIPTIONS,
    StatusPopup,
    _status_description,
)


class TestStatusDescription:
    """Tests for the status description lookup helper."""

    def test_known_code_200(self) -> None:
        """200 returns the documented description."""
        desc = _status_description(200)
        assert "successful" in desc.lower()

    def test_known_code_404(self) -> None:
        """404 returns the documented description."""
        desc = _status_description(404)
        assert "not found" in desc.lower() or "could not be found" in desc.lower()

    def test_known_code_500(self) -> None:
        """500 returns the documented description."""
        desc = _status_description(500)
        assert "unexpected" in desc.lower() or "server" in desc.lower()

    def test_unknown_code_falls_back_to_range(self) -> None:
        """An uncommon code like 299 falls back to the 2xx range description."""
        desc = _status_description(299)
        assert desc  # non-empty
        assert 299 not in STATUS_DESCRIPTIONS

    def test_completely_unknown_code(self) -> None:
        """A code outside 100-599 gives a fallback description."""
        desc = _status_description(999)
        assert desc  # non-empty


class TestStatusPopup:
    """Tests for the StatusPopup widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """StatusPopup can be instantiated."""
        popup = StatusPopup()
        qtbot.addWidget(popup)
        assert popup is not None

    def test_update_status_200(self, qapp: QApplication, qtbot) -> None:
        """update_status(200, 'OK') populates the code and description."""
        popup = StatusPopup()
        qtbot.addWidget(popup)
        popup.update_status(200, "OK", "#2ecc71")

        assert "200" in popup._code_label.text()
        assert "OK" in popup._code_label.text()
        assert popup._desc_label.text()  # non-empty description

    def test_update_status_404(self, qapp: QApplication, qtbot) -> None:
        """update_status(404, 'Not Found') shows the 404 description."""
        popup = StatusPopup()
        qtbot.addWidget(popup)
        popup.update_status(404, "Not Found", "#e67e22")

        assert "404" in popup._code_label.text()
        assert (
            "not found" in popup._desc_label.text().lower()
            or "could not" in popup._desc_label.text().lower()
        )

    def test_update_status_unknown_code(self, qapp: QApplication, qtbot) -> None:
        """A rare status code still shows a description without crashing."""
        popup = StatusPopup()
        qtbot.addWidget(popup)
        popup.update_status(599, "Unknown", "#e74c3c")

        assert "599" in popup._code_label.text()
        assert popup._desc_label.text()  # fallback description
