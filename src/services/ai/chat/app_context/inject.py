"""Auto-inject app context prefix for chat sends (not persisted to SQLite)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from services.ai.chat.app_context.snapshot import SNAPSHOT_FILENAME, AppContextSnapshot
from services.ai.chat.mode_profiles import resolve_chat_mode

InjectTier = Literal["compact", "rich", "preflight"]

_TIER_LIMITS: dict[InjectTier, int] = {
    "compact": 800,
    "rich": 2500,
    "preflight": 3000,
}


def _compact_body(snapshot: AppContextSnapshot) -> str:
    """Build the compact one-liner block."""
    tab = snapshot["active_tab"]
    env = snapshot["environment"]
    parts = [
        f"tab={tab['tab_type']}",
        f"title={tab['title']}",
    ]
    if tab.get("method"):
        parts.append(f"method={tab['method']}")
    if tab.get("request_id") is not None:
        parts.append(f"request_id={tab['request_id']}")
    if env.get("name"):
        parts.append(f"env={env['name']}")
    if tab.get("is_dirty"):
        parts.append("dirty=true")
    return " | ".join(parts)


def _rich_body(snapshot: AppContextSnapshot) -> str:
    """Build rich inject body (compact + preview + tabs + tree)."""
    lines = [_compact_body(snapshot)]
    preview = snapshot["active_tab"].get("editor_preview") or ""
    if preview:
        lines.append(f"\nEditor preview:\n{preview}")
    if snapshot.get("open_tabs"):
        labels = [t["label"] for t in snapshot["open_tabs"]]
        lines.append("\nOpen tabs: " + ", ".join(labels))
    tree = snapshot.get("tree_selection") or {}
    if tree.get("kind") != "none" and tree.get("label"):
        lines.append(f"\nTree selection: {tree['kind']} — {tree['label']}")
    return "\n".join(lines)


def _preflight_body(snapshot: AppContextSnapshot) -> str:
    """Build plan-mode preflight inject body."""
    tab = snapshot["active_tab"]
    lines = [
        _rich_body(snapshot),
        "\nIDs:",
        f"request_id={tab.get('request_id')}",
        f"collection_id={tab.get('collection_id')}",
        f"local_script_id={tab.get('local_script_id')}",
        f"environment_id={snapshot['environment'].get('id')}",
        '\nFor broad workspace search, call task(subagent_type="workspace_researcher", …).',
    ]
    return "\n".join(lines)


def build_message_prefix(send_mode: str | None, session_disk: Path) -> str:
    """Read snapshot JSON and return the inject prefix for the SDK message."""
    path = session_disk / SNAPSHOT_FILENAME
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        snapshot: AppContextSnapshot = raw  # type: ignore[assignment]
    except (OSError, json.JSONDecodeError, TypeError):
        return ""

    tier = resolve_chat_mode(send_mode).inject_tier
    if tier == "compact":
        body = _compact_body(snapshot)
    elif tier == "rich":
        body = _rich_body(snapshot)
    else:
        body = _preflight_body(snapshot)

    limit = _TIER_LIMITS[tier]
    if len(body) > limit:
        body = body[: limit - len("\n…[truncated]")] + "\n…[truncated]"

    return f'<postmark_app_context tier="{tier}">\n{body}\n</postmark_app_context>\n\n'
