"""Tests for mutation GUI bridge enqueue/drain."""

from __future__ import annotations

from services.ai.chat.mutation.bridge import (
    clear_mutation_events,
    drain_mutation_events,
    enqueue_mutation_event,
)


class TestMutationBridge:
    """Thread-safe queue for mutate/execute GUI side effects."""

    def setup_method(self) -> None:
        """Drop any leftover events between cases."""
        clear_mutation_events()

    def teardown_method(self) -> None:
        """Leave the queue empty after each case."""
        clear_mutation_events()

    def test_enqueue_then_drain(self) -> None:
        """Drain returns queued events in order and clears the queue."""
        enqueue_mutation_event(
            {
                "type": "mutated",
                "entity": "collection",
                "action": "create",
                "ids": {"collection_id": 1},
            }
        )
        enqueue_mutation_event(
            {
                "type": "open_target",
                "open_target": {"kind": "collection", "id": 1},
            }
        )
        events = drain_mutation_events()
        assert len(events) == 2
        assert events[0]["type"] == "mutated"
        assert events[1]["type"] == "open_target"
        assert drain_mutation_events() == []

    def test_clear_drops_pending(self) -> None:
        """clear_mutation_events discards without returning."""
        enqueue_mutation_event({"type": "executed", "action": "send_request"})
        clear_mutation_events()
        assert drain_mutation_events() == []
