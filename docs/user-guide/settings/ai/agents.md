# AI agents settings

Tune concurrent chat runs, parallel subagents, and which Agent write/send kinds skip Approve.

## Concurrent runs

1. Open **File → Settings…** → **AI** → **Agents**.
2. Set **Advisory concurrent chat runs** (default 10, range 1–64).
3. Optionally set **Max parallel subagents per turn**.
4. Click **Apply** or **OK**.

When active AI chat runs reach the concurrent threshold, the composer shows a **warning** before starting another message. Sends are **not blocked** — the limit is advisory so you know many sessions are running at once.

**Max parallel subagents per turn** caps how many parallel delegate subagents one assistant turn may start. Sequential task-style subagents are not affected.

## Agent edits

In the AI panel, switch the mode pill to **Agent** to propose workspace edits and request sends. Risky actions pause for an **inline Approve card** in the turn unless the kind is listed under auto-approve. Full workflow: [Agent workspace edits](../../ai-assistant/agent-edits.md).

**Ask** and **Plan** stay read-only.

## Auto-approved Agent actions

Kinds listed under **Auto-approved Agent actions** skip the Approve prompt. An empty list means ask every time.

1. Click **Add…** and choose a kind (for example **Create request**, **Send request**, or **Create local script**).
2. Select a row and click **Remove** to drop one kind, or **Remove all** to clear the list.

You can also add a kind from the chat card with **Always allow** (that still Allows the current batch).

**Auth**, **environment-secret**, and **OAuth Get Token** kinds never appear in this list and cannot be Always-allowed — they always pause for **Allow**.

Catalog coverage includes collections/requests (including folder `events`), local scripts, environments/globals/active environment (non-secret), history delete, import, script version restore, debug metadata (breakpoints/watches), allowlisted settings, snippets, saved response examples, and execute kinds (send, replay, run scripts, run local script, run collection, run iterations, GraphQL fetch, codegen, export).

## Related

- [Agent workspace edits](../../ai-assistant/agent-edits.md)
- [Chat](../../ai-assistant/chat.md)
- [AI settings hub](README.md)
