---
name: openhands-tools
description: >-
  How to add or change Postmark AI chat tools on the OpenHands Software Agent
  SDK. Use when creating a new postmark_* tool, extending mutate/execute,
  wiring Approve/ConfirmRisky, or tempted to fix tool discovery with system
  prompts / wiki how-tos.
---

# OpenHands tools in Postmark

Postmark embeds the [OpenHands Software Agent SDK](https://docs.openhands.dev/sdk/guides/custom-tools).
Follow the SDK — do not invent alternate discovery paths.

## How the SDK discovers tools (canonical)

1. **Action** — Pydantic model with `Field(description=…)` (inputs the LLM sees).
2. **Observation** — result returned to the LLM (`from_text` or structured fields + `to_llm_content`).
3. **ToolExecutor** — `__call__(action) -> Observation`.
4. **ToolDefinition.create(conv_state, …)** — builds the tool instance.
5. **`register_tool(name, factory)`** via `register_postmark_tool` in
   `src/services/ai/chat/tool_registry.py`.
6. **Agent** gets `tools=[Tool(name=…)]` from `resolve_tools(tool_names)`.

The model chooses tools from **JSON schemas** generated from Action fields and
the tool `description`. That is the intended discovery mechanism.

Security is separate: `SecurityAnalyzer.security_risk` + `ConfirmRisky` →
`WAITING_FOR_CONFIRMATION` (Postmark Approve cards). See
`mutation/security.py` and `mutation/auto_approve.py`.

Official docs: [Custom Tools](https://docs.openhands.dev/sdk/guides/custom-tools),
[Tool System](https://docs.openhands.dev/sdk/arch/tool-system),
[Security](https://docs.openhands.dev/sdk/guides/security).

## Do this

- One **user-facing job** → one **dedicated** `postmark_*` tool with clear Action
  fields (example: `postmark_import` with `url` | `path` | `text` | `curl`).
- Keep tool descriptions factual (what it does + examples), like
  `postmark_datetime` / OpenHands Grep examples.
- Wire write tools into `agent_tools._WRITE_TOOLS`, catalog kind +
  `kind_from_tool_args` / `is_mutate_or_execute_tool`, and Agent-only
  `tools_for_turn`.
- Reuse service-layer code (`ImportService`, `CollectionService`, …) inside the
  executor; enqueue GUI side effects via `mutation/bridge.py`.

## Never do this (fighting the SDK)

- **Bury a new capability** inside `postmark_workspace_mutate` /
  `postmark_workspace_execute` as another `entity` / `operation` when the model
  needs to discover it as a first-class action (import, send-like jobs with
  distinct schemas, etc.). Generic mutate stays for CRUD on existing entities.
- **Paper over bad schemas** with long system-prompt paragraphs (“call mutate
  with action=X, entity=Y…”), catalog id coaching, or “do not open the Import
  dialog” rants.
- **Substitute `postmark_wiki_query` / wiki-researcher** for a write/import that
  a tool can perform — wiki is how-to docs, not an executor.
- **Monkeypatch OpenHands** or pin packages to work around tool design; keep
  `openhands-sdk` and `openhands-tools` version-aligned.

## Checklist — new write tool

1. Package under `src/services/ai/chat/tools/<name>/` (Action / Observation /
   Executor / `register_*`).
2. `register_*` from `agent_registry._register_defaults`.
3. Add to default agent `tool_names`.
4. If write: `_WRITE_TOOLS`, auto-approve kind, security analyzer coverage.
5. Tests for Action validation, kind mapping, executor.
6. User-guide + AGENTS trees; no internal tool/catalog ids in user-facing docs.

## Reference implementations

| Tool | Package |
|------|---------|
| `postmark_datetime` | `tools/datetime_query/` |
| `postmark_import` | `tools/workspace_import/` |
| `postmark_wiki_query` | `tools/wiki_query.py` |
| `postmark_workspace_query` | `tools/workspace_query/` |
| `postmark_workspace_mutate` | `tools/workspace_mutate/` (CRUD only) |
| `postmark_workspace_execute` | `tools/workspace_execute/` (send/run ops) |

## Transcript UI — tool activity cards

Main-agent tools (not wiki/delegate) emit in-flight rows via
`ToolActivityTracker` in `tool_activity_events.py`, wired from
`AiChatWorker.event_cb` → `tool_activity_updated` → `ChatMessageBubble`.

- **Confirm-gated writes** — no running spinner on `ActionEvent`; `PendingToolCard`
  owns the pause; after Approve, running card until `ObservationEvent`.
- **Outcomes** — reuse `observation_indicates_write` for import/mutate/execute
  (zero import counts with `ok: true` = error).
- **Execute** — tool row suppressed on observation; `ExecuteResultCard` from bridge.
- **Fast read-only** — `postmark_datetime` cards under ~400ms are suppressed unless error.
- **Wiki** — stays on `SubagentEventTracker` (`kind="wiki"`); do not duplicate in tool activity.
