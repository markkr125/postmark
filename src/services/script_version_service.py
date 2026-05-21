"""Service layer for script version history.

Provides debounce-aware snapshot capture, retrieval, and pruning.
All methods are ``@staticmethod`` — no instance state needed.
"""

from __future__ import annotations

import difflib
from typing import Any

from database.models.script_versions.script_version_repository import (
    delete_script_versions,
    get_script_version,
    get_script_versions,
    save_script_version,
)


class ScriptVersionService:
    """Thin service facade over the script-version repository."""

    @staticmethod
    def capture(
        *,
        request_id: int | None = None,
        collection_id: int | None = None,
        local_script_id: int | None = None,
        script_type: str,
        content: str,
        language: str = "javascript",
    ) -> dict[str, Any] | None:
        """Save a version snapshot if the content actually changed."""
        if not content.strip():
            return None

        recent = get_script_versions(
            request_id=request_id,
            collection_id=collection_id,
            local_script_id=local_script_id,
            script_type=script_type,
            limit=1,
        )
        if recent and recent[0]["content"] == content:
            return None

        model = save_script_version(
            request_id=request_id,
            collection_id=collection_id,
            local_script_id=local_script_id,
            script_type=script_type,
            content=content,
            language=language,
        )
        return get_script_version(model.id)

    @staticmethod
    def list_versions(
        *,
        request_id: int | None = None,
        collection_id: int | None = None,
        local_script_id: int | None = None,
        script_type: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent versions for a script, newest first."""
        return get_script_versions(
            request_id=request_id,
            collection_id=collection_id,
            local_script_id=local_script_id,
            script_type=script_type,
            limit=limit,
        )

    @staticmethod
    def get_version(version_id: int) -> dict[str, Any] | None:
        """Return a single version by ID."""
        return get_script_version(version_id)

    @staticmethod
    def diff(version_a_id: int, version_b_id: int) -> str | None:
        """Return a unified diff between two versions."""
        a = get_script_version(version_a_id)
        b = get_script_version(version_b_id)
        if a is None or b is None:
            return None

        a_lines = a["content"].splitlines(keepends=True)
        b_lines = b["content"].splitlines(keepends=True)
        diff_lines = difflib.unified_diff(
            a_lines,
            b_lines,
            fromfile=f"Version {version_a_id}",
            tofile=f"Version {version_b_id}",
        )
        return "".join(diff_lines)

    @staticmethod
    def get_previous_content(
        *,
        request_id: int | None = None,
        collection_id: int | None = None,
        local_script_id: int | None = None,
        script_type: str,
        current_content: str,
    ) -> str | None:
        """Return the content of the most recent version that differs."""
        versions = get_script_versions(
            request_id=request_id,
            collection_id=collection_id,
            local_script_id=local_script_id,
            script_type=script_type,
            limit=100,
        )
        for v in versions:
            if v["content"] != current_content:
                return str(v["content"])
        return None

    @staticmethod
    def delete_versions(
        *,
        request_id: int | None = None,
        collection_id: int | None = None,
        local_script_id: int | None = None,
    ) -> int:
        """Delete all versions for a request, collection, or local script."""
        return delete_script_versions(
            request_id=request_id,
            collection_id=collection_id,
            local_script_id=local_script_id,
        )
