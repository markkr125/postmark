# AI chat

Use the right-rail assistant to ask questions, plan API work, or run agent-style turns against your configured models.

## Open the panel

1. Click the **AI** icon on the **right rail**.
2. The flyout shows the conversation transcript and composer at the bottom.

## Send a message

1. Type in the prompt box at the bottom.
2. Press **Enter** to send ( **Shift+Enter** for a new line).
3. Watch the assistant stream a reply; thinking blocks may appear collapsed above the answer. During **Agent** turns, each approval or tool call closes the current thinking block and appears directly below it. Clicking **Allow** immediately shows an animated **Starting…** indicator; while the tool runs, its card keeps animating with **Running** status. After the action completes, a **Thinking…** spinner appears directly below its card until the next reasoning block or answer starts. Later tool calls continue in the same chronological order.

Click **Stop** on the composer or user-message footer to cancel an in-flight run.

## Choose mode and model

| Control | Options |
|---------|---------|
| **Mode pill** | **Ask** / **Plan** — read-only help and planning. **Agent** — can propose workspace edits and sends; you **Approve** (or auto-approve) before they run |
| **Model button** | Pick an enabled model; gear/edit for context tier, thinking, reasoning |

See [Agent workspace edits](agent-edits.md) for the inline Approve card (**Allow** / **Reject** / **Always allow**) and auto-approved kinds.

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

Click the paperclip to attach one or more local files. Each attachment appears as a chip
above the prompt, so you can write "turn this into a collection" instead of typing the
path yourself. Chips are cleared once the message is sent. Attaching a file is enough to
send — you do not have to type anything.

When you send, Postmark copies each PDF or Word document into the chat's own storage and
converts it to Markdown. Your message carries a short reference to that copy rather than
the file's path or its contents. The assistant then reads the copy a chunk at a time, so a
long specification does not have to fit into a single message.

How screenshots inside the document are handled depends on the model you picked. If it
supports images, it is shown the screenshots themselves for the part it is reading, which
is the better result whenever the picture's layout matters. If it does not, Postmark reads
the text out of those screenshots and gives it that instead. Text recognition is only ever
a fallback, so a model that can see the picture is never handed a flattened transcript of
it. Recognition needs the optional `ocr` extra; without it, a model that cannot see images
gets nothing from them.

Because Postmark keeps its own copy, you can move or delete the original file afterwards
without breaking the chat. Deleting the chat session deletes its copies too.

## Date and time

Ask the assistant for the current date or time, to convert a time between timezones (for example, “what time is it in Australia right now?”), or to interpret a Unix timestamp / JWT `exp` epoch (“convert 1752386400 to my local timezone — is that in the past?”). The assistant uses your computer’s local timezone when the source zone is not specified; Unix timestamps are always UTC.

## Messy PDF or Word docs

In **Agent** mode, you can attach a local **PDF** or **DOCX** API document — even when request/response examples are screenshots mixed with prose. It reads the file first (no Approve), then proposes a collection import you **Allow** once. Long specs are read in several passes, a page range at a time, so give it a moment on a big document.

Screenshots need one of two things. A **vision-capable model** sees embedded images directly — check the model's capabilities in **Settings → AI → Models**. Otherwise Postmark falls back to on-device OCR, which is an optional install:

```bash
poetry install --extras ocr
```

Without either, the text and tables still import correctly, but anything that exists only inside a screenshot is skipped.

## Related

- [Agent workspace edits](agent-edits.md) — turn on edits, Approve / Reject, auto-approve
- [Workspace explorer](workspace-explorer.md) — ask about your collections, variables, and history
- [Models and providers](../settings/ai/models-and-providers.md)
- [Budgets](../settings/ai/budgets.md)
- [AI assistant hub](README.md)
