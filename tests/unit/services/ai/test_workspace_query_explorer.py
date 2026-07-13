"""Tests for env_reach, dependencies, walkthrough, and new insights sections."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from services.ai.chat.tools.workspace_query import REDACTED_PLACEHOLDER, execute_workspace_query
from services.ai.chat.tools.workspace_query.render.insights.scans.drift import _typed_paths
from services.ai.chat.workspace_snapshot import set_workspace_snapshot
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from services.request_history_service import RequestHistoryService, SendIdentityDict
from ui.styling.history_settings_manager import HistorySettingsManager


def _session() -> str:
    """Return a unique session id for snapshot isolation."""
    return str(uuid.uuid4())


def _jwt(*, exp: int, secret_marker: str = "raw_jwt_secret_marker_xyz") -> str:
    """Build a minimal HS256-shaped JWT with *exp* (value must never leak)."""

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"exp": exp, "sub": secret_marker}).encode())
    sig = _b64(b"sig")
    return f"{header}.{payload}.{sig}"


def _record_json(
    *,
    request_id: int,
    name: str,
    body: str,
    settings: HistorySettingsManager,
    url: str = "https://example.com/user",
) -> None:
    """Persist one successful JSON history send."""
    identity: SendIdentityDict = {
        "request_id": request_id,
        "request_name": name,
        "method": "GET",
        "url": url,
    }
    RequestHistoryService.record_send(
        identity=identity,
        response={
            "status_code": 200,
            "elapsed_ms": 1.0,
            "headers": [{"key": "Content-Type", "value": "application/json"}],
            "body": body,
        },
        original_request={"method": "GET", "url": url},
        settings=settings,
    )


def test_env_reach_buckets_by_host(make_collection_with_request: Any) -> None:
    """env_reach groups requests by resolved hostname under the active env."""
    env = EnvironmentService.create_environment("ReachEnv")
    secret = "reach_secret_host_fragment_xyz"
    EnvironmentService.update_environment_values(
        env.id,
        [
            {
                "key": "baseUrl",
                "value": "https://api.staging.example.com",
                "enabled": True,
                "type": "default",
            },
            {
                "key": "api_token",
                "value": secret,
                "enabled": True,
                "type": "secret",
            },
        ],
    )
    _coll, req = make_collection_with_request(
        req_name="ReachLogin",
        # Mutation: secret is referenced so a leak would surface in the URL/host path.
        url="https://{{api_token}}.evil.example/login",
    )
    sid = _session()
    set_workspace_snapshot(sid, {"current_env_id": env.id, "tabs": [], "active_tab_index": 0})
    text = execute_workspace_query("env_reach", session_id=sid)
    assert "Environment reach" in text
    assert f"postmark://request/{req.id}" in text
    assert secret not in text
    assert "redacted-host" in text


def test_env_reach_unresolved_bucket(make_collection_with_request: Any) -> None:
    """Unresolved {{vars}} land in the unresolved host bucket."""
    env = EnvironmentService.create_environment("ReachUnresolved")
    EnvironmentService.update_environment_values(
        env.id,
        [{"key": "other", "value": "x", "enabled": True, "type": "default"}],
    )
    _coll, req = make_collection_with_request(
        req_name="UnresolvedHost",
        url="https://{{missing_host}}/v1",
    )
    sid = _session()
    set_workspace_snapshot(sid, {"current_env_id": env.id, "tabs": [], "active_tab_index": 0})
    text = execute_workspace_query("env_reach", session_id=sid)
    assert "unresolved" in text.lower()
    assert f"postmark://request/{req.id}" in text


def test_env_reach_diff_repoints(make_collection_with_request: Any) -> None:
    """env_reach search=diff shows hostname re-points between two envs."""
    staging = EnvironmentService.create_environment("ReachStaging")
    prod = EnvironmentService.create_environment("ReachProd")
    EnvironmentService.update_environment_values(
        staging.id,
        [
            {
                "key": "baseUrl",
                "value": "https://api.staging.example.com",
                "enabled": True,
                "type": "default",
            }
        ],
    )
    EnvironmentService.update_environment_values(
        prod.id,
        [
            {
                "key": "baseUrl",
                "value": "https://api.prod.example.com",
                "enabled": True,
                "type": "default",
            }
        ],
    )
    _coll, req = make_collection_with_request(
        req_name="ReachDiffReq",
        url="{{baseUrl}}/v1",
    )
    text = execute_workspace_query(
        "env_reach",
        session_id=_session(),
        search=f"diff:{staging.id}:{prod.id}",
    )
    assert "Environment reach diff:" in text
    assert f"postmark://request/{req.id}" in text
    assert "api.staging.example.com" in text
    assert "api.prod.example.com" in text


def test_insights_dead_requests(
    make_collection_with_request: Any, tmp_path: Any, monkeypatch: Any, qapp: Any
) -> None:
    """dead_requests flags never-sent requests without examples; excludes history + examples."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, dead = make_collection_with_request(req_name="DeadNeverSent")
    _coll2, live = make_collection_with_request(req_name="HasHistory")
    _coll3, exemplified = make_collection_with_request(req_name="HasExample")
    CollectionService.save_response(
        exemplified.id,
        "example",
        "OK",
        200,
        [],
        "{}",
    )
    settings = HistorySettingsManager()
    _record_json(request_id=live.id, name="HasHistory", body="{}", settings=settings)
    text = execute_workspace_query(
        "insights",
        session_id=_session(),
        search="dead_requests",
    )
    assert "Dead requests" in text
    dead_section = text.split("Dead requests")[-1]
    assert f"postmark://request/{dead.id}" in dead_section
    assert f"postmark://request/{live.id}" not in dead_section
    assert f"postmark://request/{exemplified.id}" not in dead_section


def test_insights_token_expiry_no_secret_leak(make_collection_with_request: Any) -> None:
    """token_expiry reports relative JWT expiry without leaking the token."""
    del make_collection_with_request
    env = EnvironmentService.create_environment("TokenEnv")
    secret = "raw_jwt_must_never_appear_abc123"
    now = datetime(2026, 7, 13, 12, 0, 0, tzinfo=UTC)
    exp = int((now + timedelta(hours=2)).timestamp())
    token = _jwt(exp=exp, secret_marker=secret)
    expired = _jwt(exp=int((now - timedelta(days=3)).timestamp()), secret_marker=secret)
    EnvironmentService.update_environment_values(
        env.id,
        [
            {"key": "access_token", "value": token, "enabled": True, "type": "secret"},
            {"key": "refresh_token", "value": expired, "enabled": True, "type": "secret"},
            {
                "key": "opaque_token",
                "value": "opaque-not-a-jwt",
                "enabled": True,
                "type": "secret",
            },
        ],
    )
    from services.ai.chat.tools.workspace_query.render.insights.renderer import _render_insights

    text = _render_insights(sections=["token_expiry"], now=now)
    assert "Token expiry" in text
    assert "expires in ~2h" in text
    assert "EXPIRED" in text
    assert token not in text
    assert expired not in text
    assert secret not in text
    assert "skipped" in text.lower()


def test_dependencies_producer_consumer(make_collection_with_request: Any) -> None:
    """Dependencies links a script producer to a {{var}} consumer."""
    coll, login = make_collection_with_request(req_name="DepLogin")
    checkout = CollectionService.create_request(
        coll.id,
        "POST",
        "https://api.example.com/checkout/{{cart_id}}",
        "DepCheckout",
    )
    CollectionService.update_request(
        login.id,
        scripts={
            "test": 'pm.environment.set("cart_id", "abc");',
        },
    )
    text = execute_workspace_query(
        "dependencies",
        session_id=_session(),
        target_id=checkout.id,
    )
    assert "Dependencies for" in text
    assert f"postmark://request/{login.id}" in text
    assert "{{cart_id}}" in text
    assert "Static analysis" in text


def test_dependencies_ignores_description_refs(make_collection_with_request: Any) -> None:
    """Prose description {{vars}} must not create consumer edges."""
    coll, login = make_collection_with_request(req_name="DescLogin")
    prose = CollectionService.create_request(
        coll.id,
        "GET",
        "https://api.example.com/health",
        "DescOnly",
    )
    CollectionService.update_request(
        login.id,
        scripts={"test": 'pm.environment.set("token", "t");'},
    )
    CollectionService.update_request(
        prose.id,
        description="Uses {{token}} in docs only",
    )
    text = execute_workspace_query("dependencies", session_id=_session(), target_id=prose.id)
    assert "Must run first (producers):" in text
    assert "(none)" in text
    assert (
        f"postmark://request/{login.id}"
        not in text.split("Must run first")[-1].split("Depends on")[0]
    )


def test_dependencies_workspace_order_and_orphans(make_collection_with_request: Any) -> None:
    """Whole-workspace dependencies report order, orphans, and caveat."""
    coll, login = make_collection_with_request(req_name="OrdLogin")
    checkout = CollectionService.create_request(
        coll.id,
        "POST",
        "https://api.example.com/c/{{cart_id}}",
        "OrdCheckout",
    )
    orphan_req = CollectionService.create_request(
        coll.id, "GET", "https://api.example.com/x", "OrdOrphanSetter"
    )
    CollectionService.update_request(
        login.id,
        scripts={"test": 'pm.environment.set("cart_id", "1");'},
    )
    CollectionService.update_request(
        orphan_req.id,
        scripts={"test": 'pm.environment.set("unused_orphan_key", "x");'},
    )
    text = execute_workspace_query("dependencies", session_id=_session())
    assert "Suggested run order:" in text
    assert f"postmark://request/{login.id}" in text
    assert f"postmark://request/{checkout.id}" in text
    assert "unused_orphan_key" in text or "Orphan producers" in text
    assert "Static analysis" in text


def test_dependencies_cycle_detection(make_collection_with_request: Any) -> None:
    """Cyclic producer/consumer pairs are flagged as unorderable."""
    coll, a = make_collection_with_request(req_name="CycleA")
    b = CollectionService.create_request(
        coll.id, "GET", "https://api.example.com/{{b_needs}}", "CycleB"
    )
    CollectionService.update_request(
        a.id,
        url="https://api.example.com/{{a_needs}}",
        scripts={"test": 'pm.environment.set("b_needs", "1");'},
    )
    CollectionService.update_request(
        b.id,
        scripts={"test": 'pm.environment.set("a_needs", "1");'},
    )
    text = execute_workspace_query("dependencies", session_id=_session())
    assert "cycle" in text.lower() or "blocked" in text.lower()
    assert "Static analysis" in text


def test_dependencies_secret_leak(
    make_collection_with_request: Any,
) -> None:
    """Dependencies output must not include secret env values."""
    env = EnvironmentService.create_environment("DepSecretEnv")
    secret = "dep_secret_value_must_not_leak"
    EnvironmentService.update_environment_values(
        env.id,
        [{"key": "token", "value": secret, "enabled": True, "type": "secret"}],
    )
    coll, login = make_collection_with_request(req_name="DepSecLogin")
    CollectionService.create_request(
        coll.id,
        "GET",
        "https://api.example.com/{{token}}",
        "DepSecUse",
    )
    CollectionService.update_request(
        login.id,
        scripts={"test": 'pm.environment.set("token", "from_script");'},
    )
    sid = _session()
    set_workspace_snapshot(sid, {"current_env_id": env.id, "tabs": [], "active_tab_index": 0})
    text = execute_workspace_query("dependencies", session_id=sid)
    assert secret not in text


def test_walkthrough_prefers_producer_start(make_collection_with_request: Any) -> None:
    """Start here prefers a producer even when a lower-id request has no edges."""
    coll, health = make_collection_with_request(req_name="WalkHealth")
    login = CollectionService.create_request(
        coll.id, "POST", "https://api.example.com/login", "WalkLogin"
    )
    checkout = CollectionService.create_request(
        coll.id,
        "POST",
        "https://api.example.com/checkout/{{token}}",
        "WalkCheckout",
    )
    assert health.id < login.id < checkout.id
    CollectionService.update_request(
        login.id,
        scripts={"test": 'pm.environment.set("token", "t");'},
    )
    text = execute_workspace_query("walkthrough", session_id=_session(), target_id=coll.id)
    assert "Start here:" in text
    start_line = next(line for line in text.splitlines() if line.startswith("Start here:"))
    assert f"postmark://request/{login.id}" in start_line
    assert f"postmark://request/{health.id}" not in start_line
    assert "Static analysis" in text


def test_walkthrough_env_supply_unresolved(make_collection_with_request: Any) -> None:
    """Walkthrough lists vars the env must still supply, not ones it already resolved."""
    env = EnvironmentService.create_environment("WalkEnv")
    secret = "walk_env_secret_must_not_leak"
    EnvironmentService.update_environment_values(
        env.id,
        [
            {
                "key": "baseUrl",
                "value": "https://api.example.com",
                "enabled": True,
                "type": "default",
            },
            {"key": "api_key", "value": secret, "enabled": True, "type": "secret"},
        ],
    )
    coll, req = make_collection_with_request(
        req_name="WalkEnvReq",
        url="{{baseUrl}}/items/{{missing_id}}",
    )
    CollectionService.update_request(
        req.id,
        headers=[{"key": "X-Api-Key", "value": "{{api_key}}", "enabled": True}],
    )
    sid = _session()
    set_workspace_snapshot(sid, {"current_env_id": env.id, "tabs": [], "active_tab_index": 0})
    text = execute_workspace_query("walkthrough", session_id=sid, target_id=coll.id)
    assert "missing_id" in text
    # baseUrl is supplied by the env — must not appear under "supply"
    env_line = next(line for line in text.splitlines() if line.startswith("Environment:"))
    if "supply" in env_line:
        supply_part = env_line.split("supply", 1)[1]
        assert "baseUrl" not in supply_part
    assert secret not in text


def test_walkthrough_no_edges_degrades(make_collection_with_request: Any) -> None:
    """With no static edges, walkthrough does not invent a run order and keeps the caveat."""
    coll, _req = make_collection_with_request(req_name="FlatA")
    CollectionService.create_request(coll.id, "GET", "https://api.example.com/b", "FlatB")
    text = execute_workspace_query("walkthrough", session_id=_session(), target_id=coll.id)
    assert "no static dependency edges" in text.lower()
    assert " → " not in text.split("Suggested first run:")[-1].split("\n")[0]
    assert "Static analysis" in text


def test_typed_paths_merges_array_elements() -> None:
    """Array shape merges all elements — reorder/null-first must not fabricate drift."""
    a = _typed_paths([{"a": 1}, {"b": 2}])
    b = _typed_paths([{"b": 2}, {"a": 1}])
    assert a == b
    null_first = _typed_paths([None, {"a": 1}])
    assert "[]" in null_first or any(k.startswith("[]") for k in null_first)
    # Sensitive object keys are redacted in paths.
    secret_map = _typed_paths({"sk_live_abc123token": {"active": True}})
    assert "sk_live_abc123token" not in str(secret_map)
    assert REDACTED_PLACEHOLDER in str(secret_map) or "redacted" in str(secret_map).lower()


def test_insights_response_drift_paths_only(
    make_collection_with_request: Any,
    tmp_path: Any,
    monkeypatch: Any,
    qapp: Any,
) -> None:
    """response_drift reports typed paths only — never body values."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request(req_name="DriftShape")
    settings = HistorySettingsManager()
    secret_phone = "secret_phone_should_not_leak"
    _record_json(
        request_id=req.id,
        name="DriftShape",
        body=json.dumps({"user": {"email": "a@b.c", "phone": secret_phone}}),
        settings=settings,
    )
    _record_json(
        request_id=req.id,
        name="DriftShape",
        body=json.dumps({"user": {"email": "a@b.c", "phone": 555, "verified": True}}),
        settings=settings,
    )
    text = execute_workspace_query(
        "insights",
        session_id=_session(),
        search="response_drift",
    )
    assert "Response drift" in text
    assert f"postmark://request/{req.id}" in text
    assert "phone" in text
    assert secret_phone not in text
    assert "a@b.c" not in text


def test_insights_response_drift_skips_insufficient_history(
    make_collection_with_request: Any,
    tmp_path: Any,
    monkeypatch: Any,
    qapp: Any,
) -> None:
    """Fewer than two successful JSON sends → no response_drift row."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    _coll, req = make_collection_with_request(req_name="DriftSkip")
    settings = HistorySettingsManager()
    _record_json(request_id=req.id, name="DriftSkip", body='{"ok":true}', settings=settings)
    text = execute_workspace_query(
        "insights",
        session_id=_session(),
        search="response_drift",
    )
    assert f"postmark://request/{req.id}" not in text or "Response drift" not in text
