"""Tests for subagent event parsing."""

from __future__ import annotations

from services.ai.chat.subagent_events import SubagentEventTracker, records_for_turn_events


class TaskAction:
    """Minimal TaskAction stand-in for event parsing tests."""

    def __init__(self, **kw: object) -> None:
        """Initialize stand-in task action fields."""
        self.description = kw.get("description")
        self.prompt = kw.get("prompt")
        self.subagent_type = kw.get("subagent_type", "wiki-researcher")
        self.resume = kw.get("resume")


class TaskObservation:
    """Minimal TaskObservation stand-in for event parsing tests."""

    def __init__(self, **kw: object) -> None:
        """Initialize stand-in task observation fields."""
        self.task_id = kw.get("task_id", "task_00000001")
        self.subagent = kw.get("subagent", "wiki-researcher")
        self.status = kw.get("status", "completed")
        self.is_error = kw.get("is_error", False)
        self.text = kw.get("text", "Found wiki page.")
        self.content: list[object] = []


class DelegateAction:
    """Minimal DelegateAction stand-in for event parsing tests."""

    def __init__(self, command: str, **kw: object) -> None:
        """Initialize stand-in delegate action fields."""
        self.command = command
        for key, value in kw.items():
            setattr(self, key, value)


class DelegateObservation:
    """Minimal DelegateObservation stand-in for event parsing tests."""

    def __init__(self, command: str, **kw: object) -> None:
        """Initialize stand-in delegate action fields."""
        self.command = command
        for key, value in kw.items():
            setattr(self, key, value)


class ActionEvent:
    """Minimal ActionEvent stand-in for event parsing tests."""

    def __init__(self, tool_name: str, action: object, tool_call_id: str = "tc1") -> None:
        """Initialize stand-in action event fields."""
        self.tool_name = tool_name
        self.action = action
        self.tool_call_id = tool_call_id


class ObservationEvent:
    """Minimal ObservationEvent stand-in for event parsing tests."""

    def __init__(self, tool_name: str, observation: object, tool_call_id: str = "tc1") -> None:
        """Initialize stand-in observation event fields."""
        self.tool_name = tool_name
        self.observation = observation
        self.tool_call_id = tool_call_id


class WikiQueryAction:
    """Minimal WikiQueryAction stand-in for event parsing tests."""

    def __init__(self, query: str) -> None:
        """Initialize stand-in wiki action fields."""
        self.query = query


class WikiQueryObservation:
    """Minimal WikiQueryObservation stand-in for event parsing tests."""

    def __init__(self, *, text: str = "", is_error: bool = False) -> None:
        """Initialize stand-in wiki observation fields."""
        self.text = text
        self.is_error = is_error
        self.content: list[object] = []


def test_wiki_action_and_observation_lifecycle() -> None:
    """Inline wiki lookups produce wiki-researcher cards."""
    tracker = SubagentEventTracker()
    started = tracker.ingest(
        ActionEvent(
            "postmark_wiki_query",
            WikiQueryAction("how to send request"),
            tool_call_id="wiki_tc",
        )
    )
    assert len(started) == 1
    assert started[0]["kind"] == "wiki"
    assert started[0]["status"] == "running"
    assert started[0]["subagent_type"] == "wiki-researcher"

    done = tracker.ingest(
        ObservationEvent(
            "postmark_wiki_query",
            WikiQueryObservation(text="Open Collections sidebar."),
            tool_call_id="wiki_tc",
        )
    )
    assert len(done) == 1
    assert done[0]["status"] == "completed"
    assert "Collections" in done[0].get("result_preview", "")


def test_task_action_and_observation_lifecycle() -> None:
    """Task tool events produce running then completed records."""
    tracker = SubagentEventTracker()
    changed = tracker.ingest(
        ActionEvent(
            "task",
            TaskAction(description="Search wiki", subagent_type="wiki-researcher"),
        )
    )
    assert len(changed) == 1
    assert changed[0]["status"] == "running"
    assert changed[0]["label"] == "Search wiki"

    done = tracker.ingest(ObservationEvent("task", TaskObservation(text="Excerpt from docs.")))
    assert len(done) == 1
    assert done[0]["status"] == "completed"
    assert "Excerpt" in done[0].get("result_preview", "")


def test_delegate_spawn_and_delegate_flow() -> None:
    """Delegate spawn warms cards; delegate marks them running."""
    tracker = SubagentEventTracker()

    warmed = tracker.ingest(
        ActionEvent(
            "delegate",
            DelegateAction(
                "spawn",
                ids=["research", "summarize"],
                agent_types=["wiki-researcher", "general-purpose"],
            ),
            tool_call_id="d1",
        )
    )
    assert len(warmed) == 2
    assert {r["status"] for r in warmed} == {"warming"}

    running = tracker.ingest(
        ActionEvent(
            "delegate",
            DelegateAction(
                "delegate",
                tasks={
                    "research": "Find TypeScript scripting documentation in Postmark wiki",
                    "summarize": "Summarize results for the parent agent",
                },
            ),
            tool_call_id="d2",
        )
    )
    assert len(running) == 2
    assert all(r["status"] == "running" for r in running)
    by_id = {r["id"]: r for r in running}
    assert by_id["research"]["task_prompt"] == (
        "Find TypeScript scripting documentation in Postmark wiki"
    )
    assert by_id["summarize"]["task_prompt"] == "Summarize results for the parent agent"
    assert len(by_id["research"]["label"]) <= 80

    completed = tracker.ingest(
        ObservationEvent(
            "delegate",
            DelegateObservation(
                "delegate",
                is_error=False,
                text=(
                    "Completed delegation of 2 tasks\n\nResults:\n"
                    "1. Agent research: **TypeScript docs**\n\nSee pm.require.\n"
                    "2. Agent summarize: **Summary**\n\nCombined findings."
                ),
            ),
        )
    )
    assert len(completed) == 2
    assert all(r["status"] == "completed" for r in completed)
    by_id = {r["id"]: r for r in completed}
    assert "**TypeScript docs**" in by_id["research"]["result_preview"]
    assert "**Summary**" in by_id["summarize"]["result_preview"]
    assert "Completed delegation" not in by_id["research"]["result_preview"]


def test_delegate_agent_results_from_observation() -> None:
    """Parent delegate observation text splits into per-agent markdown bodies."""
    from services.ai.chat.subagent_events import delegate_agent_results_from_observation

    text = (
        "Completed delegation of 2 tasks\n\nResults:\n"
        "1. Agent py: **Python scripting docs**\n"
        "* Repository path: docs/scripting/python-api.md\n"
        "2. Agent ts: **TypeScript docs**\n"
        "* Repository path: docs/scripting/typescript-api.md\n"
    )
    results = delegate_agent_results_from_observation(text)
    assert "Repository path: docs/scripting/python-api.md" in results["py"]
    assert "Repository path: docs/scripting/typescript-api.md" in results["ts"]


def test_wiki_action_stores_full_task_prompt() -> None:
    """Wiki cards keep the full query in task_prompt."""
    tracker = SubagentEventTracker()
    started = tracker.ingest(
        ActionEvent(
            "postmark_wiki_query",
            WikiQueryAction("how to send request with variables"),
            tool_call_id="wiki_tc",
        )
    )
    assert started[0]["task_prompt"] == "how to send request with variables"


def test_task_action_stores_full_prompt() -> None:
    """Task tool stores the full prompt when description is absent."""
    tracker = SubagentEventTracker()
    changed = tracker.ingest(
        ActionEvent(
            "task",
            TaskAction(
                prompt="Search the wiki for Python scripting API details",
                subagent_type="wiki-researcher",
            ),
        )
    )
    assert changed[0]["task_prompt"] == "Search the wiki for Python scripting API details"


def test_postmark_delegate_tool_name_is_parsed() -> None:
    """SDK ActionEvent uses ToolDefinition.name (postmark_delegate before fix)."""
    tracker = SubagentEventTracker()
    warmed = tracker.ingest(
        ActionEvent(
            "postmark_delegate",
            DelegateAction(
                "spawn", ids=["ts", "py"], agent_types=["wiki-researcher", "wiki-researcher"]
            ),
            tool_call_id="spawn1",
        )
    )
    assert len(warmed) == 2
    assert {r["id"] for r in warmed} == {"ts", "py"}


def test_fail_inflight_marks_warming_and_running_as_error() -> None:
    """Parent turn failure must not leave cards stuck on Starting."""
    tracker = SubagentEventTracker()
    tracker.ingest(
        ActionEvent(
            "delegate",
            DelegateAction("spawn", ids=["a"], agent_types=["wiki-researcher"]),
            tool_call_id="spawn1",
        )
    )
    failed = tracker.fail_inflight()
    assert len(failed) == 1
    assert failed[0]["status"] == "error"


def test_records_for_turn_events_rebuild() -> None:
    """Turn slice helper rebuilds the same final state."""
    events = [
        ActionEvent("task", TaskAction(description="Lookup")),
        ObservationEvent("task", TaskObservation()),
    ]
    records = records_for_turn_events(events)
    assert len(records) == 1
    assert records[0]["status"] == "completed"


def test_turn_index_uses_full_session_not_tail_page() -> None:
    """Global msg_index must be resolved against the full session message list."""
    from services.ai.chat.subagent_events import _turn_index_for_message

    full_session = [
        {"role": "user", "id": 1},
        {"role": "assistant", "id": 2},
        {"role": "user", "id": 3},
        {"role": "assistant", "id": 4},
    ]
    tail_page = full_session[2:]
    global_index = 3

    assert _turn_index_for_message(full_session, global_index) == 1
    # Tail page + global index is the transcript-load bug: must not crash.
    assert _turn_index_for_message(tail_page, global_index) == 0
