"""Formatting helpers for send-history sidebar rows and detail panes."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ui.sidebar.history.delegate import (
    ROLE_HISTORY_CODE,
    ROLE_HISTORY_IS_DATE_GROUP,
    ROLE_HISTORY_META,
    ROLE_HISTORY_NAME,
)
from ui.sidebar.saved_responses.helpers import (
    extract_snapshot_headers,
    format_body_size,
    format_headers,
)


def format_executed_at(iso_value: str) -> str:
    """Format an ISO ``executed_at`` timestamp for list metadata."""
    text = iso_value.strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        local = parsed.astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text[:19].replace("T", " ")


def local_date_group_label(iso_value: str) -> str:
    """Return a human-readable group heading for an ISO ``executed_at`` value."""
    text = iso_value.strip()
    if not text:
        return "Unknown date"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        local_day = parsed.astimezone().date()
    except ValueError:
        return text[:10] if len(text) >= 10 else "Unknown date"
    today = datetime.now().astimezone().date()
    if local_day == today:
        return "Today"
    if local_day == today - timedelta(days=1):
        return "Yesterday"
    return local_day.strftime("%A, %B %d, %Y")


def group_entries_by_local_date(
    items: Sequence[Mapping[str, Any]],
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """Group history rows by local calendar day (preserves *items* order within each day)."""
    groups: OrderedDict[str, list[Mapping[str, Any]]] = OrderedDict()
    for item in items:
        executed = str(item.get("executed_at", ""))
        label = local_date_group_label(executed)
        groups.setdefault(label, []).append(item)
    return list(groups.items())


def iter_history_tree_items(tree: QTreeWidget) -> Iterator[QTreeWidgetItem]:
    """Yield every item in *tree* (depth-first)."""

    def visit(item: QTreeWidgetItem) -> Iterator[QTreeWidgetItem]:
        yield item
        for index in range(item.childCount()):
            yield from visit(item.child(index))

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is not None:
            yield from visit(top)


def populate_history_tree_widget(
    tree: QTreeWidget,
    items: Sequence[Mapping[str, Any]],
) -> None:
    """Fill *tree* with date group parents and send-history child rows."""
    tree.clear()
    if not items:
        return
    for day_label, day_items in group_entries_by_local_date(items):
        group = QTreeWidgetItem([day_label])
        group.setData(0, ROLE_HISTORY_IS_DATE_GROUP, True)
        group.setData(0, ROLE_HISTORY_NAME, day_label)
        group.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        group.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        tree.addTopLevelItem(group)
        for item in day_items:
            entry_id = int(item["id"])
            row = QTreeWidgetItem(group)
            row.setData(0, Qt.ItemDataRole.UserRole, entry_id)
            row.setData(0, ROLE_HISTORY_CODE, item.get("status_code"))
            row.setData(0, ROLE_HISTORY_NAME, build_row_name(item))
            row.setData(0, ROLE_HISTORY_META, build_history_row_meta(item))
            row.setToolTip(0, build_row_name(item))
        group.setExpanded(True)
    tree.expandAll()


def first_history_entry_id(tree: QTreeWidget) -> int | None:
    """Return the first send entry id in *tree*, or ``None``."""
    for item in iter_history_tree_items(tree):
        if item.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            continue
        entry_id = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(entry_id, int):
            return entry_id
    return None


def find_history_tree_item(tree: QTreeWidget, entry_id: int) -> QTreeWidgetItem | None:
    """Return the tree item for *entry_id*, or ``None`` when not present."""
    for item in iter_history_tree_items(tree):
        if item.data(0, ROLE_HISTORY_IS_DATE_GROUP):
            continue
        if item.data(0, Qt.ItemDataRole.UserRole) == entry_id:
            return item
    return None


def build_row_name(entry: Mapping[str, Any]) -> str:
    """Return the primary list label for a history row."""
    name = str(entry.get("request_name", "")).strip()
    if name:
        return name
    method = str(entry.get("method", "GET"))
    url = str(entry.get("url", ""))
    combined = f"{method} {url}".strip()
    return combined[:120] if combined else "Send"


def extract_history_request_headers(snapshot: Mapping[str, Any] | None) -> str:
    """Return request header text as sent (editor rows + auth-injected headers)."""
    if not snapshot:
        return ""
    sent = snapshot.get("sent_headers")
    if sent:
        return format_headers(sent)
    return extract_snapshot_headers(snapshot)


def build_history_row_meta(entry: Mapping[str, Any]) -> str:
    """Return a metadata summary line for a send-history list row."""
    parts: list[str] = []
    method = str(entry.get("method", "")).strip()
    if method:
        parts.append(method)
    status = entry.get("status_code")
    if status is not None:
        parts.append(str(status))
    executed = entry.get("executed_at")
    if isinstance(executed, str) and executed:
        parts.append(format_executed_at(executed))
    size = entry.get("response_size_bytes")
    if size:
        parts.append(format_body_size(int(size)))
    label = entry.get("source_label")
    if label:
        parts.append(str(label))
    return " \u00b7 ".join(parts)
