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
| `postmark_document_import` | `tools/document_import/` (read one chunk of an uploaded PDF/DOCX) |
| `postmark_collection_draft` | `tools/collection_draft/` (incremental build; only `finish` writes) |
| `postmark_wiki_query` | `tools/wiki_query.py` |
| `postmark_workspace_query` | `tools/workspace_query/` |
| `postmark_workspace_mutate` | `tools/workspace_mutate/` (CRUD only) |
| `postmark_workspace_execute` | `tools/workspace_execute/` (send/run ops) |

## Transcript UI — tool activity cards

Main-agent tools (not wiki/delegate) emit in-flight rows via
`ToolActivityTracker` in `tool_activity_events.py`, wired from
`AiChatWorker.event_cb` → `tool_activity_updated` → `ChatMessageBubble`.

- **Confirm-gated writes** — no running spinner on `ActionEvent`; `PendingToolCard`
  owns the pause; clicking Approve immediately changes it to an animated
  **Starting…** state, then the running card remains animated until `ObservationEvent`.
- **Actual event identity/state** — the SDK emits import events as
  `postmark_workspace_import` even though the registered tool is `postmark_import`.
  Track both names. Decide pending-vs-running from `ActionEvent.security_risk`
  (`LOW` executes immediately; `HIGH` / `UNKNOWN` pauses), not by independently
  predicting confirmation from the local auto-approve list.
- **Import once** — `postmark_import.collection_name_suffix` handles “import and
  append X to the name” in one approved operation. The per-session turn guard
  suppresses a second identical source call and returns the first result. Import
  observations provide named `collection_links`; final replies copy those labels
  and never display a raw `postmark://` URI.
- **Document import** — `postmark_document_import` is read-only (LOW risk, no
  Approve). It serves one chunk of an uploaded Markdown document per call: Action
  `uri` + `chunk`, observation ending in `chunk X of Y` plus a `next_step` line.
  Screenshots for that chunk ride along as `ImageContent` when the session's model
  has vision (`attachments/screenshots.py`), capped per chunk; otherwise OCR text
  is placed under each `[image N]` marker.
- **Let the existing capability flag decide, and give it one meaning.** The model
  entry already records `vision`; that flag alone chooses images *or* OCR. Sending
  both was doing a worse job twice — a vision model reads the screenshot better
  than OCR ever will, and a text-only model cannot use the image at all. Publish
  the flag once per run (`AiChatWorker.set_run`); never ask the model.
- **Do fallback work lazily, at the point the fallback is chosen.** OCR used to run
  at upload for every document, wasting seconds for vision models and baking its
  output into stored bytes where nothing could opt out. It now runs at read time,
  for one chunk's images, only when there is no vision, cached in `images/ocr.json`.
- **Scope an expensive capability to the unit you already bound.** Images attach
  per chunk, not per document — the same bound that makes the text affordable.
- **Split the work app-side, not by asking the model to plan it.** Page ranges or
  section outlines made coverage depend on the model's judgement, so parts of a
  spec were silently skipped. `attachments/chunks.py` divides the document once,
  deterministically; the model only has to count to Y. Anything that must be
  complete should be enumerated by code and consumed by the model, never the
  reverse.
- **Do not deliver a whole document in the message.** Inlining a spec at send time
  removed a failure step but did not fit in context. Store it and page through it
  instead: content the turn cannot hold belongs behind a read tool with an
  explicit position and total.
- **Never make the model retype a long literal.** A 60-character path with spaces
  and parentheses, re-emitted once per read, gets abbreviated to
  `"path":"/home/…"`; the provider then rejects the whole tool call and the run
  dies. Give it a short, URI-safe identity instead
  (`postmark://uploaded/<name>.md`, sanitized in `markdown_name_for`) and keep the
  field optional so a single upload needs no argument at all. Parse it back with a
  character-class match, not a delimiter search — models wrap URIs in markdown
  links and prose. If there is exactly one upload, resolve it even when an
  unnecessary echoed URI is damaged; ambiguity, not textual equality, is the
  safety boundary.
- **Own the bytes you depend on.** Composer attachments are copied into
  `ai_attachments/<hex>/` and converted to Markdown there (`attachments/store.py`),
  not read from wherever the user picked them, so a chat survives the original
  moving and cannot change mid-run. Keep them out of the SDK's session directory,
  which it scans for its own event files; `delete_session` removes both. Echo the
  original file name in observations — the on-disk name is sanitized.
- **Never ask a small model for one giant tool argument.** A whole Postman
  collection JSON is the failure case that produced fabricated imports: the model
  cannot emit it, there is no error, and it reports success anyway. The opposite
  extreme is also broken: one tool round-trip per endpoint replays the current
  document observation until context explodes. Build with
  `postmark_collection_draft operation=add_requests`, one atomic bounded batch per
  document chunk, and let `finish` write. Keep the model-facing operation enum
  narrow — do not retain legacy `add_request` / `add_folder` alternatives. Nested
  request bodies accept JSON objects/arrays directly and are serialized app-side;
  escaped JSON strings invite small models to abbreviate them with invalid `...`.
  The liberal schema also accepts query `params` (with per-row descriptions),
  markdown descriptions, and `pre_script`/`test_script`. Script language is the
  `ai/draft_script_language` setting (default python), interpolated into the tool
  description at create time. Shared assertions go in the collection-level script;
  shared helpers may use `postmark_workspace_mutate` local_script create +
  `pm.require("local:…")` (works for Python and JS/TS).
- **Normalize placeholders app-side.** Do not ask the model to rewrite URL
  templates — `build.py` converts `{var}` / `:var` / `<var>` to `{{var}}` and
  auto-creates missing collection variables at finish (never scan bodies).
- **Be liberal in what a tool Action accepts.** Small models emit natural field
  variations — `path` for `url`, a header object instead of `key`/`value` rows, a
  stray `target_id` copied from other tools. A strict Action schema turns a
  well-formed batch into a multi-error Pydantic dump (a hard `AgentErrorEvent`),
  which the model cannot recover from and answers with a tool-discovery spiral.
  Make Action/nested fields optional, set `model_config = ConfigDict(extra="ignore")`,
  normalize aliases in a `model_validator`, and move real validation into the
  executor/ops layer where failures come back as recoverable `ok: false`
  observations, not hard errors.
- **Cap fields a small model can balloon.** A model may paste a whole nested
  response example into a request `body`, producing a huge deeply-nested tool
  argument it then malformed (stray `{`/trailing comma) — rejected server-side
  before any Postmark code runs. Cap `body` (`MAX_BODY_CHARS`) so a valid-but-huge
  body comes back as a recoverable `body_too_large` observation instead of a giant
  argument to fumble.
- **A TOC is an index, not endpoint evidence.** Only add requests whose method,
  path, and request example/parameters have actually been read. Response docs may
  continue into another chunk; that must not postpone every request until the end.
  This prevents the model from
  turning names seen on pages 2–3 into guessed request bodies before pages 23–44
  have been read.
- **Multi-step write tools** — gate risk on the *operation*, not the tool name
  (`auto_approve.draft_operation_is_write`), so only the persisting step asks for
  Approve.
- **Deep links must be earned** — a collection link in the final message is
  stripped unless a tool observation in that turn produced its id
  (`claim_guard.strip_unbacked_collection_links`). Do not rely on phrasing regexes
  alone; models evade them.
- **Write ledger must recognize every write tool** — use the single
  `auto_approve.is_mutate_or_execute_tool` source of truth (via
  `claim_guard.observation_records_write`). A private second list in the chat
  worker missed `postmark_collection_draft`, so every successful draft `finish`
  still produced the false "No workspace change was actually made" warning and
  stripped the real collection link. For multi-step draft tools, only the
  persisting step (finish / `mutation_id:` marker) may record a write.
- **Outcomes** — reuse `observation_indicates_write` for import/mutate/execute
  (zero import counts with `ok: true` = error); draft tools gate through
  `observation_records_write` so non-finish ops never count.
- **Execute** — tool row suppressed on observation; `ExecuteResultCard` from bridge.
- **Fast read-only** — `postmark_datetime` cards under ~400ms (completed only) are suppressed unless error.
- **Chronological thinking phases** — showing Approve chrome finalizes the active thought
  immediately. Each newly visible tool-call batch gets its own append-only card group;
  reasoning after it starts a fresh thought block below it. Never reuse one global card
  stack or a single post-tool thought block: either choice reorders the second tool cycle.
- **Post-tool gap** — when the last running card becomes terminal, move the shared
  activity row below that card and show animated **Thinking…**. The next reasoning or
  answer chunk hides it before appending content.
- `clear_pending_confirmation` must re-run activity refresh after Approve because the
  worker emits `tool_activity_updated` before `confirmation_cleared`.
- **Wiki** — stays on `SubagentEventTracker` (`kind="wiki"`); do not duplicate in tool activity.

## `postmark_workspace_mutate` — collection title

- `action=rename` + `fields.name` — explicit rename.
- `action=update` + `fields.name` — also renames (pops `name`, calls `rename_collection` before
  `update_collection`; do not add `name` to repository `_EDITABLE_COLLECTION_FIELDS`).
- Request `update` already allows `name`; collection `update` must mirror that DX.
