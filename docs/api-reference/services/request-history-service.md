# RequestHistoryService

Persists HTTP **send history** (metadata in SQLite, bodies and request snapshots
on disk under `user_history_root()`). All methods are `@staticmethod` aliases of
module-level functions.

Source: `src/services/request_history_service.py`  
Repository: `src/database/models/request_history/request_history_repository.py`

## TypedDicts

### `RequestHistoryEntryDict`

Metadata row plus optional loaded file payloads (`get_entry`).

| Field | Type | Notes |
|-------|------|--------|
| `id` | `int` | Primary key |
| `executed_at` | `str` | ISO timestamp (UTC) |
| `request_id` | `int \| None` | `NULL` after request delete or draft sends |
| `was_persisted_request` | `bool` | `True` if send was from a saved request at record time |
| `request_name` | `str` | Name at send time (not updated on rename) |
| `method`, `url` | `str` | As sent |
| `status_code`, `elapsed_ms` | | Response metadata |
| `error` | `str \| None` | Transport failure |
| `response_headers` | `list \| dict \| None` | Stored headers |
| `body` | `bytes \| None` | Loaded response body (`get_entry` only) |
| `original_request` | `dict \| None` | Loaded snapshot (`get_entry` only) |
| `source_label` | `str \| None` | UI only: `(deleted)`, `(draft)`, or `None` |

### `source_label` rules

| Condition | Label |
|-----------|--------|
| `request_id` set | `None` |
| `request_id` is `None` and `was_persisted_request` | `(deleted)` |
| `request_id` is `None` and not `was_persisted_request` | `(draft)` |

### `SendIdentityDict`

Captured at send start: `request_id`, `request_name`, `method`, `url`.

### `HistorySendPayloadDict`

Built for HTTP replay from a snapshot (`build_send_payload_from_entry`).

## Methods

| Method | Purpose |
|--------|---------|
| `gather_send_identity(ctx, editor, data)` | Identity at send start |
| `record_send(identity, response, original_request, settings)` | Persist one send; return entry id |
| `list_for_sidebar(search?, executed_from?, executed_to?)` | Global list (left rail), newest first, limit 500; optional local-calendar date bounds |
| `list_for_request(request_id, search?, executed_from?, executed_to?)` | Per-request list (right rail), limit 200; optional date bounds |
| `get_entry(entry_id)` | Full row + body + snapshot |
| `entry_to_detail_snapshot(entry)` | Read-only sidebar detail panes |
| `entry_to_http_response_dict(entry)` | Dict for `ResponseViewer.load_stored_response` |
| `build_replay_request_dict(entry)` | Editor `load_request` shape from snapshot |
| `build_send_payload_from_entry(entry)` | Worker payload for HTTP replay |
| `can_replay_entry(entry)` | Whether URL exists in snapshot |
| `entry_for_replay(entry_id)` | `get_entry` when replayable |
| `delete_entry(entry_id)` | Remove row and files |
| `replay_source_link_text(entry)` | Response viewer replay banner label |

## `entry_to_http_response_dict`

Maps a full history entry to the dict shape expected by
`ResponseViewer.load_stored_response` (not the same as `entry_to_detail_snapshot`).

| Field | Source |
|-------|--------|
| `status_code`, `elapsed_ms`, `error` | Row metadata |
| `status_text` | HTTP reason phrase (e.g. `"OK"`, `"I'm a teapot"`) |
| `headers` | Normalized `response_headers` list |
| `body` | Decoded bytes, missing-file placeholder, truncation note |
| `size_bytes` | `response_size_bytes` |
| `request_method`, `request_url` | Row `method` / `url` |
| `request_headers` | From snapshot `sent_headers` or header rows |

On error sends, returns `error`, timing, and request metadata only.

## Stored vs live response display

- **`ResponseViewer.load_response`** — live send; enables Save Response.
- **`ResponseViewer.load_stored_response`** — history open/replay display; clears
  test/pre-request tabs; does **not** set `_last_live_response`.

Global open and per-request replay-from-snapshot use **stored** mode.

## Settings

`HistorySettingsManager` (`history/*` QSettings): retention, per-day caps,
`save_responses`, `max_response_bytes`.
