"""OpenHands tool — current date/time and timezone conversion."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Self

from pydantic import Field
from rich.text import Text

from openhands.sdk.tool.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
)
from services.ai.chat.tools.datetime_query.ops import Operation, execute_datetime_query

if TYPE_CHECKING:
    from openhands.sdk.conversation.base import BaseConversation


class DateTimeAction(Action):
    """Action for current date/time or timezone conversion."""

    operation: Operation = Field(
        description=(
            "Use 'now' for current local/UTC date and time. "
            "Use 'convert' to convert a time between timezones."
        ),
    )
    when: str | None = Field(
        default=None,
        description=(
            "For convert: free-text instant — 'now'/'rn', Unix epoch seconds "
            "(e.g. 1752386400 or unix:1752386400), ISO-8601, "
            "'YYYY-MM-DD HH:MM', or clock '15:30' / '3:30pm'. "
            "Unix timestamps are always UTC. "
            "Omit or 'now' for the current instant. Ignored for operation=now."
        ),
    )
    from_tz: str | None = Field(
        default=None,
        description=(
            "Source timezone free text (IANA, city, or alias like utc/australia). "
            "Omit to assume the OS local timezone. Ignored for operation=now."
        ),
    )
    to_tz: str | None = Field(
        default=None,
        description=(
            "Target timezone free text (required for convert). "
            "Accepts IANA names, cities (sydney), or aliases (australia, utc)."
        ),
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text for the action."""
        content = Text()
        content.append("Datetime: ", style="bold cyan")
        content.append(self.operation, style="white")
        if self.operation == "convert":
            bits = []
            if self.when:
                bits.append(f"when={self.when}")
            if self.from_tz:
                bits.append(f"from={self.from_tz}")
            if self.to_tz:
                bits.append(f"to={self.to_tz}")
            if bits:
                content.append(f" ({', '.join(bits)})", style="dim")
        return content


class DateTimeObservation(Observation):
    """Observation with date/time or conversion result."""


DATETIME_QUERY_DESCRIPTION = """Get the current date/time or convert between timezones.

ALWAYS call this tool for wall-clock questions — never invent the current date,
time, timezone offsets, or Unix-epoch calendar math from memory. Never convert
timestamps by mental arithmetic; pass them to this tool.

Operations:
- ``now`` — returns local date, local time, full local datetime (with offset),
  UTC equivalents, and Unix seconds.
- ``convert`` — convert ``when`` from ``from_tz`` to ``to_tz``. The observation
  includes whether the instant is in the past or future relative to now.

Free-text zones are supported (e.g. utc, australia, sydney, America/New_York,
local). If ``from_tz`` is omitted, assume the OS local timezone (except Unix
epoch values, which are always UTC). If ``when`` is omitted or 'now'/'rn', use
the current instant. Ambiguous regions (e.g. australia) resolve to a documented
default and the observation states the assumption.

Examples:
- What time is it? → operation=now
- Convert 15:30 UTC to Australia → operation=convert, when=15:30, from_tz=UTC,
  to_tz=Australia
- Time in Tokyo right now from local → operation=convert, when=now, to_tz=Tokyo
- Convert Unix 1752386400 to local and is it past? → operation=convert,
  when=1752386400, from_tz=UTC, to_tz=local
"""


class DateTimeExecutor(ToolExecutor):
    """Read-only executor for datetime queries."""

    def __call__(
        self,
        action: DateTimeAction,
        _conversation: BaseConversation | None = None,
    ) -> DateTimeObservation:
        """Run the datetime query and return markdown."""
        text = execute_datetime_query(
            action.operation,
            when=action.when,
            from_tz=action.from_tz,
            to_tz=action.to_tz,
        )
        return DateTimeObservation.from_text(text)


class PostmarkDateTimeTool(ToolDefinition[DateTimeAction, DateTimeObservation]):
    """Postmark datetime / timezone conversion tool."""

    @classmethod
    def create(
        cls,
        conv_state: object | None = None,
        **params: object,
    ) -> Sequence[Self]:
        """Create a single datetime tool instance.

        ``conv_state`` is passed positionally/by-keyword by the OpenHands tool
        registry; the parameter name must stay ``conv_state`` so the registry's
        ``create(conv_state=...)`` call binds here instead of landing in
        ``**params``.
        """
        del conv_state
        if params:
            msg = "postmark_datetime does not accept parameters"
            raise ValueError(msg)
        return [
            cls(
                description=DATETIME_QUERY_DESCRIPTION,
                action_type=DateTimeAction,
                observation_type=DateTimeObservation,
                executor=DateTimeExecutor(),
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        ]


def register_datetime_query_tool() -> None:
    """Register ``postmark_datetime`` with Postmark and OpenHands."""
    from services.ai.chat.tool_registry import register_postmark_tool

    register_postmark_tool("postmark_datetime", PostmarkDateTimeTool)
