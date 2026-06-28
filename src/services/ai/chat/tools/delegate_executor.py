"""Postmark delegate executor — records subagent disk paths at spawn time."""

from __future__ import annotations

from openhands.tools.delegate.definition import DelegateAction, DelegateObservation
from openhands.tools.delegate.impl import DelegateExecutor
from services.ai.chat.subagent_disk_registry import register_subagent_disk_path


class PostmarkDelegateExecutor(DelegateExecutor):
    """Delegate executor that registers spawn id → persistence dir for the UI."""

    def _spawn_agents(self, action: DelegateAction) -> DelegateObservation:
        """Spawn sub-agents and register each one's on-disk conversation path."""
        result = super()._spawn_agents(action)
        if getattr(result, "is_error", False):
            return result
        self._register_spawned_disk_paths()
        return result

    def _register_spawned_disk_paths(self) -> None:
        """Publish ``agent_id → persistence_dir`` for the parent chat session."""
        try:
            parent = self.parent_conversation
        except RuntimeError:
            return
        session_id = str(parent.state.id)
        for agent_id, sub_conversation in self._sub_agents.items():
            persistence_dir = sub_conversation.state.persistence_dir
            if persistence_dir:
                register_subagent_disk_path(session_id, agent_id, persistence_dir)


__all__ = ["PostmarkDelegateExecutor"]
