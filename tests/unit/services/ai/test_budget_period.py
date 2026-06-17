"""Tests for budget period window helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from services.ai.budget_period import (
    daily_reset_anchor,
    format_period_reset_label,
    parse_period_anchor,
    parse_period_reset,
    period_window,
    weekly_reset_anchor,
)


def test_parse_period_anchor_accepts_iso_date() -> None:
    """Anchor text parses as a calendar date."""
    assert parse_period_anchor("2026-06-01") == date(2026, 6, 1)
    assert parse_period_anchor("") is None


def test_parse_period_reset_accepts_time_suffix() -> None:
    """Anchors may include a local reset time."""
    reset = parse_period_reset("2026-06-01T09:30")
    assert reset is not None
    assert reset.anchor_date == date(2026, 6, 1)
    assert reset.hour == 9
    assert reset.minute == 30


def test_period_window_weekly_rolls_from_anchor() -> None:
    """Weekly windows reset every seven days from the anchor schedule."""
    anchor = weekly_reset_anchor(weekday=0, hour=0, minute=0)
    now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    window = period_window("weekly", anchor, now=now)
    assert window is not None
    start, end = window
    assert int((end - start).total_seconds()) == 7 * 24 * 60 * 60


def test_period_window_daily_uses_reset_hour() -> None:
    """Daily windows roll at the configured local hour."""
    anchor = daily_reset_anchor(hour=9, minute=0)
    now = datetime(2026, 6, 10, 15, 0, tzinfo=UTC)
    window = period_window("daily", anchor, now=now)
    assert window is not None
    start, end = window
    assert end - start == timedelta(days=1)


def test_period_window_none_returns_none() -> None:
    """No-reset budgets do not define a bounded window."""
    assert period_window("none", date(2026, 1, 1)) is None


def test_format_period_reset_label_daily() -> None:
    """Daily labels show the reset hour."""
    label = format_period_reset_label("daily", daily_reset_anchor(hour=9, minute=30))
    assert label == "Daily @ 09:30"
