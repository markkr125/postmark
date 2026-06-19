# Send history

Every **Send** (except some debug replays) can be stored with metadata, optional response body, and a request snapshot.

## Per-request history (right rail)

1. Open a saved request tab.
2. Click **History** on the **right rail**.
3. Browse sends grouped by date for that request only.
4. Select a row to view method, URL, status, headers, and body in the detail area.

Use the search field to filter by URL substring or status code (e.g. `200`).

## Global history (left rail)

1. Click **History** on the **left rail** (workspace-wide).
2. See sends across all requests, including drafts and deleted requests when metadata still exists.
3. Double-click or use **Open** to load the entry in a tab.

Deleted or draft entries may show labels such as **(draft)** or **(deleted)** in the list.

## Replay

1. Select a history row with a stored snapshot.
2. Click **Replay** in the detail header.

Replay resends using the stored request snapshot. The response viewer shows a **Replayed request** indicator with a link back to the history row. Replay does not re-run the full script chain the same way as a normal **Send** — use live **Send** when you need fresh scripts.

## Open without replay

Opening from global history may show the stored response read-only in the response viewer (no new HTTP call) when you only need to inspect a past result.

## Privacy and storage

Response bodies and snapshots are stored as files under your Postmark user data directory. Adjust retention under **File → Settings… → History**. See [History settings](../settings/history.md).

## Related

- [History hub](README.md)
- [Editing and send](../requests/editing-and-send.md)
