"""Resolve a human-readable send URL for Approve pending summaries."""

from __future__ import annotations

from typing import Any

from services.ai.chat.tools.workspace_query.helpers import _redact_url


def resolve_execute_preview_url(action: object) -> str | None:
    """Return a redacted destination URL for a workspace-execute action, if any.

    Used by Approve chrome so the user can see the host before confirming a send.
    Variables are substituted when possible (``environment_id`` or snapshot env);
    secrets in userinfo/query are masked; the host and path remain visible.
    """
    operation = str(getattr(action, "operation", "") or "")
    if operation not in {"send_request", "send_draft", "replay_history"}:
        return None
    raw: str | None = None
    env_id: int | None = None
    request_id: int | None = None
    try:
        env_raw = getattr(action, "environment_id", None)
        if isinstance(env_raw, int):
            env_id = env_raw
        if operation == "send_request":
            rid = getattr(action, "request_id", None)
            if isinstance(rid, int):
                request_id = rid
                from services.collection_service import CollectionService

                req = CollectionService.get_request(rid)
                if req is not None:
                    raw = str(req.url or "") or None
        elif operation == "send_draft":
            raw, snap_env, snap_req = _draft_url_context_from_snapshot()
            if env_id is None:
                env_id = snap_env
            if request_id is None:
                request_id = snap_req
        elif operation == "replay_history":
            history_entry_id = getattr(action, "history_entry_id", None)
            if isinstance(history_entry_id, int):
                from services.request_history_service import entry_for_replay

                entry = entry_for_replay(history_entry_id)
                if entry is not None:
                    raw = str(entry.get("url") or "") or None
                    rid = entry.get("request_id")
                    if isinstance(rid, int):
                        request_id = rid
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    resolved = _substitute_preview_url(raw.strip(), env_id=env_id, request_id=request_id)
    return _redact_url(resolved)


def _substitute_preview_url(
    url: str,
    *,
    env_id: int | None,
    request_id: int | None,
) -> str:
    """Best-effort ``{{var}}`` substitution for Approve preview (never raises)."""
    try:
        from services.environment_service import EnvironmentService

        variables = EnvironmentService.build_combined_variable_map(
            env_id,
            request_id,
        )
        return EnvironmentService.substitute(url, variables)
    except Exception:
        return url


def _draft_url_context_from_snapshot() -> tuple[str | None, int | None, int | None]:
    """Return ``(url, env_id, request_id)`` from the active chat workspace snapshot."""
    from services.ai.ai_config import AiConfig
    from services.ai.chat.workspace_snapshot import get_workspace_snapshot

    session_id = str(AiConfig.get_chat_session_id() or "")
    if not session_id:
        return None, None, None
    snap = get_workspace_snapshot(session_id)
    if not snap:
        return None, None, None
    env_id = snap.get("current_env_id") if isinstance(snap.get("current_env_id"), int) else None
    tabs = snap.get("tabs")
    if not isinstance(tabs, list):
        return None, env_id, None
    tab: dict[str, Any] | None = None
    active_index = snap.get("active_tab_index")
    if isinstance(active_index, int) and 0 <= active_index < len(tabs):
        candidate = tabs[active_index]
        if isinstance(candidate, dict):
            tab = candidate
    if tab is None or not tab.get("is_dirty"):
        for item in tabs:
            if isinstance(item, dict) and item.get("is_dirty"):
                tab = item
                break
    if tab is None:
        return None, env_id, None
    request_id = tab.get("request_id") if isinstance(tab.get("request_id"), int) else None
    data = tab.get("request_data")
    if not isinstance(data, dict):
        return None, env_id, request_id
    url = str(data.get("url") or "").strip()
    return (url or None), env_id, request_id


__all__ = ["resolve_execute_preview_url"]
