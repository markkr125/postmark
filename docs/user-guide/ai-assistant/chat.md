# AI chat

Use the right-rail assistant to ask questions, plan API work, or run agent-style turns against your configured models.

## Open the panel

1. Click the **AI** icon on the **right rail**.
2. The flyout shows the conversation transcript and composer at the bottom.

## Send a message

1. Type in the prompt box at the bottom.
2. Press **Enter** to send ( **Shift+Enter** for a new line).
3. Watch the assistant stream a reply; thinking blocks may appear collapsed above the answer.

Click **Stop** on the composer or user-message footer to cancel an in-flight run.

## Choose mode and model

| Control | Options |
|---------|---------|
| **Mode pill** | **Agent**, **Ask**, or **Plan** — changes system behaviour |
| **Model button** | Pick an enabled model; gear/edit for context tier, thinking, reasoning |

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

## Message actions

Use the **⋯** menu on user or assistant messages:

- **Edit message** (user) — rewind and resubmit from that turn
- **Fork chat** — start a new session from this point
- **Copy message** — copy markdown source

## Attachments

When supported, add file chips from the attachment row above the prompt before sending.

## Date and time

Ask the assistant for the current date or time, to convert a time between timezones (for example, “what time is it in Australia right now?”), or to interpret a Unix timestamp / JWT `exp` epoch (“convert 1752386400 to my local timezone — is that in the past?”). The assistant uses your computer’s local timezone when the source zone is not specified; Unix timestamps are always UTC.

## Related

- [Workspace explorer](workspace-explorer.md) — ask about your collections, variables, and history
- [Models and providers](../settings/ai/models-and-providers.md)
- [Budgets](../settings/ai/budgets.md)
- [AI assistant hub](README.md)
