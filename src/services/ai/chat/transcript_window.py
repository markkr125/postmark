"""Turn-aware transcript window slicing for virtualized AI chat loads."""

from __future__ import annotations

from typing import Any

INITIAL_TAIL_TURNS = 6
OLDER_PAGE_TURNS = 4
NEWER_PAGE_TURNS = 4
EVICTION_BUFFER_TURNS = 8
TOP_PREFETCH_MARGIN_PX = 400
BOTTOM_PREFETCH_MARGIN_PX = 120
SCROLL_TOP_PREFETCH_THRESHOLD_PX = 200
TOP_PREFETCH_VIEWPORT_FRACTION = 0.55
SCROLL_TOP_VIEWPORT_FRACTION = 0.2


def _is_user_message(message: dict[str, Any]) -> bool:
    return message.get("role") == "user"


def slice_tail_messages(
    messages: list[dict[str, Any]],
    *,
    tail_turns: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return the trailing *tail_turns* user turns plus any trailing user-only row."""
    if not messages or tail_turns <= 0:
        return [], bool(messages)
    user_indices = [index for index, message in enumerate(messages) if _is_user_message(message)]
    if not user_indices:
        return list(messages), False
    if len(user_indices) <= tail_turns:
        return list(messages), False
    start_user_index = user_indices[-tail_turns]
    return messages[start_user_index:], True


def slice_older_messages(
    messages: list[dict[str, Any]],
    *,
    before_id: int,
    page_turns: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return up to *page_turns* complete user turns ending before *before_id*."""
    if page_turns <= 0:
        return [], False
    before_index = next(
        (index for index, message in enumerate(messages) if message["id"] == before_id), None
    )
    if before_index is None:
        return [], False
    prefix = messages[:before_index]
    if not prefix:
        return [], False
    user_indices = [index for index, message in enumerate(prefix) if _is_user_message(message)]
    if not user_indices:
        return list(prefix), False
    if len(user_indices) <= page_turns:
        return list(prefix), False
    start_user_index = user_indices[-page_turns]
    return prefix[start_user_index:], True


def slice_newer_messages(
    messages: list[dict[str, Any]],
    *,
    after_id: int,
    page_turns: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Return up to *page_turns* user turns starting after *after_id*."""
    if page_turns <= 0:
        return [], False
    after_index = next(
        (index for index, message in enumerate(messages) if message["id"] == after_id), None
    )
    if after_index is None:
        return [], False
    suffix = messages[after_index + 1 :]
    if not suffix:
        return [], False
    user_indices = [index for index, message in enumerate(suffix) if _is_user_message(message)]
    if not user_indices:
        return list(suffix), False
    if len(user_indices) <= page_turns:
        return list(suffix), False
    next_user_after_page = (
        user_indices[page_turns] if len(user_indices) > page_turns else len(suffix)
    )
    return suffix[:next_user_after_page], True


def message_limit_for_turns(turns: int) -> int:
    """Upper-bound message count for *turns* user boundaries (user + assistant pairs)."""
    return max(turns * 2 + 2, 2)


def turn_ids_from_messages(messages: list[dict[str, Any]]) -> list[int]:
    """Return user message ids in chronological order."""
    return [int(message["id"]) for message in messages if _is_user_message(message)]
