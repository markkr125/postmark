# Workspace explorer

Ask the AI about your **collections, environments, history, and open tabs** — it reads your local workspace and answers with clickable links into Postmark. Secrets stay redacted. This page covers **read-only** questions; to let **Agent** edit or send (with your Approve), see [Agent workspace edits](agent-edits.md).

## What you can ask

Examples (say them in plain language):

1. **Which requests hit staging?** — the assistant maps requests to hostnames under the selected environment (or compares two environments).
2. **What can I clean up?** — health checks flag never-sent requests with no saved examples, missing tests, unresolved variables, and more.
3. **Is my token expired?** — JWT-shaped bearer/token variables show relative expiry only (never the raw token).
4. **What must I run before Checkout?** — a static dependency hint from scripts that set variables and requests that use `{{…}}`.
5. **Explain this collection** — a short walkthrough: where to start, auth, env vars needed, folders, suggested run order.
6. **Did this response shape change?** — compares the last two successful JSON sends and reports added/removed fields and type changes (paths only, not values).

You can also ask about **open tabs**, the **live response**, **send history**, **environments**, and **where a variable is defined or used**.

## How answers look

- Named items appear as **clickable links** that open the request, collection, environment, history send, or saved example in the app.
- Health and search scans may cover a bounded slice of a large workspace; ask to narrow by folder or name if you need more detail.
- Sensitive values (tokens, passwords, API keys) are **redacted** in tool output before the model sees them.

## Tips

1. Select the environment you care about before asking about hostnames or unresolved variables.
2. Prefer concrete names (“Checkout”, “Orders API”) over numeric ids — you never need to type ids.
3. For send history questions, mention the request or a URL fragment / status rather than asking for a generic “search”.

## Related

- [Chat](chat.md) — panel chrome, modes, sessions
- [Agent workspace edits](agent-edits.md) — Agent mode writes and sends
- [AI assistant hub](README.md)
- [AI settings](../settings/ai/README.md)
