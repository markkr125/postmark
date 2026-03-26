# Auth Handler

Shared authentication header injection for HTTP requests.  Supports 12
authentication types.

Source: `src/services/http/auth_handler.py`

## `apply_auth`

```python
def apply_auth(
    auth: dict | None,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]
```

Apply authentication to a request by modifying the URL and/or headers.

**Parameters:**
- `auth` — auth config dict with a `"type"` key and type-specific
  nested dict.  Example: `{"type": "bearer", "bearer": {"token": "abc"}}`.
  If `None` or `{"type": "noauth"}`, no changes are made.
- `url` — the request URL (may be modified for API key in query params).
- `headers` — mutable headers dict (modified in place for most auth types).
- `method` — HTTP method (needed by some auth types like AWS Signature).
- `body` — request body (needed by some auth types like Digest, Hawk).

**Returns:** `(url, headers)` — potentially modified URL and headers dict.

## Supported Auth Types

| Type Key | Auth Type | Header/Mechanism |
|----------|-----------|-----------------|
| `bearer` | Bearer Token | `Authorization: Bearer <token>` |
| `basic` | Basic Auth | `Authorization: Basic <base64>` |
| `apikey` | API Key | Header or query parameter |
| `digest` | Digest Auth | `Authorization: Digest <params>` |
| `oauth1` | OAuth 1.0 | `Authorization: OAuth <params>` |
| `oauth2` | OAuth 2.0 | `Authorization: Bearer <token>` |
| `hawk` | Hawk Auth | `Authorization: Hawk <params>` |
| `awsv4` | AWS Signature v4 | `Authorization: AWS4-HMAC-SHA256 <params>` |
| `jwt` | JWT Bearer | `Authorization: Bearer <jwt>` |
| `asap` | Atlassian ASAP | `Authorization: Bearer <asap>` |
| `ntlm` | NTLM | `Authorization: NTLM <token>` |
| `edgegrid` | Akamai EdgeGrid | `Authorization: EG1-HMAC-SHA256 <params>` |

## Auth Config Structure

Each auth type stores its parameters in a nested dict keyed by the type
name:

```python
# Bearer
{"type": "bearer", "bearer": {"token": "abc123"}}

# Basic
{"type": "basic", "basic": {"username": "user", "password": "pass"}}

# API Key
{"type": "apikey", "apikey": {"key": "X-API-Key", "value": "secret", "in": "header"}}

# OAuth 2.0
{"type": "oauth2", "oauth2": {"access_token": "token123", "token_type": "Bearer"}}

# Inherit from parent
{"type": "inherit"}

# No auth
{"type": "noauth"}
```

## Field Specs

Per-type field definitions for the UI are in `AUTH_FIELD_SPECS`
(`src/ui/request/auth/auth_field_specs.py`).  See
[Adding an Auth Type](../../guides/adding-auth-type.md) for the full
workflow.
