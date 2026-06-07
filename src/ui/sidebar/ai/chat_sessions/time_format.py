"""Relative-time formatting for AI session history rows."""

from __future__ import annotations

from datetime import UTC, datetime


def format_message_sent_at(dt: datetime) -> str:
    """Format a user-message send time for the transcript (local clock)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local = dt.astimezone()
    now = datetime.now(tz=local.tzinfo)
    hour12 = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    clock = f"{hour12}:{local.minute:02d} {suffix}"
    if local.year == now.year:
        return f"{local.strftime('%b')} {local.day}, {clock}"
    return f"{local.strftime('%b %d, %Y')}, {clock}"


def format_relative_time(dt: datetime) -> str:
    """Format *dt* as a compact relative time (``now``, ``5m``, ``3h``, ``4d``, or date)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(tz=UTC)
    delta = now - dt.astimezone(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    if days < 7:
        return f"{days}d"
    return dt.astimezone().strftime("%b %d")
