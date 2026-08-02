"""Tests for collection-draft signature recipes and draft wiring."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, cast

import pytest
from PySide6.QtCore import QSettings

from services.ai.chat.tools.collection_draft.build import (
    build_parsed_collection,
    collect_variable_rows,
)
from services.ai.chat.tools.collection_draft.config import set_draft_script_language
from services.ai.chat.tools.collection_draft.recipes import (
    build_signing_script,
    known_recipe_kinds,
    recipe_for_kind,
    recipe_variables,
)
from services.ai.chat.tools.collection_draft.state import (
    CollectionDraft,
    DraftRequest,
    clear_draft,
    get_draft,
)
from services.ai.chat.tools.collection_draft.tool import (
    CollectionDraftAction,
    CollectionDraftExecutor,
)
from services.collection_service import CollectionService

_SESSION = "00000000-0000-4000-8000-00000000e3c3"


class _State:
    """Minimal conversation state exposing the session id."""

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.persistence_dir = None


class _Conversation:
    """Minimal conversation stub for the executor."""

    def __init__(self, session_id: str) -> None:
        self.state = _State(session_id)


@pytest.fixture
def executor() -> Iterator[CollectionDraftExecutor]:
    """Return a fresh executor with no draft carried over."""
    clear_draft(_SESSION)
    yield CollectionDraftExecutor()
    clear_draft(_SESSION)


@pytest.fixture(autouse=True)
def _reset_language() -> Iterator[None]:
    """Isolate the draft script language setting."""
    settings = QSettings("Postmark", "Postmark")
    settings.remove("ai/draft_script_language")
    settings.sync()
    yield
    settings.remove("ai/draft_script_language")
    settings.sync()


def _run(executor: CollectionDraftExecutor, **kwargs: Any) -> str:
    """Invoke the executor and return the observation text."""
    action = CollectionDraftAction(**kwargs)
    obs = executor(action, cast(Any, _Conversation(_SESSION)))
    return obs.text


def _collection_id(body: str) -> int:
    """Parse the created collection id from a finish observation."""
    match = re.search(r"imported_collections: \[\{'id': (\d+),", body)
    assert match is not None, body
    return int(match.group(1))


def test_recipe_lookup_known_kinds() -> None:
    """Both built-in kinds resolve; unknown returns None."""
    assert recipe_for_kind("sha256_apikey_secret_timestamp") is not None
    assert recipe_for_kind("hmac_sha256") is not None
    assert recipe_for_kind("rsa_v4") is None
    assert "sha256_apikey_secret_timestamp" in known_recipe_kinds()
    assert "hmac_sha256" in known_recipe_kinds()


def test_sha256_python_script_uses_sandbox_shim() -> None:
    """Python Hotelbeds recipe references hashlib_sha256 + unix_timestamp."""
    recipe = recipe_for_kind("sha256_apikey_secret_timestamp")
    assert recipe is not None
    script = build_signing_script(recipe, "python")
    assert "hashlib_sha256" in script
    assert "unix_timestamp()" in script
    assert "X-Signature" in script
    assert "Api-key" in script
    assert "CryptoJS" not in script


def test_sha256_javascript_script_uses_cryptojs() -> None:
    """JS Hotelbeds recipe uses CryptoJS.SHA256."""
    recipe = recipe_for_kind("sha256_apikey_secret_timestamp")
    assert recipe is not None
    script = build_signing_script(recipe, "javascript")
    assert "CryptoJS.SHA256" in script
    assert "Date.now()" in script
    assert "hashlib_sha256" not in script


def test_hmac_sha256_scripts_reference_correct_crypto() -> None:
    """HMAC recipe uses hmac shim (py) or CryptoJS.HmacSHA256 (js)."""
    recipe = recipe_for_kind("hmac_sha256")
    assert recipe is not None
    py = build_signing_script(recipe, "python")
    js = build_signing_script(recipe, "javascript")
    assert "hashlib_hmac_sha256" in py
    assert "CryptoJS.HmacSHA256" in js


def test_recipe_variables_include_credentials() -> None:
    """Recipe variable rows cover apiKey + secret with empty values."""
    recipe = recipe_for_kind("sha256_apikey_secret_timestamp")
    assert recipe is not None
    rows = recipe_variables(recipe)
    keys = {row["key"] for row in rows}
    assert keys == {"apiKey", "secret"}
    assert all(row["value"] == "" for row in rows)


def test_unknown_signature_kind_recoverable(executor: CollectionDraftExecutor) -> None:
    """Unknown signature.kind returns ok:false without starting a draft."""
    body = _run(
        executor,
        operation="start",
        name="Bad",
        signature={"kind": "aws_sig_v4"},
    )
    assert "ok: false" in body
    assert "unknown_signature_kind" in body
    assert get_draft(_SESSION) is None


def test_status_and_finish_signature_flags(executor: CollectionDraftExecutor) -> None:
    """Status/finish report the signature recipe kind."""
    start = _run(
        executor,
        operation="start",
        name="Signed API",
        signature={"kind": "sha256_apikey_secret_timestamp"},
    )
    assert "signature: sha256_apikey_secret_timestamp" in start
    _run(
        executor,
        operation="add_requests",
        requests=[{"name": "Ping", "method": "GET", "url": "{{baseUrl}}/ping"}],
    )
    status = _run(executor, operation="status")
    assert "signature: sha256_apikey_secret_timestamp" in status
    finish = _run(executor, operation="finish")
    assert "ok: true" in finish
    assert "signature script" in finish
    assert "sha256_apikey_secret_timestamp" in finish


def test_finish_persists_signing_script_and_variables(
    executor: CollectionDraftExecutor,
) -> None:
    """Finish writes events.pre_request + apiKey/secret collection variables."""
    set_draft_script_language("python")
    _run(
        executor,
        operation="start",
        name="Hotelbeds-like",
        signature={
            "kind": "sha256_apikey_secret_timestamp",
            "key_header": "Api-key",
            "signature_header": "X-Signature",
        },
        pre_script="# user pre\npm.variables.set('x', '1')",
    )
    _run(
        executor,
        operation="add_requests",
        requests=[{"name": "Availability", "method": "GET", "url": "{{baseUrl}}/hotels"}],
    )
    body = _run(executor, operation="finish")
    collection = CollectionService.get_collection(_collection_id(body))
    assert collection is not None
    events = collection.events or {}
    pre = str(events.get("pre_request") or "")
    assert "hashlib_sha256" in pre
    assert "unix_timestamp()" in pre
    assert "pm.variables.set('x', '1')" in pre
    assert pre.index("hashlib_sha256") < pre.index("pm.variables.set('x'")
    variables = collection.variables or []
    keys = {str(row.get("key")) for row in variables if isinstance(row, dict)}
    assert "apiKey" in keys
    assert "secret" in keys


def test_build_prepends_signing_script_to_user_pre() -> None:
    """Signing script is prepended ahead of any user collection pre_script."""
    set_draft_script_language("python")
    recipe = recipe_for_kind("sha256_apikey_secret_timestamp")
    assert recipe is not None
    draft = CollectionDraft(
        name="Signed",
        signature_recipe=recipe,
        pre_script="pm.variables.set('extra', '1')",
        requests=[DraftRequest(name="A", method="GET", url="/a")],
    )
    parsed = build_parsed_collection(draft)
    events = parsed.get("events") or {}
    assert isinstance(events, dict)
    pre = str(events.get("pre_request") or "")
    assert "hashlib_sha256" in pre
    assert "pm.variables.set('extra', '1')" in pre
    assert pre.index("hashlib_sha256") < pre.index("pm.variables.set('extra'")


def test_unsafe_signature_overrides_recoverable(executor: CollectionDraftExecutor) -> None:
    """Header/var overrides that break out of string literals are rejected."""
    body = _run(
        executor,
        operation="start",
        name="Inject",
        signature={
            "kind": "sha256_apikey_secret_timestamp",
            "signature_header": 'X-Sig"; evil()',
            "key_var": "apiKey",
        },
    )
    assert "ok: false" in body
    assert "bad_signature" in body
    assert get_draft(_SESSION) is None


def test_unsafe_overrides_sanitized_in_recipe_for_kind() -> None:
    """recipe_for_kind drops unsafe overrides and keeps safe defaults."""
    recipe = recipe_for_kind(
        "sha256_apikey_secret_timestamp",
        {
            "signature_header": 'X-Sig"; evil()',
            "key_header": "Api-key",
            "key_var": "myKey",
        },
    )
    assert recipe is not None
    assert recipe.signature_header == "X-Signature"
    assert recipe.key_header == "Api-key"
    assert recipe.key_var == "myKey"
    script = build_signing_script(recipe, "python")
    assert "evil()" not in script
    assert "X-Signature" in script


def test_bearer_auth_does_not_seed_unused_token_var() -> None:
    """Bearer auth with {{bearerToken}} does not also create a token variable."""
    draft = CollectionDraft(
        name="Bearer",
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{bearerToken}}", "type": "string"}],
        },
        requests=[DraftRequest(name="Me", method="GET", url="/me")],
    )
    keys = {row["key"] for row in collect_variable_rows(draft)}
    assert "bearerToken" in keys
    assert "token" not in keys


def test_default_headers_preserve_duplicate_request_headers() -> None:
    """Request headers keep duplicates; defaults only fill missing keys."""
    from services.ai.chat.tools.collection_draft.build import _merge_headers

    merged = _merge_headers(
        [{"key": "Accept", "value": "application/json"}, {"key": "X-Default", "value": "1"}],
        [
            {"key": "Accept", "value": "text/plain"},
            {"key": "X-Custom", "value": "a"},
            {"key": "X-Custom", "value": "b"},
        ],
    )
    assert merged == [
        {"key": "X-Default", "value": "1", "enabled": True},
        {"key": "Accept", "value": "text/plain", "enabled": True},
        {"key": "X-Custom", "value": "a", "enabled": True},
        {"key": "X-Custom", "value": "b", "enabled": True},
    ]


def test_too_many_variables_are_trimmed(executor: CollectionDraftExecutor) -> None:
    """Oversized variables list is trimmed; the draft still starts."""
    from services.ai.chat.tools.collection_draft.ops import MAX_VARIABLES

    body = _run(
        executor,
        operation="start",
        name="Vars",
        variables=[{"key": f"v{i}", "value": ""} for i in range(MAX_VARIABLES + 1)],
    )
    assert "ok: true" in body
    assert "variables trimmed" in body
    draft = get_draft(_SESSION)
    assert draft is not None
    assert len(draft.variables) == MAX_VARIABLES


def test_auth_too_large_recoverable(executor: CollectionDraftExecutor) -> None:
    """Oversized auth blob returns ok:false."""
    from services.ai.chat.tools.collection_draft.ops import MAX_AUTH_CHARS

    body = _run(
        executor,
        operation="start",
        name="Auth",
        auth={
            "type": "bearer",
            "bearer": [{"key": "token", "value": "x" * (MAX_AUTH_CHARS + 10)}],
        },
    )
    assert "ok: false" in body
    assert "auth_too_large" in body
