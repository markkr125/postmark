"""Tests for the DebugPanel sidebar widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.debug_panel import DebugPanel


class TestDebugPanel:
    """Tests for the debug panel widget — step controls and variable display."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """DebugPanel can be instantiated without errors."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        assert panel._position_label.text() == "Idle"

    def test_buttons_start_disabled(self, qapp: QApplication, qtbot) -> None:
        """Step buttons are disabled when no session is active."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        assert not panel._continue_btn.isEnabled()
        assert not panel._step_over_btn.isEnabled()
        assert not panel._step_into_btn.isEnabled()
        assert not panel._step_out_btn.isEnabled()
        assert not panel._stop_btn.isEnabled()

    def test_update_pause_enables_buttons(self, qapp: QApplication, qtbot) -> None:
        """update_pause() enables step buttons and shows position."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 5,
                "source_name": "test.js",
                "local_vars": {"x": 42},
                "script_type": "pre_request",
            }
        )
        assert panel._continue_btn.isEnabled()
        assert panel._stop_btn.isEnabled()
        assert "line 6" in panel._position_label.text()
        assert "pre_request" in panel._position_label.text()

    def test_update_pause_shows_variables(self, qapp: QApplication, qtbot) -> None:
        """update_pause() populates the variable list."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {"a": 1, "b": "hello"},
                "script_type": "test",
            }
        )
        # Content layout has variable rows + stretch
        assert panel._content_layout.count() > 1

    def test_update_pause_empty_vars(self, qapp: QApplication, qtbot) -> None:
        """update_pause() shows placeholder when no variables exist."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {},
                "script_type": "test",
            }
        )
        # Stretch + "No local variables" label
        assert panel._content_layout.count() == 2

    def test_clear_session(self, qapp: QApplication, qtbot) -> None:
        """clear_session() disables buttons and shows ended message."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {"x": 1},
                "script_type": "pre_request",
            }
        )
        panel.clear_session()
        assert not panel._continue_btn.isEnabled()
        assert "ended" in panel._position_label.text().lower()

    def test_set_idle(self, qapp: QApplication, qtbot) -> None:
        """set_idle() resets to initial idle state."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 3,
                "source_name": "",
                "local_vars": {"a": 1},
                "script_type": "test",
            }
        )
        panel.set_idle()
        assert panel._position_label.text() == "Idle"
        assert not panel._continue_btn.isEnabled()

    def test_step_signal_emitted(self, qapp: QApplication, qtbot) -> None:
        """Clicking a step button emits step_requested with the mode name."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {},
                "script_type": "pre_request",
            }
        )
        with qtbot.waitSignal(panel.step_requested, timeout=1000) as blocker:
            panel._continue_btn.click()
        assert blocker.args == ["continue"]

    def test_step_over_signal(self, qapp: QApplication, qtbot) -> None:
        """Step Over button emits 'step_over'."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {},
                "script_type": "pre_request",
            }
        )
        with qtbot.waitSignal(panel.step_requested, timeout=1000) as blocker:
            panel._step_over_btn.click()
        assert blocker.args == ["step_over"]

    def test_stop_signal(self, qapp: QApplication, qtbot) -> None:
        """Stop button emits 'stop'."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {},
                "script_type": "pre_request",
            }
        )
        with qtbot.waitSignal(panel.step_requested, timeout=1000) as blocker:
            panel._stop_btn.click()
        assert blocker.args == ["stop"]

    def test_variables_replaced_on_subsequent_pause(self, qapp: QApplication, qtbot) -> None:
        """Calling update_pause() again replaces previous variables."""
        panel = DebugPanel()
        qtbot.addWidget(panel)
        panel.update_pause(
            {
                "line": 0,
                "source_name": "",
                "local_vars": {"a": 1, "b": 2, "c": 3},
                "script_type": "test",
            }
        )
        count_before = panel._content_layout.count()
        panel.update_pause(
            {
                "line": 1,
                "source_name": "",
                "local_vars": {"x": 10},
                "script_type": "test",
            }
        )
        # Should have 1 variable row + stretch = 2 items
        assert panel._content_layout.count() == 2
        assert panel._content_layout.count() <= count_before
