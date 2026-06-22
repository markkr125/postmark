# AI chat app context

How Postmark exposes live workspace state to the AI assistant via
`postmark_app_context`, snapshot files, mode profiles, and the workspace
researcher sub-agent.

## Overview

```text
User edits in MainWindow (tabs, env, tree)
  --> app_context_snapshot.json  (per session disk dir)
       |
       +-- build_message_prefix()  (once at send; not in SQLite)
       |
       +-- postmark_app_context tool  (re-reads snapshot each call)
```

| Piece | Role |
|-------|------|
| `_AppContextSnapshotMixin` | GUI-thread capture into `app_context_snapshot.json` |
| `_AppContextRefreshMixin` | Debounced live refresh while the **active** session runs |
| `build_message_prefix` | Auto-inject tier (compact / rich / preflight) prepended to SDK message |
| `postmark_app_context` | OpenHands read-only tool (search, detail foci) |
| `workspace_researcher` | Sub-agent via OpenHands `TaskToolSet` for cross-workspace search |
| `PostmarkChatVisualizer` | Maps Task events to research flyout + activity row |

## Snapshot file

Path: `{session_disk_dir}/{uuid.hex}/app_context_snapshot.json`

Written atomically (`*.tmp` + `os.replace`). Schema: `AppContextSnapshot` in
`services/ai/chat/app_context/snapshot.py`.

Sensitive fields are redacted via `context_redaction.py` before persistence.

## Live refresh (v2)

While the **active** AI session has an in-flight worker, Postmark rewrites the
snapshot when the user changes workspace context:

| Trigger | Mechanism |
|---------|-----------|
| Tab switch (settled) | `schedule_app_context_refresh()` from `_on_tab_change_settled` |
| Environment change | `schedule_app_context_refresh()` from `_on_environment_changed` |
| Collection / script tree selection | `selected_collection_changed` on both sidebars |
| Request sub-tab (Headers, Body, …) | `RequestEditor._tabs.currentChanged` |
| Return to a running session | `flush_app_context_refresh()` from `_reattach_session_run_if_needed` |

Debounced **250 ms** (`_APP_CONTEXT_REFRESH_MS`) to coalesce rapid tab scrolling.

**Policy:** Only `_active_ai_session_id` is refreshed. Background concurrent runs
keep their send-time snapshot until you focus that chat again (then flush once).

**Limit:** The auto-inject prefix is still captured at send time. Live refresh
updates tool reads and `focus=current` mid-turn, not the already-sent prefix.

## Mode profiles

`resolve_chat_mode(send_mode)` in `mode_profiles.py` sets:

| Mode | Tools | Inject tier |
|------|-------|-------------|
| Ask | wiki + app_context | compact |
| Agent | wiki + app_context + TaskToolSet | rich |
| Plan | same as Agent | preflight |

`send_mode` is stored on `ChatRunHandle` for refresh without reaching into the
worker thread.

## Workspace research

Agent/Plan modes may call `task(subagent_type="workspace_researcher", …)`.
The main agent cannot use `focus=search` on `postmark_app_context` when
TaskToolSet is present — it must delegate.

UI:

- Activity row shows status (`Researching workspace…`, etc.)
- Click **Research** (activity chip or footer) opens `aiResearchActivityPopup`
- Findings land in the flyout from `TaskObservation.text`
- 2 s grace after findings, then activity hides; footer chip remains

Signals: `ChatRunRegistry.research_updated` →
`AiChatPanel.deliver_research_update`.

## Stop during research (v2)

When the user clicks **Stop** during a sub-agent `task`:

1. UI shows **Stopping…** on the activity row and clears research grace timer
2. `ChatRunRegistry.cancel` emits `phase=stopped` research payload
3. Worker calls `conv.interrupt()` and polls `_run_until_done_or_stop`
4. If the SDK does not exit within `CHAT_STOP_SUBAGENT_TIMEOUT_S` (5 s), the
   asyncio task is cancelled so the worker thread unblocks

Partial assistant text is preserved with a **Stopped** footer when content had
started streaming.

## Related

- [Data flow](data-flow.md) — section 6 (AI chat app context)
- [User guide: AI chat](../user-guide/ai-assistant/chat.md)
- `src/AGENTS.md` — app context wiring summary
