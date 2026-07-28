"""Tests for stripping collection links a turn never actually created."""

from __future__ import annotations

from services.ai.chat.mutation.claim_guard import (
    collection_ids_in_observation,
    strip_unbacked_collection_links,
)
from services.ai.chat.mutation.write_ledger import (
    clear_workspace_writes,
    record_collection_ids,
    take_collection_ids,
)

_SESSION = "00000000-0000-4000-8000-00000000f00d"


def test_real_link_survives() -> None:
    """A link the turn produced must never be touched."""
    text = "Done: [Agoda Spec](postmark://collection/717)"
    cleaned, stripped = strip_unbacked_collection_links(text, {717})
    assert cleaned == text
    assert stripped is False


def test_fabricated_link_is_reduced_to_its_label() -> None:
    """An invented link can land on an unrelated collection, so it must go.

    This is the exact failure seen in the field: the model reused an id from an
    earlier turn, and the link opened a different collection entirely.
    """
    text = "You can open it here: [Agoda Standard Pull Spec 11](postmark://collection/717)"
    cleaned, stripped = strip_unbacked_collection_links(text, set())
    assert stripped is True
    assert "postmark://collection/717" not in cleaned
    assert "Agoda Standard Pull Spec 11" in cleaned


def test_bare_uri_is_removed_too() -> None:
    """A raw URI outside markdown is just as clickable and just as wrong."""
    cleaned, stripped = strip_unbacked_collection_links("see postmark://collection/9", set())
    assert stripped is True
    assert "postmark://collection/9" not in cleaned


def test_mixed_links_keep_only_the_backed_one() -> None:
    """Stripping must be per-id, not all-or-nothing."""
    text = "[Real](postmark://collection/5) and [Fake](postmark://collection/6)"
    cleaned, stripped = strip_unbacked_collection_links(text, {5})
    assert stripped is True
    assert "postmark://collection/5" in cleaned
    assert "postmark://collection/6" not in cleaned


def test_text_without_links_is_untouched() -> None:
    """Ordinary answers must pass through unchanged."""
    cleaned, stripped = strip_unbacked_collection_links("no links here", set())
    assert cleaned == "no links here"
    assert stripped is False


def test_ids_are_read_from_a_successful_observation() -> None:
    """Backed ids come from the tool output, which the model cannot forge."""
    observation = (
        "ok: true\ncollections_imported: 1\nrequests_imported: 4\n"
        "collection_links: ['[Spec](postmark://collection/42)']\n"
    )
    assert collection_ids_in_observation(observation) == {42}


def test_failed_observation_backs_no_ids() -> None:
    """A failed import must not license a link, even if it mentions one."""
    observation = "ok: false\nerror: boom\npostmark://collection/42\n"
    assert collection_ids_in_observation(observation) == set()


def test_zero_count_import_backs_no_ids() -> None:
    """ImportService reports ok: true with zero counts when parsing failed."""
    observation = (
        "ok: true\ncollections_imported: 0\nrequests_imported: 0\n"
        "environments_imported: 0\npostmark://collection/42\n"
    )
    assert collection_ids_in_observation(observation) == set()


def test_ledger_round_trips_ids_per_turn() -> None:
    """The worker records ids; the GUI thread consumes them exactly once."""
    clear_workspace_writes(_SESSION)
    record_collection_ids(_SESSION, {1, 2})
    assert take_collection_ids(_SESSION) == {1, 2}
    assert take_collection_ids(_SESSION) == set()


def test_clearing_a_turn_drops_stale_ids() -> None:
    """Ids from a previous turn must not authorise links in the next one."""
    record_collection_ids(_SESSION, {99})
    clear_workspace_writes(_SESSION)
    assert take_collection_ids(_SESSION) == set()
