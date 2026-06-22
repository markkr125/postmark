# AI chat

Use the right-rail assistant to ask questions, plan API work, or run agent-style turns against your configured models.

## Open the panel

1. Click the **AI** icon on the **right rail**.
2. The flyout shows the conversation transcript and composer at the bottom.

## Send a message

1. Type in the prompt box at the bottom.
2. Press **Enter** to send ( **Shift+Enter** for a new line).
3. Watch the assistant stream a reply; thinking blocks may appear collapsed above the answer.

Click **Stop** on the composer or user-message footer to cancel an in-flight run. During **Agent** or **Plan** workspace research, Stop shows **Stopping…** and should return within a few seconds; partial answers keep a **Stopped** footer.

## Live workspace context

While a turn is running in the **active** chat session, Postmark keeps the app-context snapshot aligned with what you are viewing:

- Switching request tabs or sub-tabs (Headers, Body, Scripts, …)
- Changing the active environment
- Selecting a different collection or local-script tree item

The assistant’s tools see the updated tab and selection on the next `postmark_app_context` call. The invisible auto-inject block at send time does **not** update mid-turn — only tool reads refresh.

If you run multiple chats concurrently, only the **visible** session’s snapshot updates as you work. Switch back to a background-running chat to refresh its snapshot once.

## Choose mode and model

| Control | Options |
|---------|---------|
| **Mode pill** | **Agent**, **Ask**, or **Plan** — changes tools and how much workspace context is auto-injected |
| **Model button** | Pick an enabled model; gear/edit for context tier, thinking, reasoning |

### What each mode does

| Mode | Behaviour |
|------|-----------|
| **Ask** | Wiki tool only; compact snapshot of your active tab is prepended invisibly (not stored in chat history) |
| **Agent** | Wiki + app-context tool + workspace researcher sub-agent; richer auto-inject; research progress may appear in a flyout while the sub-agent searches |
| **Plan** | Like Agent but tuned for planning turns (preflight context tier) |

The assistant can read your open tabs, collections, scripts, send history, and environments through the **app context** system. Sensitive values (API keys, auth headers, environment secrets) are redacted before they reach the model.

## Sessions

| Action | How |
|--------|-----|
| New chat | **+** on the title bar |
| Past chats | Clock icon → session history popover (search, rename, delete) |
| Rename | Click the title or pencil on hover |

Postmark restores the last active session on launch when possible.

## Context and spend

Click the **context ring** next to the model button to open a breakdown of tokens used in the current session. Switch to **Spend** for per-turn USD cost when the model has pricing metadata.

A one-line **summarized** notice may appear after long conversations when the SDK compacts older turns.

During **Agent** or **Plan** turns, a **research** flyout may show while a background sub-agent searches your workspace (collections, requests, scripts, history). Click **Research** on the activity row or assistant footer to open it. Status lines update while searching; findings appear when ready. After findings, the activity row hides after a short pause while the footer chip remains.

## Message actions

Use the **⋯** menu on user or assistant messages:

- **Edit message** (user) — rewind and resubmit from that turn
- **Fork chat** — start a new session from this point
- **Copy message** — copy markdown source

## Attachments

When supported, add file chips from the attachment row above the prompt before sending.

## Related

- [Models and providers](../settings/ai/models-and-providers.md)
- [Budgets](../settings/ai/budgets.md)
- [AI assistant hub](README.md)
