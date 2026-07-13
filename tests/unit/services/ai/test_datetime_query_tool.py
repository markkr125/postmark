"""Tests for the postmark_datetime tool helpers and registration."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from services.ai.chat.tools.datetime_query import (
    DateTimeAction,
    DateTimeExecutor,
    execute_datetime_query,
    parse_when,
    resolve_zone,
)
from services.ai.chat.tool_registry import resolve_tools


def test_execute_now_includes_date_time_and_offset() -> None:
    """operation=now returns local date, time, and timezone offset."""
    frozen = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    text = execute_datetime_query("now", now=frozen)
    assert "## Current date/time" in text
    assert "**Local date:**" in text
    assert "**Local time:**" in text
    assert "**Local full:**" in text
    assert "**UTC full:**" in text
    assert "2026-07-13" in text
    assert "+00:00" in text or "UTC" in text


def test_convert_utc_to_australia_sydney_frozen_clock() -> None:
    """UTC → Australia resolves to Sydney with a fixed instant."""
    frozen = datetime(2026, 1, 15, 6, 0, 0, tzinfo=UTC)
    text = execute_datetime_query(
        "convert",
        when="now",
        from_tz="UTC",
        to_tz="Australia",
        now=frozen,
    )
    assert "Australia/Sydney" in text
    assert "2026-01-15 17:00:00" in text  # AEDT = UTC+11 in January
    assert "Assumed Australia/Sydney" in text


def test_convert_defaults_from_tz_to_local() -> None:
    """Omitting from_tz assumes local and records the assumption."""
    frozen = datetime(2026, 7, 13, 10, 0, 0, tzinfo=UTC)
    text = execute_datetime_query(
        "convert",
        when="10:00",
        to_tz="UTC",
        now=frozen,
    )
    assert "Source timezone omitted" in text
    assert "UTC" in text


def test_resolve_zone_fuzzy_labels() -> None:
    """Fuzzy labels resolve to expected IANA / local zones."""
    utc = resolve_zone("utc")
    assert not isinstance(utc, str)
    assert utc.key == "UTC"

    aus = resolve_zone("Australia")
    assert not isinstance(aus, str)
    assert aus.key == "Australia/Sydney"
    assert aus.note

    syd = resolve_zone("sydney")
    assert not isinstance(syd, str)
    assert syd.key == "Australia/Sydney"

    local = resolve_zone("local")
    assert not isinstance(local, str)
    assert local.tz is not None


def test_bad_zone_and_when_return_error_text() -> None:
    """Unknown zones and unparseable times return errors, not exceptions."""
    bad_zone = execute_datetime_query(
        "convert",
        when="now",
        from_tz="UTC",
        to_tz="NotARealPlaceXYZ",
    )
    assert bad_zone.startswith("Error:")
    assert "Unknown timezone" in bad_zone

    bad_when = execute_datetime_query(
        "convert",
        when="not-a-time",
        from_tz="UTC",
        to_tz="UTC",
    )
    assert bad_when.startswith("Error:")
    assert "Could not parse time" in bad_when

    missing_to = execute_datetime_query("convert", when="now", from_tz="UTC")
    assert missing_to.startswith("Error:")
    assert "to_tz" in missing_to


def test_parse_when_clock_and_iso() -> None:
    """Clock-only and ISO strings parse in the source timezone."""
    tz = ZoneInfo("UTC")
    frozen = datetime(2026, 7, 13, 8, 0, 0, tzinfo=tz)
    clock = parse_when("3:30pm", from_tz=tz, now=frozen)
    assert isinstance(clock, datetime)
    assert clock.hour == 15
    assert clock.minute == 30

    iso = parse_when("2026-07-13T15:30:00Z", from_tz=tz, now=frozen)
    assert isinstance(iso, datetime)
    assert iso.astimezone(UTC).hour == 15


def test_convert_unix_timestamp_to_local_reports_past() -> None:
    """Unix epoch seconds convert to local and include past/future relative to now."""
    frozen = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    # 1752386400 = 2025-07-13 06:00:00 UTC — one year before frozen now.
    text = execute_datetime_query(
        "convert",
        when="1752386400",
        from_tz="UTC",
        to_tz="local",
        now=frozen,
    )
    assert "2025-07-13" in text
    assert "Interpreted 1752386400 as Unix epoch seconds" in text
    assert "**Relative to now:** in the past" in text
    assert "1752386400" in text


def test_parse_unix_timestamp_variants() -> None:
    """unix:/epoch: prefixes and ms lengths parse as UTC."""
    tz = ZoneInfo("America/New_York")
    result = parse_when("unix:1752386400", from_tz=tz)
    assert isinstance(result, tuple)
    dt, note = result
    assert dt == datetime(2025, 7, 13, 6, 0, 0, tzinfo=UTC)
    assert "seconds" in note

    ms = parse_when("1752386400000", from_tz=tz)
    assert isinstance(ms, tuple)
    assert ms[0] == datetime(2025, 7, 13, 6, 0, 0, tzinfo=UTC)
    assert "milliseconds" in ms[1]


def test_datetime_executor_and_registration() -> None:
    """Executor wraps execute_datetime_query; tool name resolves."""
    obs = DateTimeExecutor()(
        DateTimeAction(operation="now"),
    )
    assert "Current date/time" in obs.text

    tools = resolve_tools(("postmark_datetime",))
    assert len(tools) == 1
    assert tools[0].name == "postmark_datetime"
