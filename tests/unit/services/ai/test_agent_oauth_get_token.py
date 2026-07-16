"""Tests for credential-blind OAuth Get Token v1."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from services.ai.chat.execution.oauth.get_token import run_oauth_get_token
from services.ai.chat.tools.workspace_execute.tool import WorkspaceExecuteAction
from services.collection_service import CollectionService
from services.environment_service import EnvironmentService


def _fake_token(*, access: str = "SUPER_SECRET_ACCESS_TOKEN") -> dict[str, Any]:
    """Return a mock OAuth2Service.get_token success payload."""
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "",
        "scope": "",
        "error": "",
    }


class TestOauthGetTokenV1:
    """Token never appears in observations; bound to env {{var}}."""

    def test_client_credentials_binds_env(self) -> None:
        """Successful exchange writes secret env value and placeholder auth."""
        env = EnvironmentService.create_environment("OAuth Env", values=[])
        col = CollectionService.create_collection("OAuth Col")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://api.example.com",
            "Authed",
        )
        CollectionService.update_request(
            int(req.id),
            auth={
                "type": "oauth2",
                "oauth2": [
                    {"key": "grant_type", "value": "client_credentials", "type": "string"},
                    {
                        "key": "accessTokenUrl",
                        "value": "https://auth.example/token",
                        "type": "string",
                    },
                    {"key": "clientId", "value": "cid", "type": "string"},
                    {"key": "clientSecret", "value": "csecret", "type": "string"},
                ],
            },
        )
        with patch(
            "services.http.oauth2_service.OAuth2Service.get_token",
            return_value=_fake_token(),
        ):
            result = run_oauth_get_token(
                request_id=int(req.id),
                environment_id=int(env.id),
                bound_var="oauth_access_token",
            )
        assert result["ok"] is True
        assert result.get("bound_var") == "oauth_access_token"
        assert result.get("auth_updated") is True
        assert result.get("token_type") == "Bearer"
        assert result.get("expires_in") == 3600
        obs_blob = str(result)
        assert "SUPER_SECRET_ACCESS_TOKEN" not in obs_blob
        assert "access_token:" not in obs_blob
        reloaded = EnvironmentService.get_environment(int(env.id))
        assert reloaded is not None
        values = {str(v.get("key")): v for v in (reloaded.values or []) if isinstance(v, dict)}
        assert values["oauth_access_token"]["value"] == "SUPER_SECRET_ACCESS_TOKEN"
        assert values["oauth_access_token"].get("type") == "secret"
        auth = CollectionService.get_request(int(req.id))
        assert auth is not None
        entries = (auth.auth or {}).get("oauth2") or []
        access = next(
            (e for e in entries if isinstance(e, dict) and e.get("key") == "accessToken"),
            None,
        )
        assert access is not None
        assert access.get("value") == "{{oauth_access_token}}"

    def test_password_grant_binds_env(self) -> None:
        """Password grant exchanges and binds without returning the token."""
        env = EnvironmentService.create_environment("OAuth Password Env", values=[])
        captured: dict[str, Any] = {}

        def _capture(config: dict[str, Any]) -> dict[str, Any]:
            captured.update(config)
            return _fake_token(access="PASSWORD_GRANT_TOKEN_VALUE")

        with patch(
            "services.http.oauth2_service.OAuth2Service.get_token",
            side_effect=_capture,
        ):
            result = run_oauth_get_token(
                environment_id=int(env.id),
                bound_var="pw_token",
                oauth_config={
                    "grant_type": "password",
                    "accessTokenUrl": "https://auth.example/token",
                    "clientId": "cid",
                    "clientSecret": "csecret",
                    "username": "user",
                    "password": "secret-pass",
                },
                update_auth_placeholder=False,
            )
        assert result["ok"] is True
        assert result.get("bound_var") == "pw_token"
        assert result.get("auth_updated") is False
        assert captured.get("grant_type") == "password"
        assert "PASSWORD_GRANT_TOKEN_VALUE" not in str(result)
        reloaded = EnvironmentService.get_environment(int(env.id))
        assert reloaded is not None
        values = {str(v.get("key")): v for v in (reloaded.values or []) if isinstance(v, dict)}
        assert values["pw_token"]["value"] == "PASSWORD_GRANT_TOKEN_VALUE"

    def test_substitutes_env_placeholders_in_config(self) -> None:
        """``{{var}}`` credentials resolve from the bind environment before exchange."""
        env = EnvironmentService.create_environment(
            "OAuth Sub Env",
            values=[
                {
                    "key": "oauth_client_secret",
                    "value": "resolved-secret",
                    "type": "secret",
                    "enabled": True,
                },
            ],
        )
        captured: dict[str, Any] = {}

        def _capture(config: dict[str, Any]) -> dict[str, Any]:
            captured.update(config)
            return _fake_token()

        with patch(
            "services.http.oauth2_service.OAuth2Service.get_token",
            side_effect=_capture,
        ):
            result = run_oauth_get_token(
                environment_id=int(env.id),
                bound_var="oauth_access_token",
                oauth_config={
                    "grant_type": "client_credentials",
                    "accessTokenUrl": "https://auth.example/token",
                    "clientId": "cid",
                    "clientSecret": "{{oauth_client_secret}}",
                },
                update_auth_placeholder=False,
            )
        assert result["ok"] is True
        assert captured.get("clientSecret") == "resolved-secret"
        assert "resolved-secret" not in str(result)

    def test_rejects_browser_grant(self) -> None:
        """Authorization-code grants are not supported in v1."""
        env = EnvironmentService.create_environment("OAuth Env2", values=[])
        result = run_oauth_get_token(
            environment_id=int(env.id),
            oauth_config={"grant_type": "authorization_code", "authUrl": "https://x"},
        )
        assert result["ok"] is False
        assert result["error"] == "browser_grant_not_supported"

    def test_dispatch_observation_excludes_token(self) -> None:
        """Successful execute observation includes auth_updated, never the token."""
        from services.ai.chat.tools.workspace_execute.tool import _execute

        env = EnvironmentService.create_environment("OAuth Obs Env", values=[])
        col = CollectionService.create_collection("OAuth Obs Col")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://api.example.com",
            "Authed",
        )
        CollectionService.update_request(
            int(req.id),
            auth={
                "type": "oauth2",
                "oauth2": [
                    {"key": "grant_type", "value": "client_credentials", "type": "string"},
                    {
                        "key": "accessTokenUrl",
                        "value": "https://auth.example/token",
                        "type": "string",
                    },
                    {"key": "clientId", "value": "cid", "type": "string"},
                    {"key": "clientSecret", "value": "csecret", "type": "string"},
                ],
            },
        )
        action = WorkspaceExecuteAction(
            operation="oauth_get_token",
            request_id=int(req.id),
            environment_id=int(env.id),
            bound_var="oauth_access_token",
        )
        with patch(
            "services.http.oauth2_service.OAuth2Service.get_token",
            return_value=_fake_token(),
        ):
            obs = _execute(action)
        content = str(getattr(obs, "text", obs))
        assert "ok: true" in content
        assert "auth_updated: True" in content
        assert "bound_var: oauth_access_token" in content
        assert "SUPER_SECRET_ACCESS_TOKEN" not in content
        assert "access_token:" not in content
