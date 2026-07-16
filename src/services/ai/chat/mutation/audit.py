"""Append-only audit log for successful Agent workspace mutations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from database.data_paths import postmark_user_data_dir


def _audit_path() -> Path:
    return postmark_user_data_dir() / "ai" / "mutations.jsonl"


def append_mutation_audit(record: dict[str, Any]) -> None:
    """Append one JSON line to the mutations audit log (best-effort)."""
    path = _audit_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(UTC).isoformat(),
            **record,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


__all__ = ["append_mutation_audit"]
