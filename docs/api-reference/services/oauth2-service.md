# OAuth2Service

OAuth 2.0 token exchange supporting 4 grant types.  All methods are
`@staticmethod`.

Source: `src/services/http/oauth2_service.py`

## Methods

### `get_token`

```python
@staticmethod
def get_token(config: dict) -> OAuth2TokenResult
```

Exchange credentials for an access token.  The `config` dict must
contain `grant_type` and grant-type-specific fields.

**Supported grant types:**

| Grant Type | Config Keys |
|-----------|-------------|
| `authorization_code` | `token_url`, `code`, `redirect_uri`, `client_id`, `client_secret`, `client_auth` |
| `client_credentials` | `token_url`, `client_id`, `client_secret`, `client_auth`, `scope` |
| `password` | `token_url`, `username`, `password`, `client_id`, `client_secret`, `client_auth`, `scope` |
| `implicit` | — (handled client-side, no server call) |

**`client_auth`** controls how client credentials are sent:
- `"header"` — HTTP Basic auth header (default)
- `"body"` — POST body parameters

### `refresh_token`

```python
@staticmethod
def refresh_token(
    token_url: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    client_auth: str = "header",
) -> OAuth2TokenResult
```

Exchange a refresh token for a new access token.

## OAuth2TokenResult

```python
class OAuth2TokenResult(TypedDict):
    access_token: str     # The access token
    token_type: str       # Token type (usually "Bearer")
    expires_in: int       # Token lifetime in seconds
    refresh_token: str    # Refresh token (if provided)
    scope: str            # Granted scope
    error: str            # Error message (empty on success)
```
