"""Thread-safe AI logging."""

from __future__ import annotations

from services.ai import ai_logging


def test_log_skips_ui_sink_off_gui_thread(monkeypatch) -> None:
    """Background threads must not invoke the UI sink (would crash Qt)."""
    calls: list[str] = []
    monkeypatch.setattr(ai_logging, "_on_gui_thread", lambda: False)
    ai_logging.set_ui_log_sink(calls.append)
    ai_logging.log("worker line")
    assert calls == []
