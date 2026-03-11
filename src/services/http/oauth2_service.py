"""OAuth 2.0 token exchange service.

Performs the actual HTTP token exchanges for all four grant types:

- **Authorization Code** — opens browser, starts local redirect server,
  exchanges code for token.
- **Implicit** — opens browser, captures token from redirect fragment.
- **Password Credentials** — direct POST to token endpoint.
- **Client Credentials** — direct POST to token endpoint.

All methods are ``@staticmethod`` following the project convention.
"""

from __future__ import annotations

import contextlib
import html
import http.server
import logging
import secrets
import webbrowser
from typing import TypedDict
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_REDIRECT_PORT_RANGE = (5000, 5010)


class OAuth2TokenResult(TypedDict):
    """Result of an OAuth 2.0 token exchange."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str
    error: str


class OAuth2Service:
    """Static methods for OAuth 2.0 token exchange flows."""

    @staticmethod
    def get_token(config: dict) -> OAuth2TokenResult:
        """Dispatch to the correct grant-type handler.

        *config* is the dict returned by ``OAuth2Page.get_config()``.
        """
        grant = config.get("grant_type", "authorization_code")
        if grant == "authorization_code":
            return OAuth2Service._authorization_code(config)
        if grant == "implicit":
            return OAuth2Service._implicit(config)
        if grant == "password":
            return OAuth2Service._password_credentials(config)
        if grant == "client_credentials":
            return OAuth2Service._client_credentials(config)
        return _error_result(f"Unknown grant type: {grant}")

    # ------------------------------------------------------------------
    # Grant type implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _authorization_code(config: dict) -> OAuth2TokenResult:
        """Authorization Code grant — browser + redirect + code exchange."""
        auth_url = config.get("authUrl", "")
        token_url = config.get("accessTokenUrl", "")
        client_id = config.get("clientId", "")
        client_secret = str(config.get("clientSecret", ""))
        scope = config.get("scope", "")
        state = config.get("state", "") or secrets.token_urlsafe(16)
        callback_url = config.get("callbackUrl", "")
        client_auth = config.get("client_authentication", "header")

        if not auth_url or not token_url or not client_id:
            return _error_result("Auth URL, Token URL, and Client ID are required")

        # 1. Determine redirect URI and start local server
        redirect_uri, port = _parse_redirect(callback_url)
        code_holder: dict[str, str] = {}
        server = _start_redirect_server(port, code_holder)
        if server is None:
            return _error_result(f"Could not start redirect server on port {port}")

        try:
            # 2. Open browser to authorization endpoint
            params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
            }
            browser_url = f"{auth_url}?{urlencode({k: v for k, v in params.items() if v})}"
            webbrowser.open(browser_url)

            # 3. Wait for redirect (blocking — runs on worker thread)
            server.handle_request()
            server.server_close()

            code = code_holder.get("code", "")
            returned_state = code_holder.get("state", "")
            error = code_holder.get("error", "")

            if error:
                return _error_result(f"Authorization error: {error}")
            if state and returned_state and returned_state != state:
                return _error_result("State mismatch — possible CSRF attack")
            if not code:
                return _error_result("No authorization code received")

            # 4. Exchange code for token
            return _exchange_code(
                token_url=token_url,
                code=code,
                redirect_uri=redirect_uri,
                client_id=client_id,
                client_secret=client_secret,
                client_auth=client_auth,
            )
        finally:
            with contextlib.suppress(Exception):
                server.server_close()

    @staticmethod
    def _implicit(config: dict) -> OAuth2TokenResult:
        """Implicit grant — browser redirect with token in fragment."""
        auth_url = config.get("authUrl", "")
        client_id = config.get("clientId", "")
        scope = config.get("scope", "")
        state = config.get("state", "") or secrets.token_urlsafe(16)
        callback_url = config.get("callbackUrl", "")

        if not auth_url or not client_id:
            return _error_result("Auth URL and Client ID are required")

        redirect_uri, port = _parse_redirect(callback_url)
        token_holder: dict[str, str] = {}
        server = _start_fragment_server(port, token_holder)
        if server is None:
            return _error_result(f"Could not start redirect server on port {port}")

        try:
            params = {
                "response_type": "token",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
            }
            browser_url = f"{auth_url}?{urlencode({k: v for k, v in params.items() if v})}"
            webbrowser.open(browser_url)

            # Handle two requests: first the redirect, then the JS POST
            server.handle_request()
            server.handle_request()
            server.server_close()

            error = token_holder.get("error", "")
            if error:
                return _error_result(f"Authorization error: {error}")

            access_token = token_holder.get("access_token", "")
            if not access_token:
                return _error_result("No access token received")

            return OAuth2TokenResult(
                access_token=access_token,
                token_type=token_holder.get("token_type", "Bearer"),
                expires_in=int(token_holder.get("expires_in", "0") or "0"),
                refresh_token="",
                scope=token_holder.get("scope", ""),
                error="",
            )
        finally:
            with contextlib.suppress(Exception):
                server.server_close()

    @staticmethod
    def _password_credentials(config: dict) -> OAuth2TokenResult:
        """Resource Owner Password Credentials grant — direct token request."""
        token_url = config.get("accessTokenUrl", "")
        client_id = config.get("clientId", "")
        client_secret = str(config.get("clientSecret", ""))
        username = config.get("username", "")
        password = str(config.get("password", ""))
        scope = config.get("scope", "")
        client_auth = config.get("client_authentication", "header")

        if not token_url:
            return _error_result("Access Token URL is required")

        data = {"grant_type": "password", "username": username, "password": password}
        if scope:
            data["scope"] = scope

        return _post_token_request(token_url, data, client_id, client_secret, client_auth)

    @staticmethod
    def _client_credentials(config: dict) -> OAuth2TokenResult:
        """Client Credentials grant — direct token request."""
        token_url = config.get("accessTokenUrl", "")
        client_id = config.get("clientId", "")
        client_secret = str(config.get("clientSecret", ""))
        scope = config.get("scope", "")
        client_auth = config.get("client_authentication", "header")

        if not token_url:
            return _error_result("Access Token URL is required")

        data: dict[str, str] = {"grant_type": "client_credentials"}
        if scope:
            data["scope"] = scope

        return _post_token_request(token_url, data, client_id, client_secret, client_auth)

    @staticmethod
    def refresh_token(
        token_url: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        client_auth: str = "header",
    ) -> OAuth2TokenResult:
        """Refresh an expired access token."""
        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        return _post_token_request(token_url, data, client_id, client_secret, client_auth)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _error_result(msg: str) -> OAuth2TokenResult:
    """Create an error result."""
    return OAuth2TokenResult(
        access_token="",
        token_type="",
        expires_in=0,
        refresh_token="",
        scope="",
        error=msg,
    )


def _post_token_request(
    token_url: str,
    data: dict[str, str],
    client_id: str,
    client_secret: str,
    client_auth: str,
) -> OAuth2TokenResult:
    """POST to a token endpoint and parse the response."""
    headers: dict[str, str] = {"Accept": "application/json"}
    use_basic_auth = client_auth == "header" and bool(client_id)

    if not use_basic_auth:
        data["client_id"] = client_id
        if client_secret:
            data["client_secret"] = client_secret

    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            if use_basic_auth:
                resp = client.post(
                    token_url,
                    data=data,
                    headers=headers,
                    auth=httpx.BasicAuth(client_id, client_secret),
                )
            else:
                resp = client.post(token_url, data=data, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        try:
            err_body = exc.response.json()
            msg = err_body.get("error_description", err_body.get("error", str(exc)))
        except Exception:
            msg = str(exc)
        return _error_result(msg)
    except Exception as exc:
        return _error_result(str(exc))

    return OAuth2TokenResult(
        access_token=body.get("access_token", ""),
        token_type=body.get("token_type", "Bearer"),
        expires_in=int(body.get("expires_in", 0)),
        refresh_token=body.get("refresh_token", ""),
        scope=body.get("scope", ""),
        error=body.get("error", ""),
    )


def _exchange_code(
    token_url: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
    client_auth: str,
) -> OAuth2TokenResult:
    """Exchange an authorization code for a token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    return _post_token_request(token_url, data, client_id, client_secret, client_auth)


def _parse_redirect(callback_url: str) -> tuple[str, int]:
    """Extract the redirect URI and port from the callback URL."""
    if not callback_url:
        callback_url = "http://localhost:5000/callback"
    parsed = urlparse(callback_url)
    port = parsed.port or 5000
    redirect_uri = callback_url
    return redirect_uri, port


def _start_redirect_server(
    port: int,
    result: dict[str, str],
) -> http.server.HTTPServer | None:
    """Start a one-shot HTTP server to capture the authorization code."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            """Capture code from query parameters."""
            qs = parse_qs(urlparse(self.path).query)
            result["code"] = qs.get("code", [""])[0]
            result["state"] = qs.get("state", [""])[0]
            result["error"] = qs.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization complete</h2>"
                b"<p>You can close this window.</p></body></html>"
            )

        def log_message(self, format: str, *args: object) -> None:
            """Suppress default request logging."""

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
        server.timeout = 120
        return server
    except OSError:
        logger.warning("Could not bind to port %d", port)
        return None


_FRAGMENT_CAPTURE_HTML = """\
<html><body>
<h2>Capturing token&hellip;</h2>
<script>
(function() {
  var h = window.location.hash.substring(1);
  if (h) {
    var x = new XMLHttpRequest();
    x.open("POST", "/token_callback", true);
    x.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    x.onload = function() {
      document.body.innerHTML = "<h2>Authorization complete</h2>" +
                                 "<p>You can close this window.</p>";
    };
    x.send(h);
  } else {
    document.body.innerHTML = "<h2>No token received</h2>";
  }
})();
</script>
</body></html>"""


def _start_fragment_server(
    port: int,
    result: dict[str, str],
) -> http.server.HTTPServer | None:
    """Start a server that captures token from URL fragment via JS POST."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            """Serve the fragment-capture HTML page."""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_FRAGMENT_CAPTURE_HTML.encode())

        def do_POST(self) -> None:
            """Receive the token fragment forwarded by JS."""
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            params = parse_qs(body)
            for key in ("access_token", "token_type", "expires_in", "scope", "error"):
                vals = params.get(key, [])
                if vals:
                    result[key] = html.escape(vals[0])
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            """Suppress default request logging."""

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
        server.timeout = 120
        return server
    except OSError:
        logger.warning("Could not bind to port %d", port)
        return None
