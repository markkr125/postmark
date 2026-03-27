"""Script chain resolution service.

Builds the ordered list of script entries that must execute for a given
request, walking the collection → folder → … → request inheritance chain.
"""

from __future__ import annotations

import logging
from typing import Any

from database.models.collections.collection_query_repository import get_script_chain
from services.scripting import ScriptEntry
from services.scripting.context import normalize_events

logger = logging.getLogger(__name__)

# Default language when no ``"language"`` key is present on an events dict.
_DEFAULT_LANGUAGE = "javascript"


class ScriptService:
    """Resolve inherited script chains for a request or collection.

    All methods are ``@staticmethod`` — no instance state needed.
    """

    @staticmethod
    def build_script_chain(
        request_id: int,
    ) -> tuple[list[ScriptEntry], list[ScriptEntry]]:
        """Return ``(pre_request_chain, test_chain)`` for *request_id*.

        **Pre-request chain** is ordered top-down: collection → folder → request.
        **Test chain** is ordered bottom-up: request → folder → collection
        (matching Postman convention: the request's own tests run first).

        Each entry contains the script ``code``, ``language``, and
        ``source_name`` (human-readable label for console output).

        Empty scripts are omitted from both chains.
        """
        raw_chain = get_script_chain(request_id)
        return _build_chains(raw_chain)

    @staticmethod
    def build_collection_script_chain(
        events: dict[str, Any] | None,
        *,
        name: str = "",
    ) -> tuple[list[ScriptEntry], list[ScriptEntry]]:
        """Build a single-level chain from inline events (no DB lookup).

        Used for draft requests that have no ``request_id`` yet.
        """
        normalized = normalize_events(events)
        pre: list[ScriptEntry] = []
        test: list[ScriptEntry] = []
        language = str(normalized.get("language", _DEFAULT_LANGUAGE))

        pre_code = normalized.get("pre_request", "").strip()
        if pre_code:
            pre.append({"code": pre_code, "language": language, "source_name": name})

        test_code = normalized.get("test", "").strip()
        if test_code:
            test.append({"code": test_code, "language": language, "source_name": name})

        return pre, test


def _build_chains(
    raw_chain: list[dict[str, Any]],
) -> tuple[list[ScriptEntry], list[ScriptEntry]]:
    """Convert raw DB chain into ordered ``(pre_request, test)`` entry lists."""
    pre_entries: list[ScriptEntry] = []
    test_entries: list[ScriptEntry] = []

    for layer in raw_chain:
        normalized = normalize_events(layer.get("scripts"))
        source_name = layer.get("name", "")
        language = str(normalized.get("language", _DEFAULT_LANGUAGE))

        pre_code = normalized.get("pre_request", "").strip()
        if pre_code:
            pre_entries.append(
                {
                    "code": pre_code,
                    "language": language,
                    "source_name": source_name,
                }
            )

        test_code = normalized.get("test", "").strip()
        if test_code:
            test_entries.append(
                {
                    "code": test_code,
                    "language": language,
                    "source_name": source_name,
                }
            )

    # Test chain runs bottom-up: request → folder → collection.
    test_entries.reverse()

    return pre_entries, test_entries
