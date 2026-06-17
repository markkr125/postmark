"""Budget period window helpers for provider spend rollups."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from services.ai.ai_budget_config import BudgetPeriod
from services.ai.chat.session_service import AiChatMessageDict

_LOCAL_TZ = datetime.now().astimezone().tzinfo or UTC
_DAILY_REFERENCE_DATE = date(2000, 1, 1)


@dataclass(frozen=True)
class PeriodReset:
    """Local reset schedule encoded in ``period_anchor``."""

    anchor_date: date
    hour: int
    minute: int


def parse_period_reset(value: str | None) -> PeriodReset | None:
    """Parse ``YYYY-MM-DD`` or ``YYYY-MM-DDTHH:MM`` anchor text."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        try:
            anchor_date = date.fromisoformat(date_part)
            hour_str, minute_str, *_rest = f"{time_part}:00".split(":")
            hour = int(hour_str)
            minute = int(minute_str)
        except ValueError:
            return None
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        return PeriodReset(anchor_date=anchor_date, hour=hour, minute=minute)
    try:
        anchor_date = date.fromisoformat(text)
    except ValueError:
        return None
    return PeriodReset(anchor_date=anchor_date, hour=0, minute=0)


def parse_period_anchor(value: str | None) -> date | None:
    """Parse the calendar date portion of one anchor string."""
    reset = parse_period_reset(value)
    return reset.anchor_date if reset is not None else None


def format_period_reset(reset: PeriodReset) -> str:
    """Serialize one reset schedule for QSettings."""
    return f"{reset.anchor_date.isoformat()}T{reset.hour:02d}:{reset.minute:02d}"


def format_period_anchor(anchor: date, *, hour: int = 0, minute: int = 0) -> str:
    """Serialize one anchor date and optional local reset time."""
    return format_period_reset(PeriodReset(anchor_date=anchor, hour=hour, minute=minute))


def format_period_reset_label(period: BudgetPeriod, anchor: str | None) -> str:
    """Human-readable reset schedule for the budgets table."""
    if period == "none" or not anchor:
        return ""
    reset = parse_period_reset(anchor)
    if reset is None:
        return ""
    time_label = f"{reset.hour:02d}:{reset.minute:02d}"
    if period == "daily":
        return f"Daily @ {time_label}"
    if period == "weekly":
        day_name = calendar.day_name[reset.anchor_date.weekday()]
        return f"Weekly {day_name} @ {time_label}"
    if period == "monthly":
        return f"Monthly day {reset.anchor_date.day} @ {time_label}"
    if period == "yearly":
        month_name = calendar.month_name[reset.anchor_date.month]
        return f"Yearly {month_name} {reset.anchor_date.day} @ {time_label}"
    return ""


def daily_reset_anchor(*, hour: int, minute: int) -> str:
    """Build the stored anchor for a daily reset (date portion ignored)."""
    return format_period_reset(
        PeriodReset(anchor_date=_DAILY_REFERENCE_DATE, hour=hour, minute=minute)
    )


def weekly_reset_anchor(*, weekday: int, hour: int, minute: int) -> str:
    """Build the stored anchor for a weekly reset."""
    # 2024-01-01 is a Monday (weekday 0).
    base_monday = date(2024, 1, 1)
    anchor_date = base_monday + timedelta(days=weekday % 7)
    return format_period_reset(PeriodReset(anchor_date=anchor_date, hour=hour, minute=minute))


def monthly_reset_anchor(*, day: int, hour: int, minute: int) -> str:
    """Build the stored anchor for a monthly reset."""
    anchor_date = date(2000, 1, min(max(day, 1), 31))
    return format_period_reset(PeriodReset(anchor_date=anchor_date, hour=hour, minute=minute))


def yearly_reset_anchor(*, month: int, day: int, hour: int, minute: int) -> str:
    """Build the stored anchor for a yearly reset."""
    last_day = calendar.monthrange(2000, month)[1]
    anchor_date = date(2000, month, min(max(day, 1), last_day))
    return format_period_reset(PeriodReset(anchor_date=anchor_date, hour=hour, minute=minute))


def _reset_time(reset: PeriodReset) -> time:
    return time(reset.hour, reset.minute)


def _local_bounds(start_local: datetime, end_local: datetime) -> tuple[datetime, datetime]:
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _clamp_day_of_month(year: int, month: int, day: int) -> date:
    """Return *year-month-day* clamped to the month's last day."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _daily_window(reset: PeriodReset, local_now: datetime) -> tuple[datetime, datetime]:
    candidate = datetime.combine(local_now.date(), _reset_time(reset), tzinfo=_LOCAL_TZ)
    if local_now < candidate:
        candidate -= timedelta(days=1)
    end = candidate + timedelta(days=1)
    return _local_bounds(candidate, end)


def _weekly_window(reset: PeriodReset, local_now: datetime) -> tuple[datetime, datetime]:
    target_weekday = reset.anchor_date.weekday()
    days_back = (local_now.date().weekday() - target_weekday) % 7
    candidate = datetime.combine(
        local_now.date() - timedelta(days=days_back),
        _reset_time(reset),
        tzinfo=_LOCAL_TZ,
    )
    if local_now < candidate:
        candidate -= timedelta(days=7)
    end = candidate + timedelta(days=7)
    return _local_bounds(candidate, end)


def _monthly_window(reset: PeriodReset, local_now: datetime) -> tuple[datetime, datetime]:
    anchor_day = reset.anchor_date.day
    year, month = local_now.year, local_now.month
    candidate_date = _clamp_day_of_month(year, month, anchor_day)
    candidate = datetime.combine(candidate_date, _reset_time(reset), tzinfo=_LOCAL_TZ)
    if local_now < candidate:
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1
        candidate_date = _clamp_day_of_month(year, month, anchor_day)
        candidate = datetime.combine(candidate_date, _reset_time(reset), tzinfo=_LOCAL_TZ)
    if month == 12:
        next_date = _clamp_day_of_month(year + 1, 1, anchor_day)
    else:
        next_date = _clamp_day_of_month(year, month + 1, anchor_day)
    end = datetime.combine(next_date, _reset_time(reset), tzinfo=_LOCAL_TZ)
    return _local_bounds(candidate, end)


def _yearly_window(reset: PeriodReset, local_now: datetime) -> tuple[datetime, datetime]:
    anchor_month, anchor_day = reset.anchor_date.month, reset.anchor_date.day
    year = local_now.year
    candidate_date = _clamp_day_of_month(year, anchor_month, anchor_day)
    candidate = datetime.combine(candidate_date, _reset_time(reset), tzinfo=_LOCAL_TZ)
    if local_now < candidate:
        year -= 1
        candidate_date = _clamp_day_of_month(year, anchor_month, anchor_day)
        candidate = datetime.combine(candidate_date, _reset_time(reset), tzinfo=_LOCAL_TZ)
    next_date = _clamp_day_of_month(year + 1, anchor_month, anchor_day)
    end = datetime.combine(next_date, _reset_time(reset), tzinfo=_LOCAL_TZ)
    return _local_bounds(candidate, end)


def period_window(
    period: BudgetPeriod,
    anchor: str | date | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime] | None:
    """Return the active ``[start, end)`` UTC window for *period* at *now*."""
    if period == "none":
        return None
    if isinstance(anchor, date):
        reset: PeriodReset | None = PeriodReset(anchor_date=anchor, hour=0, minute=0)
    else:
        reset = parse_period_reset(anchor if isinstance(anchor, str) else None)
    if reset is None:
        return None

    instant = now or datetime.now(tz=UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    local_now = instant.astimezone(_LOCAL_TZ)

    if period == "daily":
        return _daily_window(reset, local_now)
    if period == "weekly":
        return _weekly_window(reset, local_now)
    if period == "monthly":
        return _monthly_window(reset, local_now)
    if period == "yearly":
        return _yearly_window(reset, local_now)
    return None


def message_created_at_utc(msg: AiChatMessageDict) -> datetime | None:
    """Parse ``created_at`` ISO text from one message dict."""
    raw = msg.get("created_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def message_in_window(msg: AiChatMessageDict, window: tuple[datetime, datetime] | None) -> bool:
    """Return whether *msg* falls inside *window* (or always when window is ``None``)."""
    if window is None:
        return True
    created = message_created_at_utc(msg)
    if created is None:
        return False
    start, end = window
    return start <= created < end


__all__ = [
    "PeriodReset",
    "daily_reset_anchor",
    "format_period_anchor",
    "format_period_reset",
    "format_period_reset_label",
    "message_created_at_utc",
    "message_in_window",
    "monthly_reset_anchor",
    "parse_period_anchor",
    "parse_period_reset",
    "period_window",
    "weekly_reset_anchor",
    "yearly_reset_anchor",
]
