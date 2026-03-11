"""Tests for the OAuth 2.0 token exchange service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from services.http.oauth2_service import (OAuth2Service, _error_result,
                                          _parse_redirect, _post_token_request)

# ------------------------------------------------------------------
# Helper function tests
# ------------------------------------------------------------------


class TestErrorResult:
    """Verify _error_result helper builds correct TypedDict."""

    def test_fields(self) -> None:
        """All fields present with error message."""
        result = _error_result("boom")
        assert result["error"] == "boom"
        assert result["access_token"] == ""
        assert result["token_type"] == ""
        assert result["expires_in"] == 0
        assert result["refresh_token"] == ""
        assert result["scope"] == ""


class TestParseRedirect:
    """Verify _parse_redirect extracts URI and port."""

    def test_with_explicit_url(self) -> None:
        """Explicit callback URL returns correct port."""
        uri, port = _parse_redirect("http://localhost:9876/callback")
        assert uri == "http://localhost:9876/callback"
        assert port == 9876

    def test_default_when_empty(self) -> None:
        """Empty callback falls back to localhost:5000."""
        uri, port = _parse_redirect("")
        assert port == 5000
        assert "localhost" in uri

    def test_no_port_defaults_to_5000(self) -> None:
        """URL without port defaults to 5000."""
        _, port = _parse_redirect("http://localhost/callback")
        assert port == 5000


# ------------------------------------------------------------------
# Direct grant type tests (mock httpx)
# ------------------------------------------------------------------


def _mock_token_response(
    *,
    access_token: str = "test_access_token",
    token_type: str = "Bearer",
    expires_in: int = 3600,
    refresh_token: str = "test_refresh",
    scope: str = "read",
) -> MagicMock:
    """Create a mock httpx.Response for a successful token exchange."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": access_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "refresh_token": refresh_token,
        "scope": scope,
    }
    resp.raise_for_status = MagicMock()
    return resp


class TestPasswordGrant:
    """Password Credentials grant — direct POST."""

    def test_missing_token_url(self) -> None:
        """Returns error when token URL is empty."""
        result = OAuth2Service._password_credentials({"accessTokenUrl": ""})
        assert result["error"]

    @patch("services.http.oauth2_service.httpx.Client")
    def test_successful_exchange(self, mock_client_cls: MagicMock) -> None:
        """Successful password grant returns token."""
        mock_resp = _mock_token_response()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        config = {
            "grant_type": "password",
            "accessTokenUrl": "https://auth.example.com/token",
            "clientId": "my_client",
            "clientSecret": "my_secret",
            "username": "user",
            "password": "pass",
            "scope": "read",
            "client_authentication": "header",
        }
        result = OAuth2Service.get_token(config)

        assert result["access_token"] == "test_access_token"
        assert result["token_type"] == "Bearer"
        assert result["error"] == ""

        # Verify client credentials in Basic Auth
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs.get("auth") is not None

    @patch("services.http.oauth2_service.httpx.Client")
    def test_body_auth(self, mock_client_cls: MagicMock) -> None:
        """Body auth sends client_id/secret in POST body."""
        mock_resp = _mock_token_response()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        config = {
            "grant_type": "password",
            "accessTokenUrl": "https://auth.example.com/token",
            "clientId": "my_client",
            "clientSecret": "my_secret",
            "username": "user",
            "password": "pass",
            "client_authentication": "body",
        }
        result = OAuth2Service.get_token(config)

        assert result["access_token"] == "test_access_token"
        call_kwargs = mock_client.post.call_args
        post_data = call_kwargs.kwargs.get("data", call_kwargs[1].get("data", {}))
        assert post_data.get("client_id") == "my_client"


class TestClientCredentialsGrant:
    """Client Credentials grant — direct POST."""

    def test_missing_token_url(self) -> None:
        """Returns error when token URL is empty."""
        result = OAuth2Service._client_credentials({"accessTokenUrl": ""})
        assert result["error"]

    @patch("services.http.oauth2_service.httpx.Client")
    def test_successful_exchange(self, mock_client_cls: MagicMock) -> None:
        """Successful client_credentials grant returns token."""
        mock_resp = _mock_token_response(refresh_token="")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        config = {
            "grant_type": "client_credentials",
            "accessTokenUrl": "https://auth.example.com/token",
            "clientId": "service_client",
            "clientSecret": "service_secret",
            "scope": "api",
            "client_authentication": "header",
        }
        result = OAuth2Service.get_token(config)

        assert result["access_token"] == "test_access_token"
        assert result["error"] == ""

    @patch("services.http.oauth2_service.httpx.Client")
    def test_scope_included(self, mock_client_cls: MagicMock) -> None:
        """Scope is included in the POST data when provided."""
        mock_resp = _mock_token_response()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        config = {
            "grant_type": "client_credentials",
            "accessTokenUrl": "https://auth.example.com/token",
            "clientId": "cid",
            "clientSecret": "csec",
            "scope": "admin",
            "client_authentication": "body",
        }
        OAuth2Service.get_token(config)

        call_kwargs = mock_client.post.call_args
        post_data = call_kwargs.kwargs.get("data", call_kwargs[1].get("data", {}))
        assert post_data.get("scope") == "admin"


class TestPostTokenRequest:
    """Verify _post_token_request handles errors."""

    @patch("services.http.oauth2_service.httpx.Client")
    def test_http_error_with_json(self, mock_client_cls: MagicMock) -> None:
        """HTTP error with JSON body extracts error_description."""
        error_resp = MagicMock(spec=httpx.Response)
        error_resp.status_code = 400
        error_resp.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Bad credentials",
        }
        exc = httpx.HTTPStatusError(
            "400",
            request=MagicMock(),
            response=error_resp,
        )
        error_resp.raise_for_status.side_effect = exc

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = error_resp
        mock_client_cls.return_value = mock_client

        result = _post_token_request(
            "https://auth.example.com/token",
            {"grant_type": "password"},
            "cid",
            "csec",
            "header",
        )
        assert "Bad credentials" in result["error"]

    @patch("services.http.oauth2_service.httpx.Client")
    def test_connection_error(self, mock_client_cls: MagicMock) -> None:
        """Connection error returns error result."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client_cls.return_value = mock_client

        result = _post_token_request(
            "https://auth.example.com/token",
            {"grant_type": "client_credentials"},
            "cid",
            "csec",
            "header",
        )
        assert result["error"]


class TestGetTokenDispatch:
    """Verify get_token dispatches to correct handler."""

    def test_unknown_grant_type(self) -> None:
        """Unknown grant type returns error."""
        result = OAuth2Service.get_token({"grant_type": "unknown"})
        assert "Unknown grant type" in result["error"]

    def test_authorization_code_missing_fields(self) -> None:
        """Auth code grant with missing fields returns error."""
        result = OAuth2Service.get_token(
            {
                "grant_type": "authorization_code",
                "authUrl": "",
                "accessTokenUrl": "",
                "clientId": "",
            }
        )
        assert result["error"]

    def test_implicit_missing_fields(self) -> None:
        """Implicit grant with missing fields returns error."""
        result = OAuth2Service.get_token(
            {
                "grant_type": "implicit",
                "authUrl": "",
                "clientId": "",
            }
        )
        assert result["error"]
