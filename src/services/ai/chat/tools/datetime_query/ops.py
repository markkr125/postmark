"""Pure datetime / timezone helpers for ``postmark_datetime``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo, available_timezones

Operation = Literal["now", "convert"]

# Common free-text labels → IANA zone (ambiguous regions pick a documented default).
_ZONE_ALIASES: dict[str, str] = {
    "local": "local",
    "here": "local",
    "utc": "UTC",
    "gmt": "UTC",
    "zulu": "UTC",
    "australia": "Australia/Sydney",
    "aus": "Australia/Sydney",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide",
    "uk": "Europe/London",
    "britain": "Europe/London",
    "england": "Europe/London",
    "london": "Europe/London",
    "europe": "Europe/Paris",
    "eu": "Europe/Paris",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "india": "Asia/Kolkata",
    "ist": "Asia/Kolkata",
    "japan": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "china": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    "hongkong": "Asia/Hong_Kong",
    "eastern": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "et": "America/New_York",
    "central": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "ct": "America/Chicago",
    "mountain": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "mt": "America/Denver",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
    "awst": "Australia/Perth",
    "acst": "Australia/Adelaide",
    "acdt": "Australia/Adelaide",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "bst": "Europe/London",
    "jst": "Asia/Tokyo",
    "nz": "Pacific/Auckland",
    "new zealand": "Pacific/Auckland",
    "auckland": "Pacific/Auckland",
}

_AMBIGUOUS_NOTES: dict[str, str] = {
    "Australia/Sydney": (
        "Assumed Australia/Sydney (AEST/AEDT). Other common zones: "
        "Australia/Melbourne, Australia/Brisbane, Australia/Perth, Australia/Adelaide."
    ),
    "Europe/Paris": (
        "Assumed Europe/Paris (CET/CEST). Other common zones: "
        "Europe/Berlin, Europe/Madrid, Europe/Rome."
    ),
    "America/New_York": (
        "Assumed America/New_York (US Eastern). Other US zones: "
        "America/Chicago, America/Denver, America/Los_Angeles."
    ),
}

_CLOCK_RE = re.compile(
    r"^"
    r"(?P<h>\d{1,2})"
    r"(?::(?P<m>\d{2})(?::(?P<s>\d{2}))?)?"
    r"\s*(?P<ampm>[AaPp][Mm])?"
    r"$"
)
_UNIX_TS_RE = re.compile(r"^(?:unix:|epoch:)?(?P<n>\d{9,13})(?:\s*(?:s|ms|sec|secs|seconds?))?$")
_SPACE_DT_RE = re.compile(
    r"^"
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"[ T]"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?P<frac>\.\d+)?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?"
    r"$",
    re.IGNORECASE,
)

_IANA_LOOKUP: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedZone:
    """A resolved timezone with optional assumption note for the observation."""

    key: str
    tz: tzinfo
    note: str | None = None


def _iana_lookup() -> dict[str, str]:
    """Build a lowercase → canonical IANA map (cached)."""
    global _IANA_LOOKUP
    if _IANA_LOOKUP is None:
        _IANA_LOOKUP = {name.lower(): name for name in available_timezones()}
    return _IANA_LOOKUP


def _local_tz() -> tzinfo:
    """Return the OS local timezone."""
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def _zone_key(tz: tzinfo) -> str:
    """Human-readable key for a tzinfo."""
    key = getattr(tz, "key", None)
    if isinstance(key, str) and key:
        return key
    name = str(tz)
    return name if name else "local"


def resolve_zone(label: str | None) -> ResolvedZone | str:
    """Resolve a free-text timezone label.

    Returns a :class:`ResolvedZone` on success, or an error string on failure.
    Empty / ``local`` / ``here`` → OS local timezone.
    """
    raw = (label or "").strip()
    if not raw or raw.lower() in {"local", "here"}:
        tz = _local_tz()
        return ResolvedZone(key=_zone_key(tz), tz=tz)

    lowered = raw.lower().replace("_", " ").strip()
    alias = _ZONE_ALIASES.get(lowered) or _ZONE_ALIASES.get(lowered.replace(" ", ""))
    if alias == "local":
        tz = _local_tz()
        return ResolvedZone(key=_zone_key(tz), tz=tz, note=None)
    if alias is not None:
        try:
            zi = ZoneInfo(alias)
        except (KeyError, ValueError, OSError):
            return f"Unknown timezone after alias resolve: {alias!r} (from {raw!r})."
        note = _AMBIGUOUS_NOTES.get(alias)
        return ResolvedZone(key=alias, tz=zi, note=note)

    iana = _iana_lookup()
    exact = iana.get(raw.lower()) or iana.get(raw.replace(" ", "_").lower())
    if exact is not None:
        return ResolvedZone(key=exact, tz=ZoneInfo(exact))

    needle = lowered.replace(" ", "_")
    hits = [name for name in iana.values() if needle in name.lower()]
    if len(hits) == 1:
        name = hits[0]
        return ResolvedZone(key=name, tz=ZoneInfo(name))
    if len(hits) > 1:
        city_hits = [h for h in hits if h.rsplit("/", 1)[-1].lower() == needle]
        if len(city_hits) == 1:
            name = city_hits[0]
            return ResolvedZone(key=name, tz=ZoneInfo(name))
        sample = ", ".join(sorted(hits)[:8])
        more = f" (+{len(hits) - 8} more)" if len(hits) > 8 else ""
        return (
            f"Ambiguous timezone {raw!r}. Candidates include: {sample}{more}. "
            "Pass a more specific IANA name (e.g. Australia/Sydney)."
        )

    return (
        f"Unknown timezone {raw!r}. "
        "Try IANA names (America/New_York), city names (sydney), "
        "or aliases (utc, australia, local)."
    )


def _parse_clock(text: str, *, day: date, tz: tzinfo) -> datetime | None:
    """Parse HH:MM[:SS][am/pm] into an aware datetime on *day* in *tz*."""
    match = _CLOCK_RE.match(text.strip())
    if match is None:
        return None
    hour = int(match.group("h"))
    minute = int(match.group("m") or 0)
    second = int(match.group("s") or 0)
    ampm = match.group("ampm")
    if ampm is not None:
        suffix = ampm.lower()
        if hour < 1 or hour > 12:
            return None
        if suffix == "am":
            hour = 0 if hour == 12 else hour
        elif hour != 12:
            hour = hour + 12
    elif hour > 23:
        return None
    if minute > 59 or second > 59:
        return None
    return datetime.combine(day, time(hour, minute, second), tzinfo=tz)


def _parse_unix_timestamp(text: str) -> tuple[datetime, str] | None:
    """Parse a Unix epoch string as UTC.

    Accepts 9-10 digit seconds or 13 digit milliseconds, optional ``unix:`` /
    ``epoch:`` prefix or ``s`` / ``ms`` suffix.
    """
    match = _UNIX_TS_RE.match(text.strip().lower())
    if match is None:
        return None
    digits = match.group("n")
    lowered = text.strip().lower()
    explicit_ms = bool(re.search(r"(?:^|[\s:])ms\b", lowered) or lowered.endswith("ms"))
    as_ms = explicit_ms or len(digits) >= 13
    try:
        value = int(digits)
    except ValueError:
        return None
    seconds = value / 1000.0 if as_ms else float(value)
    if seconds < 1_000_000_000 or seconds > 10_000_000_000:
        return None
    dt = datetime.fromtimestamp(seconds, tz=UTC)
    unit = "milliseconds" if as_ms else "seconds"
    note = f"Interpreted {digits} as Unix epoch {unit} (UTC)."
    return dt, note


def parse_when(
    when: str | None,
    *,
    from_tz: tzinfo,
    now: datetime | None = None,
) -> datetime | tuple[datetime, str] | str:
    """Parse a free-text instant in *from_tz*.

    Returns an aware datetime, ``(datetime, assumption_note)`` for Unix epoch
    inputs, or an error string.
    """
    instant = now or datetime.now(tz=from_tz)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=from_tz)
    else:
        instant = instant.astimezone(from_tz)

    raw = (when or "").strip()
    if not raw or raw.lower() in {"now", "rn", "right now"}:
        return instant

    unix = _parse_unix_timestamp(raw)
    if unix is not None:
        return unix

    iso_candidate = raw.replace("Z", "+00:00").replace("z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=from_tz)
        return parsed

    space_match = _SPACE_DT_RE.match(raw)
    if space_match is not None:
        rebuilt = (
            f"{space_match.group('date')}T{space_match.group('time')}"
            f"{space_match.group('frac') or ''}"
            f"{space_match.group('tz') or ''}"
        )
        rebuilt = rebuilt.replace("Z", "+00:00").replace("z", "+00:00")
        try:
            parsed = datetime.fromisoformat(rebuilt)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=from_tz)
            return parsed

    clock = _parse_clock(raw, day=instant.date(), tz=from_tz)
    if clock is not None:
        return clock

    return (
        f"Could not parse time {raw!r}. "
        "Use now, a Unix timestamp (1752386400), ISO-8601 "
        "(2026-07-13T15:30:00Z), YYYY-MM-DD HH:MM, or a clock like 15:30 / 3:30pm."
    )


def _relative_to_now(instant: datetime, *, now: datetime) -> str:
    """Return a short past/future verdict for *instant* vs *now*."""
    delta = int((instant - now).total_seconds())
    abs_delta = abs(delta)
    if abs_delta < 60:
        unit, amount = "s", abs_delta
    elif abs_delta < 3600:
        unit, amount = "m", abs_delta // 60
    elif abs_delta < 86400:
        unit, amount = "h", abs_delta // 3600
    else:
        unit, amount = "d", abs_delta // 86400
    if delta < 0:
        return f"in the past (~{amount}{unit} ago)"
    if delta == 0:
        return "exactly now"
    return f"in the future (in ~{amount}{unit})"


def _format_dt(dt: datetime) -> str:
    """Format an aware datetime for tool output."""
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    offset = aware.strftime("%z")
    if offset and len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    zone = _zone_key(aware.tzinfo) if aware.tzinfo is not None else "UTC"
    return f"{aware.strftime('%Y-%m-%d %H:%M:%S')} {offset} ({zone})\nISO: {aware.isoformat()}"


def _render_now(instant: datetime) -> str:
    """Render date / time / full datetime for local and UTC."""
    local = instant.astimezone()
    utc = instant.astimezone(UTC)
    local_key = _zone_key(local.tzinfo) if local.tzinfo is not None else "local"
    lines = [
        "## Current date/time",
        "",
        f"- **Local timezone:** {local_key}",
        f"- **Local date:** {local.strftime('%Y-%m-%d')} ({local.strftime('%A')})",
        f"- **Local time:** {local.strftime('%H:%M:%S')} "
        f"({local.strftime('%z')[:3]}:{local.strftime('%z')[3:]})",
        f"- **Local full:** {_format_dt(local).splitlines()[0]}",
        f"- **UTC full:** {_format_dt(utc).splitlines()[0]}",
        f"- **Local ISO:** {local.isoformat()}",
        f"- **UTC ISO:** {utc.isoformat()}",
        f"- **Unix (UTC seconds):** {int(utc.timestamp())}",
    ]
    return "\n".join(lines)


def _render_convert(
    source: datetime,
    source_zone: ResolvedZone,
    target_zone: ResolvedZone,
    *,
    when_raw: str | None,
    from_tz_raw: str | None,
    now: datetime,
    extra_notes: list[str] | None = None,
) -> str:
    """Render a timezone conversion observation."""
    target = source.astimezone(target_zone.tz)
    assumptions: list[str] = list(extra_notes or [])
    if not (from_tz_raw or "").strip() and not any(
        n.startswith("Interpreted ") for n in assumptions
    ):
        assumptions.append("Source timezone omitted — assumed local OS timezone.")
    if not (when_raw or "").strip() or (when_raw or "").strip().lower() in {
        "now",
        "rn",
        "right now",
    }:
        assumptions.append("Time omitted or 'now' — used the current instant.")
    if source_zone.note:
        assumptions.append(source_zone.note)
    if target_zone.note:
        assumptions.append(target_zone.note)

    relative = _relative_to_now(source, now=now)
    lines = [
        "## Timezone conversion",
        "",
        f"**Source** ({source_zone.key}):",
        _format_dt(source),
        "",
        f"**Target** ({target_zone.key}):",
        _format_dt(target),
        "",
        f"**Relative to now:** {relative}",
        f"**Unix (UTC seconds):** {int(source.timestamp())}",
    ]
    if assumptions:
        lines.extend(["", "**Assumptions:**"])
        lines.extend(f"- {a}" for a in assumptions)
    return "\n".join(lines)


def execute_datetime_query(
    operation: Operation,
    *,
    when: str | None = None,
    from_tz: str | None = None,
    to_tz: str | None = None,
    now: datetime | None = None,
) -> str:
    """Run a datetime tool query and return markdown text."""
    clock = now or datetime.now().astimezone()
    if operation == "now":
        return _render_now(clock)

    if operation != "convert":
        return f"Unknown operation {operation!r}. Use 'now' or 'convert'."

    if not (to_tz or "").strip():
        return "Error: convert requires ``to_tz`` (e.g. 'UTC', 'Australia', 'America/New_York')."

    looks_unix = _parse_unix_timestamp((when or "").strip()) is not None
    effective_from = from_tz
    if looks_unix and not (from_tz or "").strip():
        effective_from = "UTC"

    source_resolved = resolve_zone(effective_from)
    if isinstance(source_resolved, str):
        return f"Error: {source_resolved}"
    target_resolved = resolve_zone(to_tz)
    if isinstance(target_resolved, str):
        return f"Error: {target_resolved}"

    parsed = parse_when(when, from_tz=source_resolved.tz, now=clock)
    extra_notes: list[str] = []
    if isinstance(parsed, str):
        return f"Error: {parsed}"
    if isinstance(parsed, tuple):
        source_dt, note = parsed
        extra_notes.append(note)
        source_resolved = ResolvedZone(key="UTC", tz=UTC, note=source_resolved.note)
    else:
        source_dt = parsed

    return _render_convert(
        source_dt,
        source_resolved,
        target_resolved,
        when_raw=when,
        from_tz_raw=from_tz,
        now=clock,
        extra_notes=extra_notes,
    )
