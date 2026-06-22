"""Unit tests for app context snapshot TypedDict helpers."""

from __future__ import annotations

import json
from pathlib import Path

from services.ai.chat.app_context.inject import build_message_prefix
from services.ai.chat.app_context.snapshot import SNAPSHOT_FILENAME, truncate_preview


def test_truncate_preview_adds_marker() -> None:
    """Long preview text is truncated with a marker."""
    text = "x" * 9000
    out = truncate_preview(text, limit=100)
    assert out.endswith("[truncated]")
    assert len(out) <= 100


def test_build_message_prefix_reads_snapshot(tmp_path: Path) -> None:
    """Inject prefix is built from snapshot file on disk."""
    snap = {
        "captured_at": "2026-01-01T00:00:00+00:00",
        "send_mode": "agent",
        "active_tab": {
            "tab_type": "request",
            "request_id": 1,
            "collection_id": None,
            "local_script_id": None,
            "title": "Users",
            "method": "GET",
            "is_dirty": False,
            "is_preview": False,
            "draft_name": None,
            "active_sub_tab": None,
            "editor_preview": "",
        },
        "open_tabs": [],
        "deferred_tabs": [],
        "environment": {"id": None, "name": None},
        "tree_selection": {
            "kind": "none",
            "collection_id": None,
            "local_script_id": None,
            "label": None,
        },
    }
    (tmp_path / SNAPSHOT_FILENAME).write_text(json.dumps(snap), encoding="utf-8")
    prefix = build_message_prefix("agent", tmp_path)
    assert "<postmark_app_context" in prefix
    assert "Users" in prefix
