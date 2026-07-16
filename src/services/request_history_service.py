"""Service layer for persisted HTTP send history."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from http import HTTPStatus
from typing import Any, Protocol, TypedDict, cast

from database.models.request_history import request_history_repository


class HistorySettingsLike(Protocol):
    """Minimal settings surface needed by :func:`record_send`."""

    @property
    def retention_days(self) -> int:
        """Days to retain history entries."""
        ...

    @property
    def max_items_per_day(self) -> int:
        """Max entries kept per calendar day."""
        ...

    @property
    def unlimited_per_day(self) -> bool:
        """When true, do not cap entries per day."""
        ...

    @property
    def save_responses(self) -> bool:
        """Whether response bodies/headers are persisted."""
        ...

    @property
    def max_response_bytes(self) -> int:
        """Max response body bytes to store."""
        ...

    def max_response_bytes_for_storage(self) -> int:
        """Return the body size cap used when persisting response bodies."""
        ...


class HistorySendPayloadDict(TypedDict):
    """HTTP payload for replaying a send without loading the editor."""

    method: str
    url: str
    headers: str | None
    body: str | None
    history_snapshot: dict[str, Any]


class RequestHistoryEntryDict(TypedDict, total=False):
    """A request history row with optional loaded file payloads."""

    id: int
    executed_at: str
    request_id: int | None
    was_persisted_request: bool
    request_name: str
    method: str
    url: str
    status_code: int
    elapsed_ms: float
    error: str | None
    response_headers: list[Any] | dict[str, Any] | None
    response_body_path: str | None
    body_truncated: bool
    response_size_bytes: int
    request_snapshot_path: str | None
    body: bytes | None
    original_request: dict[str, Any] | None
    source_label: str | None


class SendIdentityDict(TypedDict):
    """Identity fields captured at send time."""

    request_id: int | None
    request_name: str
    method: str
    url: str


class PendingHistoryContextDict(TypedDict):
    """Send-time tab context used when the HTTP worker finishes."""

    request_id: int | None
    request_name: str
    method: str
    url: str
    tab_type: str


def gather_send_identity(ctx: Any, editor: Any, data: dict[str, Any]) -> SendIdentityDict:
    """Build send identity from tab context, editor, and worker payload."""
    from services.collection_service import CollectionService

    method = str(data.get("request_method") or editor._method_combo.currentText())
    url = str(data.get("request_url") or editor._url_input.text()).strip()
    request_id = ctx.request_id if ctx is not None else None
    request_name = ""
    if ctx is not None and ctx.request_id:
        req_model = CollectionService.get_request(ctx.request_id)
        if req_model is not None:
            request_name = str(req_model.name or "")
    elif ctx is not None and ctx.draft_name:
        request_name = str(ctx.draft_name)
    return SendIdentityDict(
        request_id=request_id,
        request_name=request_name,
        method=method,
        url=url,
    )


def _body_bytes_from_response(data: dict[str, Any]) -> bytes | None:
    """Extract response body as bytes for file storage."""
    if "error" in data:
        return None
    body = data.get("body")
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8", errors="replace")


def _source_label(request_id: int | None, was_persisted_request: bool) -> str | None:
    """Return a muted UI label for unattached rows (metadata only)."""
    if request_id is not None:
        return None
    if was_persisted_request:
        return "(deleted)"
    return "(draft)"


def _normalize_history_response_headers(
    raw: list[Any] | dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Convert stored history headers to the list shape expected by the response viewer."""
    if isinstance(raw, dict):
        return [{"key": str(key), "value": str(value)} for key, value in raw.items()]
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for row in raw:
        if isinstance(row, dict):
            out.append(
                {
                    "key": str(row.get("key", "")),
                    "value": str(row.get("value", "")),
                }
            )
    return out


def _request_headers_for_viewer(snapshot: Mapping[str, Any] | None) -> list[dict[str, str]]:
    """Build outgoing header rows for the response viewer Request Headers tab."""
    if not snapshot:
        return []
    sent = snapshot.get("sent_headers")
    if isinstance(sent, dict):
        return [{"key": str(k), "value": str(v)} for k, v in sent.items()]
    if isinstance(sent, list):
        return _normalize_history_response_headers(sent)
    headers = snapshot.get("headers")
    if isinstance(headers, list):
        rows: list[dict[str, str]] = []
        for row in headers:
            if not isinstance(row, dict) or not row.get("enabled", True):
                continue
            key = str(row.get("key", "")).strip()
            if not key:
                continue
            rows.append({"key": key, "value": str(row.get("value", ""))})
        return rows
    return []


def enrich_snapshot_for_history(
    snapshot: dict[str, Any] | None,
    response: dict[str, Any],
) -> dict[str, Any]:
    """Merge editor snapshot with headers/URL/method actually sent (incl. auth)."""
    merged: dict[str, Any] = dict(snapshot) if isinstance(snapshot, dict) else {}
    sent_headers = response.get("request_headers")
    if sent_headers:
        merged["sent_headers"] = sent_headers
    request_url = response.get("request_url")
    if isinstance(request_url, str) and request_url.strip():
        merged["url"] = request_url
    request_method = response.get("request_method")
    if isinstance(request_method, str) and request_method.strip():
        merged["method"] = request_method
    return merged


def record_send(
    *,
    identity: SendIdentityDict,
    response: dict[str, Any],
    original_request: dict[str, Any] | None,
    settings: HistorySettingsLike,
) -> int | None:
    """Persist one send to history; return new entry id or ``None`` on failure."""
    snapshot = enrich_snapshot_for_history(original_request, response)
    error = response.get("error")
    if error is not None:
        status_code = 0
        elapsed_ms = 0.0
        err_text = str(error)
        headers = None
        body_bytes = None
    else:
        status_code = int(response.get("status_code", 0) or 0)
        elapsed_ms = float(response.get("elapsed_ms", 0.0) or 0.0)
        err_text = None
        headers = response.get("headers")
        body_bytes = _body_bytes_from_response(response)

    max_bytes = settings.max_response_bytes_for_storage()
    row = request_history_repository.insert_entry(
        request_id=identity.get("request_id"),
        request_name=str(identity.get("request_name", "")),
        method=str(identity.get("method", "GET")),
        url=str(identity.get("url", "")),
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        error=err_text,
        response_headers=headers if settings.save_responses else None,
        response_body=body_bytes,
        original_request=snapshot,
        save_responses=settings.save_responses,
        max_response_bytes=max_bytes if max_bytes > 0 else settings.max_response_bytes,
        retention_days=settings.retention_days,
        max_items_per_day=settings.max_items_per_day,
        unlimited_per_day=settings.unlimited_per_day,
    )
    return int(row["id"])


def _entries_with_labels(rows: list[dict[str, Any]]) -> list[RequestHistoryEntryDict]:
    """Attach ``source_label`` to repository metadata rows."""
    out: list[RequestHistoryEntryDict] = []
    for row in rows:
        entry = cast(RequestHistoryEntryDict, dict(row))
        entry["source_label"] = _source_label(
            row.get("request_id"),
            bool(row.get("was_persisted_request")),
        )
        out.append(entry)
    return out


def list_for_sidebar(
    search: str = "",
    *,
    executed_from: date | None = None,
    executed_to: date | None = None,
    limit: int = 500,
) -> list[RequestHistoryEntryDict]:
    """List all history metadata (global sidebar; newest first)."""
    rows = request_history_repository.list_entries_for_sidebar(
        search=search,
        limit=limit,
        executed_from=executed_from,
        executed_to=executed_to,
    )
    return _entries_with_labels(rows)


def list_for_request(
    request_id: int,
    search: str = "",
    *,
    executed_from: date | None = None,
    executed_to: date | None = None,
) -> list[RequestHistoryEntryDict]:
    """List send history for one persisted request."""
    rows = request_history_repository.list_for_request(
        request_id,
        search=search,
        limit=200,
        executed_from=executed_from,
        executed_to=executed_to,
    )
    return _entries_with_labels(rows)


def latest_for_request(request_id: int) -> RequestHistoryEntryDict | None:
    """Return the newest send for *request_id* (metadata only), or None."""
    rows = request_history_repository.list_for_request(request_id, limit=1)
    if not rows:
        return None
    labeled = _entries_with_labels(rows)
    return labeled[0] if labeled else None


def request_ids_with_history(ids: list[int]) -> set[int]:
    """Return request ids from *ids* that have at least one send-history row."""
    return request_history_repository.request_ids_with_history(ids)


def latest_two_json_success_entry_ids(ids: list[int]) -> dict[int, list[int]]:
    """Return request ids mapped to their two newest 2xx JSON history entry ids."""
    return request_history_repository.latest_success_json_entry_ids(ids, per_request=2)


def get_entry_metadata(entry_id: int) -> RequestHistoryEntryDict | None:
    """Load database metadata for a history row (no body/snapshot file reads)."""
    row = request_history_repository.get_entry_metadata(entry_id)
    if row is None:
        return None
    entry = cast(RequestHistoryEntryDict, dict(row))
    entry["source_label"] = _source_label(
        row.get("request_id"),
        bool(row.get("was_persisted_request")),
    )
    return entry


def get_entry(entry_id: int) -> RequestHistoryEntryDict | None:
    """Load a full history entry including file payloads."""
    row = request_history_repository.get_entry(entry_id)
    if row is None:
        return None
    entry = cast(RequestHistoryEntryDict, dict(row))
    entry["source_label"] = _source_label(
        row.get("request_id"),
        bool(row.get("was_persisted_request")),
    )
    return entry


def build_replay_request_dict(entry: RequestHistoryEntryDict) -> dict[str, Any]:
    """Build editor load data from a stored snapshot and row metadata."""
    snap = entry.get("original_request")
    data: dict[str, Any] = dict(snap) if isinstance(snap, dict) else {}
    if not str(data.get("method", "")).strip():
        data["method"] = str(entry.get("method", "GET"))
    if not str(data.get("url", "")).strip():
        data["url"] = str(entry.get("url", ""))
    if not str(data.get("name", "")).strip():
        data["name"] = str(entry.get("request_name", ""))
    return data


def can_replay_entry(entry: RequestHistoryEntryDict) -> bool:
    """Return True when *entry* has enough data to replay a send."""
    return bool(str(build_replay_request_dict(entry).get("url", "")).strip())


def _headers_text_from_snapshot(snapshot: Mapping[str, Any]) -> str:
    """Return newline header text from ``sent_headers`` or snapshot header rows."""
    sent = snapshot.get("sent_headers")
    if sent:
        if isinstance(sent, dict):
            return "\n".join(f"{key}: {value}" for key, value in sent.items())
        if isinstance(sent, str):
            return sent
        if isinstance(sent, list):
            return "\n".join(
                f"{row.get('key', '')}: {row.get('value', '')}"
                for row in sent
                if isinstance(row, dict) and row.get("key")
            )
    headers = snapshot.get("headers")
    if isinstance(headers, list) and headers:
        lines: list[str] = []
        for row in headers:
            if not isinstance(row, dict) or not row.get("enabled", True):
                continue
            key = str(row.get("key", "")).strip()
            if not key:
                continue
            lines.append(f"{key}: {row.get('value', '')}")
        return "\n".join(lines)
    return ""


def build_send_payload_from_entry(
    entry: RequestHistoryEntryDict,
) -> HistorySendPayloadDict | None:
    """Build worker inputs from a stored snapshot (headers as actually sent)."""
    snap = build_replay_request_dict(entry)
    url = str(snap.get("url", "")).strip()
    if not url:
        return None
    method = str(snap.get("method", "GET") or "GET")
    headers = _headers_text_from_snapshot(snap)
    body_val = snap.get("body")
    body: str | None
    if body_val is None:
        body = None
    else:
        body = str(body_val)
        if not body:
            body = None
    return HistorySendPayloadDict(
        method=method,
        url=url,
        headers=headers or None,
        body=body,
        history_snapshot=snap,
    )


def delete_entry(entry_id: int) -> bool:
    """Delete one send-history row and its payload files."""
    return request_history_repository.delete_entry(entry_id)


def entry_for_replay(entry_id: int) -> RequestHistoryEntryDict | None:
    """Load a history row for replay; return ``None`` when missing or not replayable."""
    entry = get_entry(entry_id)
    if entry is None or not can_replay_entry(entry):
        return None
    return entry


def replay_source_link_text(entry: RequestHistoryEntryDict) -> str:
    """Short link label for the response viewer replay banner."""
    from ui.sidebar.history.helpers import format_executed_at

    method = str(entry.get("method", "GET") or "GET")
    code = entry.get("status_code")
    status_part = f" {code}" if code is not None else ""
    executed = str(entry.get("executed_at", ""))
    when = format_executed_at(executed) if executed else "earlier send"
    return f"View {method}{status_part} ({when})"


def _http_status_reason_phrase(code: int) -> str:
    """Return the standard HTTP reason phrase for *code*, or empty if unknown."""
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return ""


def entry_to_http_response_dict(entry: RequestHistoryEntryDict) -> dict[str, Any]:
    """Map a full history entry to the dict shape used by :meth:`ResponseViewer.load_stored_response`."""
    err = entry.get("error")
    elapsed = float(entry.get("elapsed_ms", 0.0) or 0.0)
    snapshot = entry.get("original_request")
    snap_dict = snapshot if isinstance(snapshot, dict) else {}
    req_method = str(entry.get("method", "") or snap_dict.get("method", "GET"))
    req_url = str(entry.get("url", "") or snap_dict.get("url", ""))
    req_headers = _request_headers_for_viewer(snap_dict)

    if err:
        return {
            "error": str(err),
            "elapsed_ms": elapsed,
            "request_method": req_method,
            "request_url": req_url,
            "request_headers": req_headers,
            "history_entry_id": entry.get("id"),
        }

    code = int(entry.get("status_code", 0) or 0)
    body_bytes = entry.get("body")
    body_text = ""
    if body_bytes:
        body_text = body_bytes.decode("utf-8", errors="replace")
    elif entry.get("response_size_bytes"):
        body_text = "[Response body unavailable — history file missing from storage]"
    if entry.get("body_truncated") and body_text and not body_text.startswith("["):
        body_text = f"{body_text}\n\n[Response body truncated in history storage]"

    headers = _normalize_history_response_headers(entry.get("response_headers"))
    return {
        "status_code": code,
        "status_text": _http_status_reason_phrase(code),
        "elapsed_ms": elapsed,
        "headers": headers,
        "body": body_text,
        "size_bytes": int(entry.get("response_size_bytes", 0) or 0),
        "request_method": req_method,
        "request_url": req_url,
        "request_headers": req_headers,
        "history_entry_id": entry.get("id"),
    }


def entry_to_detail_snapshot(entry: RequestHistoryEntryDict) -> dict[str, Any]:
    """Shape a history row for read-only detail panes (future sidebar)."""
    body_bytes = entry.get("body")
    body_text = ""
    if body_bytes:
        body_text = body_bytes.decode("utf-8", errors="replace")
    elif entry.get("response_size_bytes"):
        body_text = "[Response body unavailable — history file missing from storage]"

    headers = _normalize_history_response_headers(entry.get("response_headers"))
    original = entry.get("original_request") or {}
    return {
        "status_code": entry.get("status_code", 0),
        "status_text": "",
        "method": entry.get("method", ""),
        "url": entry.get("url", ""),
        "elapsed_ms": entry.get("elapsed_ms", 0.0),
        "error": entry.get("error"),
        "headers": headers,
        "body": body_text,
        "body_truncated": entry.get("body_truncated", False),
        "original_request": original,
        "source_label": entry.get("source_label"),
    }


class RequestHistoryService:
    """Static façade for request send history (project convention)."""

    gather_send_identity = staticmethod(gather_send_identity)
    enrich_snapshot_for_history = staticmethod(enrich_snapshot_for_history)
    record_send = staticmethod(record_send)
    list_for_sidebar = staticmethod(list_for_sidebar)
    list_for_request = staticmethod(list_for_request)
    latest_for_request = staticmethod(latest_for_request)
    request_ids_with_history = staticmethod(request_ids_with_history)
    latest_two_json_success_entry_ids = staticmethod(latest_two_json_success_entry_ids)
    get_entry_metadata = staticmethod(get_entry_metadata)
    get_entry = staticmethod(get_entry)
    build_replay_request_dict = staticmethod(build_replay_request_dict)
    build_send_payload_from_entry = staticmethod(build_send_payload_from_entry)
    delete_entry = staticmethod(delete_entry)
    can_replay_entry = staticmethod(can_replay_entry)
    entry_for_replay = staticmethod(entry_for_replay)
    entry_to_detail_snapshot = staticmethod(entry_to_detail_snapshot)
    entry_to_http_response_dict = staticmethod(entry_to_http_response_dict)
    replay_source_link_text = staticmethod(replay_source_link_text)
