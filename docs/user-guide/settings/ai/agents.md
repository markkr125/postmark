# AI agents settings

Tune how many chat runs Postmark allows before warning you about concurrency.

## Steps

1. Open **File → Settings…** → **AI** → **Agents**.
2. Set **Advisory concurrent chat runs** (default 10, range 1–64).
3. Click **Apply** or **OK**.

## What this controls

When the number of active AI chat worker runs reaches this threshold, the composer shows a **warning** before starting another message. Sends are **not blocked** — the limit is advisory so you know many sessions are running at once.

Useful when testing multiple chats or long-running agent turns.

## Related

- [Chat](../../ai-assistant/chat.md)
- [AI settings hub](README.md)
