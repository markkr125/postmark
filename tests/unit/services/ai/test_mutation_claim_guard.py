"""Tests for the unverified workspace-write claim guard."""

from __future__ import annotations

import pytest

from services.ai.chat.mutation.claim_guard import (
    UNVERIFIED_WRITE_NOTE,
    claims_workspace_write,
    collection_ids_in_observation,
    observation_indicates_write,
    observation_records_write,
    strip_unbacked_collection_links,
    unverified_write_note,
)
from services.ai.chat.mutation.write_ledger import (
    clear_workspace_writes,
    record_collection_ids,
    record_workspace_write,
    take_collection_ids,
    take_workspace_write,
)

# The message the assistant actually produced when it delegated the import to a
# wiki-researcher and imported nothing.
_REAL_FABRICATED_MESSAGE = (
    "✅ The OpenAPI file has been imported.\n"
    "Four collections were created, containing eight requests in total.\n"
    "You can find them on the left-hand side of the UI."
)

_DRAFT_TOOL = "postmark_collection_draft"
_IMPORT_TOOL = "postmark_import"
_QUERY_TOOL = "postmark_workspace_query"

# Verbatim finish observation from conversation 5d197805 (collection 723).
_REAL_DRAFT_FINISH_OBSERVATION = (
    "ok: true\n"
    "mutation_id: cfc4e73ebb8a\n"
    "summary: Created collection 'Agoda Standard Pull Spec v1.34 (5) (1)' "
    "with 7 request(s)\n"
    "action: create\n"
    "entity: import\n"
    "collections_imported: 1\n"
    "requests_imported: 7\n"
    "imported_collections: [{'id': 723, 'name': "
    "'Agoda Standard Pull Spec v1.34 (5) (1)'}]\n"
    "collection_links: "
    "['[Agoda Standard Pull Spec v1.34 (5) (1)](postmark://collection/723)']\n"
    "next_step: The collection exists. Reply using the collection_links label "
    "above; never invent a collection id or link.\n"
)

_REAL_DRAFT_START_OBSERVATION = (
    "ok: true\ndraft: Agoda Standard Pull Spec v1.34 (5) (1)\nrequests: 0\n"
    "note: This draft supersedes any earlier import in this chat. Build it only "
    "from the document you are reading now.\n"
    "next_step: call operation=add_requests with a requests array, then "
    "operation=finish. JSON bodies must be objects or arrays, not encoded strings.\n"
)

_REAL_DRAFT_ADD_OBSERVATION = "ok: true\nadded: ['GET Get Booking Details']\nrequests: 1\n"

_REAL_FINAL_MESSAGE = (
    "I've created the collection: "
    "[Agoda Standard Pull Spec v1.34 (5) (1)](postmark://collection/723)"
)


@pytest.mark.parametrize(
    "content",
    [
        _REAL_FABRICATED_MESSAGE,
        "The OpenAPI file has been imported.",
        "I've imported the spec for you.",
        "I have imported it.",
        "Imported 4 collections and 8 requests.",
        "Four collections were created.",
        "2 collections were created.",
        "I created the Hotel Booking API collection.",
        "I've created a new collection for you.",
    ],
)
def test_claims_workspace_write_detects_completed_claims(content: str) -> None:
    """Past-tense import/create claims are detected."""
    assert claims_workspace_write(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "To import an OpenAPI spec, click File > Import and choose the file.",
        "You can import a collection via the Import button in the sidebar.",
        "Would you like me to import it?",
        "I'll import it now.",
        "I can create a collection from that spec if you'd like.",
        "The import failed — the host was unreachable.",
        "If you import this file, four collections will be created.",
        "Switch the mode pill to Agent so I can import it.",
        "",
    ],
)
def test_claims_workspace_write_ignores_non_claims(content: str) -> None:
    """How-to, forward-looking, and failure text must not be treated as a claim."""
    assert claims_workspace_write(content) is False


def test_unverified_note_returned_when_claim_unbacked() -> None:
    """A claim with no observed write is flagged."""
    assert (
        unverified_write_note(_REAL_FABRICATED_MESSAGE, write_observed=False)
        == UNVERIFIED_WRITE_NOTE
    )


def test_no_note_when_write_actually_observed() -> None:
    """A claim backed by a real write tool run is not flagged."""
    assert unverified_write_note(_REAL_FABRICATED_MESSAGE, write_observed=True) is None


def test_no_note_without_a_claim() -> None:
    """A read-only answer is never flagged, even with no writes."""
    assert (
        unverified_write_note(
            "To import an OpenAPI spec, click File > Import.", write_observed=False
        )
        is None
    )


# Verbatim observation text produced by a real unreachable-URL import. Note it
# reports ok: true — ImportService swallows the fetch error into `errors` — so the
# zero counts are the only signal that nothing was written.
_REAL_FAILED_IMPORT_OBSERVATION = (
    "ok: true\n"
    "mutation_id: 16761b307448\n"
    "summary: Imported 0 collection(s), 0 request(s), 0 environment(s)\n"
    "action: create\n"
    "entity: import\n"
    "collections_imported: 0\n"
    "requests_imported: 0\n"
    "environments_imported: 0\n"
    "errors: ['Failed to fetch URL: <urlopen error [Errno 111] Connection refused>']\n"
)

_REAL_OK_IMPORT_OBSERVATION = (
    "ok: true\n"
    "mutation_id: 26f892d6ac66\n"
    "summary: Imported 4 collection(s), 8 request(s), 0 environment(s)\n"
    "action: create\n"
    "entity: import\n"
    "collections_imported: 4\n"
    "requests_imported: 8\n"
    "environments_imported: 0\n"
    "imported_collections: [{'id': 1, 'name': 'Hotel Booking API'}]\n"
    "deep_links: ['postmark://collection/1']\n"
)


class TestObservationIndicatesWrite:
    """Only a genuinely successful write counts as a write."""

    def test_real_successful_import_is_a_write(self) -> None:
        """A real successful import observation counts."""
        assert observation_indicates_write(_REAL_OK_IMPORT_OBSERVATION) is True

    def test_real_failed_url_import_is_not_a_write(self) -> None:
        """ok: true with all-zero counts (unreachable URL) is not a write."""
        assert observation_indicates_write(_REAL_FAILED_IMPORT_OBSERVATION) is False

    def test_ok_false_is_not_a_write(self) -> None:
        """An explicit tool-level failure is not a write."""
        text = "ok: false\nerror: IntegrityError\nmessage: UNIQUE constraint failed\n"
        assert observation_indicates_write(text) is False

    def test_environment_only_import_is_a_write(self) -> None:
        """Zero collections but a real environment import still counts."""
        text = "ok: true\ncollections_imported: 0\nrequests_imported: 0\nenvironments_imported: 1\n"
        assert observation_indicates_write(text) is True

    def test_unknown_shape_counts_as_write(self) -> None:
        """Unrecognised output must never mislabel a real change as fabricated."""
        assert observation_indicates_write("sent GET https://example.com -> 200") is True
        assert observation_indicates_write("") is True
        assert observation_indicates_write("ok: true\nmutation_id: abc\n") is True

    def test_failed_import_with_fabricated_claim_is_flagged(self) -> None:
        """The tightened case: import ran, wrote nothing, model claims success."""
        write_observed = observation_indicates_write(_REAL_FAILED_IMPORT_OBSERVATION)
        assert (
            unverified_write_note(_REAL_FABRICATED_MESSAGE, write_observed=write_observed)
            == UNVERIFIED_WRITE_NOTE
        )

    def test_successful_import_with_claim_is_not_flagged(self) -> None:
        """A real import backing the claim must never be flagged."""
        write_observed = observation_indicates_write(_REAL_OK_IMPORT_OBSERVATION)
        assert (
            unverified_write_note(_REAL_FABRICATED_MESSAGE, write_observed=write_observed) is None
        )


class TestObservationRecordsWrite:
    """Write-ledger membership uses the shared tool predicate + draft finish gate."""

    def test_draft_finish_records_a_write(self) -> None:
        """A successful draft finish is the observation that creates the collection."""
        assert observation_records_write(_DRAFT_TOOL, _REAL_DRAFT_FINISH_OBSERVATION) is True
        assert collection_ids_in_observation(_REAL_DRAFT_FINISH_OBSERVATION) == {723}

    def test_draft_start_does_not_record(self) -> None:
        """Staging a draft must not silence the unverified-write guard."""
        assert observation_records_write(_DRAFT_TOOL, _REAL_DRAFT_START_OBSERVATION) is False

    def test_draft_add_requests_does_not_record(self) -> None:
        """Adding requests only mutates in-memory draft state."""
        assert observation_records_write(_DRAFT_TOOL, _REAL_DRAFT_ADD_OBSERVATION) is False

    def test_import_still_records(self) -> None:
        """postmark_import success continues to count."""
        assert observation_records_write(_IMPORT_TOOL, _REAL_OK_IMPORT_OBSERVATION) is True

    def test_read_only_tool_does_not_record(self) -> None:
        """Workspace query must never enter the write ledger."""
        assert observation_records_write(_QUERY_TOOL, "ok: true\ncollections: 3\n") is False

    def test_draft_finish_ok_false_does_not_record(self) -> None:
        """A failed finish (with mutation_id absent or ok: false) is not a write."""
        failed = "ok: false\nerror: draft_empty\nhint: Add at least one request.\n"
        assert observation_records_write(_DRAFT_TOOL, failed) is False
        failed_with_id = "ok: false\nmutation_id: deadbeef\nerror: IntegrityError\nmessage: boom\n"
        assert observation_records_write(_DRAFT_TOOL, failed_with_id) is False

    def test_draft_finish_zero_counts_does_not_record(self) -> None:
        """All-zero import counts mean nothing was persisted."""
        zero = (
            "ok: true\n"
            "mutation_id: deadbeef\n"
            "collections_imported: 0\n"
            "requests_imported: 0\n"
            "environments_imported: 0\n"
        )
        assert observation_records_write(_DRAFT_TOOL, zero) is False

    def test_finish_turn_does_not_flag_or_strip_real_link(self) -> None:
        """End-to-end: finish observation backs the claim and keeps the real link."""
        session = "draft-finish-session"
        clear_workspace_writes(session)
        if observation_records_write(_DRAFT_TOOL, _REAL_DRAFT_FINISH_OBSERVATION):
            record_workspace_write(session)
            record_collection_ids(
                session, collection_ids_in_observation(_REAL_DRAFT_FINISH_OBSERVATION)
            )
        assert take_workspace_write(session) is True
        produced = take_collection_ids(session)
        assert produced == {723}
        assert unverified_write_note(_REAL_FINAL_MESSAGE, write_observed=True) is None
        cleaned, stripped = strip_unbacked_collection_links(_REAL_FINAL_MESSAGE, produced)
        assert stripped is False
        assert "postmark://collection/723" in cleaned

    def test_claim_after_only_start_still_flagged(self) -> None:
        """Guard stays intact when the model claims create after only staging."""
        session = "draft-start-only-session"
        clear_workspace_writes(session)
        for text in (_REAL_DRAFT_START_OBSERVATION, _REAL_DRAFT_ADD_OBSERVATION):
            if observation_records_write(_DRAFT_TOOL, text):
                record_workspace_write(session)
        assert take_workspace_write(session) is False
        assert (
            unverified_write_note(_REAL_FINAL_MESSAGE, write_observed=False)
            == UNVERIFIED_WRITE_NOTE
        )


class TestWriteLedger:
    """Cross-thread write ledger consumed by turn finalize."""

    def test_record_then_take_is_true_once(self) -> None:
        """take() reports the write and clears it, so it cannot leak to next turn."""
        clear_workspace_writes("s1")
        record_workspace_write("s1")
        assert take_workspace_write("s1") is True
        assert take_workspace_write("s1") is False

    def test_take_without_record_is_false(self) -> None:
        """A turn with no write reports False."""
        clear_workspace_writes("s2")
        assert take_workspace_write("s2") is False

    def test_sessions_are_isolated(self) -> None:
        """One session's write must not mark another."""
        clear_workspace_writes("s3")
        clear_workspace_writes("s4")
        record_workspace_write("s3")
        assert take_workspace_write("s4") is False
        assert take_workspace_write("s3") is True
