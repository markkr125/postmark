"""Service layer for persisted HTTP send history."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict, cast

from database.models.request_history import request_history_repository
from ui.styling.history_settings_manager import HistorySettingsManager


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


def _source_label(request_id: int | None, request_name: str) -> str | None:
    """Return a muted UI label for unattached rows (metadata only).

    Rows with ``request_id is NULL`` are either unsaved-tab sends or orphaned
    after the collection request was deleted; v1 uses ``(deleted)`` when the
    id is missing and a name was stored (draft sends are hidden on the
    per-request rail).
    """
    if request_id is None:
        return "(deleted)" if request_name.strip() else "(draft)"
    return None


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
    settings: HistorySettingsManager,
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
            row.get("request_id"), str(row.get("request_name", ""))
        )
        out.append(entry)
    return out


def list_for_sidebar(search: str = "") -> list[RequestHistoryEntryDict]:
    """List all history metadata (global sidebar; newest first)."""
    rows = request_history_repository.list_entries_for_sidebar(search=search, limit=500)
    return _entries_with_labels(rows)


def list_for_request(request_id: int, search: str = "") -> list[RequestHistoryEntryDict]:
    """List send history for one persisted request."""
    rows = request_history_repository.list_for_request(request_id, search=search, limit=200)
    return _entries_with_labels(rows)


def get_entry(entry_id: int) -> RequestHistoryEntryDict | None:
    """Load a full history entry including file payloads."""
    row = request_history_repository.get_entry(entry_id)
    if row is None:
        return None
    entry = cast(RequestHistoryEntryDict, dict(row))
    entry["source_label"] = _source_label(row.get("request_id"), str(row.get("request_name", "")))
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


def entry_to_detail_snapshot(entry: RequestHistoryEntryDict) -> dict[str, Any]:
    """Shape a history row for read-only detail panes (future sidebar)."""
    body_bytes = entry.get("body")
    body_text = ""
    if body_bytes:
        body_text = body_bytes.decode("utf-8", errors="replace")
    elif entry.get("response_size_bytes"):
        body_text = "[Response body unavailable — history file missing from storage]"

    headers = entry.get("response_headers") or []
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
    get_entry = staticmethod(get_entry)
    build_replay_request_dict = staticmethod(build_replay_request_dict)
    build_send_payload_from_entry = staticmethod(build_send_payload_from_entry)
    delete_entry = staticmethod(delete_entry)
    can_replay_entry = staticmethod(can_replay_entry)
    entry_for_replay = staticmethod(entry_for_replay)
    entry_to_detail_snapshot = staticmethod(entry_to_detail_snapshot)
    replay_source_link_text = staticmethod(replay_source_link_text)
