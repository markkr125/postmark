"""Credential-blind OAuth Get Token (v1: non-browser grants only)."""

from __future__ import annotations

from typing import Any


_V1_GRANTS = frozenset({"client_credentials", "password"})


def _entries_to_map(entries: Any) -> dict[str, str]:
    """Convert Postman-style auth entries to a key→value map."""
    out: dict[str, str] = {}
    if not isinstance(entries, list):
        return out
    for item in entries:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        out[key] = str(item.get("value") or "")
    return out


def _oauth_config_from_auth(auth: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build OAuth2Service config from a saved request auth dict."""
    if not isinstance(auth, dict):
        return None
    if str(auth.get("type") or "").casefold() != "oauth2":
        return None
    entries = auth.get("oauth2")
    entry_map = _entries_to_map(entries)
    grant = str(entry_map.get("grant_type") or "client_credentials").strip()
    config: dict[str, Any] = {"grant_type": grant}
    for key in (
        "accessTokenUrl",
        "authUrl",
        "clientId",
        "clientSecret",
        "username",
        "password",
        "scope",
        "state",
        "callbackUrl",
        "client_authentication",
        "tokenName",
    ):
        value = entry_map.get(key)
        if value:
            config[key] = value
    return config


def _substitute_oauth_config(
    config: dict[str, Any],
    *,
    environment_id: int,
    request_id: int | None,
) -> dict[str, Any]:
    """Resolve ``{{var}}`` placeholders in OAuth config string fields."""
    from services.environment_service import EnvironmentService

    variables = EnvironmentService.build_combined_variable_map(
        environment_id,
        request_id,
    )
    if not variables:
        return dict(config)
    sub = EnvironmentService.substitute
    out: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, str) and "{{" in value:
            out[key] = sub(value, variables)
        else:
            out[key] = value
    return out


def _bind_token_to_environment(
    *,
    environment_id: int,
    bound_var: str,
    token: str,
) -> None:
    """Upsert *bound_var* as a secret environment value (token never returned)."""
    from services.environment_service import EnvironmentService

    env = EnvironmentService.get_environment(environment_id)
    if env is None:
        raise ValueError(f"environment_not_found:{environment_id}")
    values = list(env.values or [])
    updated = False
    for row in values:
        if not isinstance(row, dict):
            continue
        if str(row.get("key") or "") == bound_var:
            row["value"] = token
            row["type"] = "secret"
            row["enabled"] = True
            updated = True
            break
    if not updated:
        values.append(
            {
                "key": bound_var,
                "value": token,
                "type": "secret",
                "enabled": True,
            }
        )
    EnvironmentService.update_environment_values(environment_id, values)


def _set_auth_access_token_placeholder(
    *,
    request_id: int,
    bound_var: str,
) -> None:
    """Set request oauth2 accessToken to ``{{bound_var}}`` only."""
    from services.collection_service import CollectionService

    req = CollectionService.get_request(request_id)
    if req is None:
        return
    auth = dict(req.auth) if isinstance(req.auth, dict) else {"type": "oauth2", "oauth2": []}
    auth["type"] = "oauth2"
    entries = list(auth.get("oauth2") or []) if isinstance(auth.get("oauth2"), list) else []
    placeholder = "{{" + bound_var + "}}"
    found = False
    for item in entries:
        if isinstance(item, dict) and str(item.get("key") or "") == "accessToken":
            item["value"] = placeholder
            found = True
            break
    if not found:
        entries.append({"key": "accessToken", "value": placeholder, "type": "string"})
    auth["oauth2"] = entries
    CollectionService.update_request(request_id, auth=auth)


def run_oauth_get_token(
    *,
    request_id: int | None = None,
    environment_id: int | None = None,
    bound_var: str | None = None,
    oauth_config: dict[str, Any] | None = None,
    update_auth_placeholder: bool = True,
) -> dict[str, Any]:
    """Exchange OAuth credentials (v1 non-browser) and bind token to an env var.

    Resolves ``{{var}}`` placeholders in the OAuth config from the bind
    environment (and request collection chain when *request_id* is set)
    before calling :meth:`OAuth2Service.get_token`.  The access token never
    appears in the returned dict.
    """
    from services.ai.chat.mutation.bridge import enqueue_mutation_event
    from services.collection_service import CollectionService
    from services.http.oauth2_service import OAuth2Service

    var_name = (bound_var or "oauth_access_token").strip()
    if not var_name or not var_name.replace("_", "").isalnum():
        return {
            "ok": False,
            "error": "invalid_bound_var",
            "message": "bound_var must be alphanumeric/underscore",
        }
    if environment_id is None:
        return {
            "ok": False,
            "error": "environment_id_required",
            "message": "environment_id is required to bind the token",
        }

    config: dict[str, Any] | None = None
    if isinstance(oauth_config, dict) and oauth_config:
        config = dict(oauth_config)
    elif request_id is not None:
        auth = CollectionService.get_request_auth_chain(request_id)
        config = _oauth_config_from_auth(auth)
    if not config:
        return {
            "ok": False,
            "error": "oauth_config_required",
            "message": "Provide request_id with oauth2 auth or oauth_config",
        }

    grant = str(config.get("grant_type") or "client_credentials").strip()
    if not grant:
        grant = "client_credentials"
    config["grant_type"] = grant
    if grant not in _V1_GRANTS:
        return {
            "ok": False,
            "error": "browser_grant_not_supported",
            "message": (
                f"Grant {grant!r} requires browser HITL (oauth v2). "
                "Use client_credentials or password."
            ),
        }

    config = _substitute_oauth_config(
        config,
        environment_id=int(environment_id),
        request_id=request_id,
    )
    result = OAuth2Service.get_token(config)
    if result.get("error"):
        return {
            "ok": False,
            "error": "oauth_failed",
            "message": str(result.get("error")),
        }
    token = str(result.get("access_token") or "")
    if not token:
        return {
            "ok": False,
            "error": "empty_access_token",
            "message": "Token endpoint returned no access_token",
        }

    try:
        _bind_token_to_environment(
            environment_id=environment_id,
            bound_var=var_name,
            token=token,
        )
    except ValueError as exc:
        return {"ok": False, "error": "bind_failed", "message": str(exc)}

    auth_updated = False
    ids: dict[str, int] = {"environment_id": int(environment_id)}
    if update_auth_placeholder and request_id is not None:
        _set_auth_access_token_placeholder(request_id=request_id, bound_var=var_name)
        auth_updated = True
        ids["request_id"] = int(request_id)

    enqueue_mutation_event(
        {
            "type": "mutated",
            "entity": "environment",
            "action": "update",
            "ids": {"environment_id": int(environment_id)},
            "payload": {"summary": f"Bound OAuth token to {{{{{var_name}}}}}"},
        }
    )
    if auth_updated and request_id is not None:
        enqueue_mutation_event(
            {
                "type": "open_target",
                "open_target": {"kind": "request", "id": int(request_id), "focus": "auth"},
            }
        )

    # Never include the token value in the observation.
    return {
        "ok": True,
        "summary": f"OAuth token bound to {{{{{var_name}}}}}",
        "bound_var": var_name,
        "token_type": str(result.get("token_type") or "Bearer"),
        "expires_in": int(result.get("expires_in") or 0),
        "auth_updated": auth_updated,
        "ids": ids,
    }
