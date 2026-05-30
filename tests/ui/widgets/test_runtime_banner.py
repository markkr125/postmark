"""Tests for the RuntimeBanner widget."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ui.widgets.runtime_banner import RuntimeBanner


class TestRuntimeBanner:
    """Test suite for the RuntimeBanner widget."""

    def test_initial_state(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Banner creates without errors and has the expected children."""
        banner = RuntimeBanner()
        qtbot.addWidget(banner)
        assert banner.objectName() == "RuntimeBanner"
        assert banner._download_btn.isEnabled()
        assert not banner._progress_bar.isVisible()
        assert not banner._status_label.isVisible()

    def test_settings_link_emits(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """The Scripting settings link emits ``open_settings_clicked``."""
        banner = RuntimeBanner()
        qtbot.addWidget(banner)

        with qtbot.waitSignal(banner.open_settings_clicked, timeout=1000):
            banner._on_message_link("action:scripting")

    def test_download_button_starts_download(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Clicking download disables the button and shows progress."""
        from PySide6.QtCore import QThread

        banner = RuntimeBanner()
        qtbot.addWidget(banner)

        # Use a real QThread but prevent it from starting.
        with patch.object(QThread, "start"):
            banner._start_download()

        assert not banner._download_btn.isEnabled()
        assert banner._download_btn.text() == "Downloading\u2026"
        assert not banner._progress_bar.isHidden()

    def test_on_download_finished(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Successful download updates the banner message."""
        banner = RuntimeBanner()
        qtbot.addWidget(banner)

        with qtbot.waitSignal(banner.download_completed, timeout=1000):
            banner._on_download_finished("/fake/path/deno")

        assert "installed" in banner._message.text().lower()
        assert not banner._download_btn.isVisible()

    def test_on_download_error(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Failed download shows error message and retry button."""
        banner = RuntimeBanner()
        qtbot.addWidget(banner)
        banner._on_download_error("Connection timeout")

        assert "failed" in banner._message.text().lower()
        assert banner._download_btn.isEnabled()
        assert banner._download_btn.text() == "Retry"

    def test_progress_update(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Progress callback updates the bar and status label."""
        banner = RuntimeBanner()
        qtbot.addWidget(banner)
        banner._progress_bar.setVisible(True)
        banner._status_label.setVisible(True)

        banner._on_progress(5_242_880, 41_943_040)

        assert banner._progress_bar.maximum() == 41_943_040
        assert banner._progress_bar.value() == 5_242_880
        assert "5.0" in banner._status_label.text()
        assert "40.0" in banner._status_label.text()

    def test_progress_unknown_total(self, qapp: QApplication, qtbot) -> None:  # type: ignore[no-untyped-def]
        """When total is 0, progress bar is indeterminate."""
        banner = RuntimeBanner()
        qtbot.addWidget(banner)
        banner._progress_bar.setVisible(True)
        banner._status_label.setVisible(True)

        banner._on_progress(1_048_576, 0)

        assert banner._progress_bar.maximum() == 0  # indeterminate
        assert "1.0" in banner._status_label.text()
