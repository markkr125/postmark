"""Service bridge for declarative request assertions (UI must use this, not DB)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict

from database.models.request_assertions.request_assertion_repository import (
    delete_assertions_for_request,
    fetch_assertions_for_request,
    replace_assertions_for_request,
)
from services.scripting import ScriptEntry
from services.scripting.assertions_compiler import VALID_OPERATORS, compile_to_js, compile_to_py


class AssertionDict(TypedDict):
    """Interchange dict for one declarative assertion row."""

    subject: str
    operator: str
    expected: str
    enabled: bool
    order_index: int
    id: NotRequired[int]
    request_id: NotRequired[int]


class AssertionService:
    """Static API for the Assertions tab and send pipeline."""

    @staticmethod
    def fetch_for_request(request_id: int) -> list[AssertionDict]:
        """Return assertion rows for *request_id*."""
        rows = fetch_assertions_for_request(request_id)
        return [AssertionService._normalise_row(row) for row in rows]

    @staticmethod
    def save_for_request(request_id: int, assertions: list[AssertionDict]) -> list[AssertionDict]:
        """Replace all assertions for *request_id* and return persisted rows."""
        cleaned = [
            AssertionService._normalise_row(row, index=index)
            for index, row in enumerate(assertions)
        ]
        saved = replace_assertions_for_request(request_id, [dict(row) for row in cleaned])
        return [AssertionService._normalise_row(row) for row in saved]

    @staticmethod
    def delete_for_request(request_id: int) -> None:
        """Remove every assertion row for *request_id*."""
        delete_assertions_for_request(request_id)

    @staticmethod
    def build_declarative_script_entry(
        request_id: int,
        language: str,
    ) -> ScriptEntry | None:
        """Compile enabled assertions into a single post-response script entry."""
        rows = fetch_assertions_for_request(request_id)
        enabled = [row for row in rows if row.get("enabled", True)]
        if not enabled:
            return None
        lang = (language or "javascript").lower()
        code = compile_to_py(enabled) if lang == "python" else compile_to_js(enabled)
        if not code.strip():
            return None
        return ScriptEntry(code=code, language=lang, source_name="declarative")

    @staticmethod
    def _normalise_row(row: Mapping[str, Any], *, index: int | None = None) -> AssertionDict:
        """Validate and coerce a repository/service dict."""
        operator = str(row.get("operator", "eq")).strip() or "eq"
        if operator not in VALID_OPERATORS:
            operator = "eq"
        order = int(row.get("order_index", index if index is not None else 0))
        out: AssertionDict = {
            "subject": str(row.get("subject", "")).strip(),
            "operator": operator,
            "expected": str(row.get("expected", "") or ""),
            "enabled": bool(row.get("enabled", True)),
            "order_index": order,
        }
        if row.get("id") is not None:
            out["id"] = int(row["id"])
        if row.get("request_id") is not None:
            out["request_id"] = int(row["request_id"])
        return out
