"""Shared auth header injection for HTTP send and snippet generation.

Computes and injects authentication credentials into request headers
or URL query parameters.  Used by :mod:`ui.request.http_worker`
(actual send) and :mod:`services.http.snippet_generator.generator`
(code snippets).

Every handler receives already-substituted values — variable
replacement is the caller's responsibility.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import Callable
from urllib.parse import parse_qs, quote, urlencode, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_Handler = Callable[..., tuple[str, dict[str, str]]]


def _entries_map(auth: dict, auth_type: str) -> dict[str, str]:
    """Extract Postman key-value entries into a flat ``{key: value}`` map.

    Booleans are normalised to lowercase ``"true"`` / ``"false"``
    strings so that callers can compare consistently.
    """
    result: dict[str, str] = {}
    for entry in auth.get(auth_type, []):
        if isinstance(entry, dict):
            val = entry.get("value", "")
            if isinstance(val, bool):
                result[entry["key"]] = "true" if val else "false"
            elif isinstance(val, str):
                result[entry["key"]] = val
            else:
                result[entry["key"]] = str(val)
    return result


def _b64url(data: bytes) -> str:
    """Base64url-encode *data* without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _percent_encode(s: str) -> str:
    """RFC 5849 percent-encoding (unreserved characters only)."""
    return quote(s, safe="")


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    """Return the raw HMAC-SHA256 digest."""
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_auth(
    auth: dict | None,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Inject auth credentials into *headers* and/or *url*.

    Returns the (possibly modified) ``(url, headers)`` pair.
    *method* and *body* are required by schemes that include them in
    the signature (Digest, OAuth 1.0, Hawk, AWS SigV4, EdgeGrid).
    """
    if not auth:
        return url, headers
    auth_type = auth.get("type", "noauth")
    handler = _HANDLERS.get(auth_type)
    if handler:
        url, headers = handler(auth, url, headers, method=method, body=body)
    return url, headers


# ---------------------------------------------------------------------------
# Simple token / credential types
# ---------------------------------------------------------------------------


def _apply_bearer(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Bearer token — ``Authorization: Bearer <token>``."""
    token = _entries_map(auth, "bearer").get("token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return url, headers


def _apply_basic(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Basic auth — ``Authorization: Basic <base64>``."""
    v = _entries_map(auth, "basic")
    username, password = v.get("username", ""), v.get("password", "")
    if username or password:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    return url, headers


def _apply_apikey(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """API key — custom header or query parameter."""
    v = _entries_map(auth, "apikey")
    key, value, add_to = v.get("key", ""), v.get("value", ""), v.get("in", "header")
    if key and value:
        if add_to == "header":
            headers[key] = value
        else:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{_percent_encode(key)}={_percent_encode(value)}"
    return url, headers


def _apply_oauth2(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """OAuth 2.0 manual token — ``Authorization: <prefix> <token>``."""
    v = _entries_map(auth, "oauth2")
    token = v.get("accessToken", "")
    prefix = v.get("headerPrefix", "Bearer")
    add_to = v.get("addTokenTo", "header")
    if token:
        if add_to == "header":
            headers["Authorization"] = f"{prefix} {token}" if prefix else token
        else:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}access_token={_percent_encode(token)}"
    return url, headers


# ---------------------------------------------------------------------------
# Digest Auth (RFC 7616)
# ---------------------------------------------------------------------------

_DIGEST_HASH: dict[str, str] = {
    "MD5": "md5",
    "MD5-sess": "md5",
    "SHA-256": "sha256",
    "SHA-256-sess": "sha256",
    "SHA-512-256": "sha512_256",
    "SHA-512-256-sess": "sha512_256",
}


def _apply_digest(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Digest auth — ``Authorization: Digest ...``."""
    v = _entries_map(auth, "digest")
    username, password = v.get("username", ""), v.get("password", "")
    realm, nonce = v.get("realm", ""), v.get("nonce", "")
    algorithm = v.get("algorithm", "MD5")
    qop = v.get("qop", "")
    nc = v.get("nonceCount", "00000001")
    cnonce = v.get("clientNonce", "") or secrets.token_hex(8)
    opaque = v.get("opaque", "")

    uri = urlparse(url).path or "/"
    hash_name = _DIGEST_HASH.get(algorithm, "md5")

    def _h(data: str) -> str:
        return hashlib.new(hash_name, data.encode()).hexdigest()

    a1 = f"{username}:{realm}:{password}"
    if algorithm.endswith("-sess"):
        a1 = f"{_h(a1)}:{nonce}:{cnonce}"

    a2 = f"{method}:{uri}"
    if qop == "auth-int" and body:
        a2 = f"{method}:{uri}:{_h(body)}"

    ha1, ha2 = _h(a1), _h(a2)
    if qop in ("auth", "auth-int"):
        response = _h(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
    else:
        response = _h(f"{ha1}:{nonce}:{ha2}")

    parts = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f"algorithm={algorithm}",
        f'response="{response}"',
    ]
    if qop:
        parts.extend([f"qop={qop}", f"nc={nc}", f'cnonce="{cnonce}"'])
    if opaque:
        parts.append(f'opaque="{opaque}"')
    headers["Authorization"] = f"Digest {', '.join(parts)}"
    return url, headers


# ---------------------------------------------------------------------------
# OAuth 1.0 (RFC 5849)
# ---------------------------------------------------------------------------


def _apply_oauth1(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """OAuth 1.0 — ``Authorization: OAuth ...`` or query/body params."""
    v = _entries_map(auth, "oauth1")
    consumer_key = v.get("consumerKey", "")
    consumer_secret = v.get("consumerSecret", "")
    token = v.get("token", "")
    token_secret = v.get("tokenSecret", "")
    sig_method = v.get("signatureMethod", "HMAC-SHA1")
    timestamp = v.get("timestamp", "") or str(int(time.time()))
    nonce = v.get("nonce", "") or secrets.token_hex(16)
    version = v.get("version", "1.0")
    realm = v.get("realm", "")
    callback_url = v.get("callbackUrl", "")
    verifier = v.get("verifier", "")
    include_body_hash = v.get("includeBodyHash", "false") == "true"
    add_empty = v.get("addEmptyParamsToSign", "false") == "true"
    to_header_raw = v.get("addParamsToHeader", "true")

    # 1. Collect OAuth params
    oauth: dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_signature_method": sig_method,
        "oauth_timestamp": timestamp,
        "oauth_nonce": nonce,
        "oauth_version": version,
    }
    if token:
        oauth["oauth_token"] = token
    if callback_url:
        oauth["oauth_callback"] = callback_url
    if verifier:
        oauth["oauth_verifier"] = verifier

    # Body hash (RFC 5849 §3.4.1.3.1)
    if include_body_hash and body:
        if sig_method == "HMAC-SHA256":
            bh = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        else:
            bh = base64.b64encode(hashlib.sha1(body.encode()).digest()).decode()
        oauth["oauth_body_hash"] = bh

    # Add empty params if requested
    if add_empty:
        for k, val in list(oauth.items()):
            if not val:
                oauth[k] = ""

    # 2. Merge query params for base-string
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    all_params: list[tuple[str, str]] = []
    for k, vals in parse_qs(parsed.query, keep_blank_values=True).items():
        for val in vals:
            all_params.append((k, val))
    all_params.extend(oauth.items())

    # 3. Base string
    param_str = "&".join(
        f"{_percent_encode(k)}={_percent_encode(val)}" for k, val in sorted(all_params)
    )
    base_string = f"{method.upper()}&{_percent_encode(base_url)}&{_percent_encode(param_str)}"

    # 4. Signature
    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"
    if sig_method == "HMAC-SHA1":
        raw_sig = hmac.new(
            signing_key.encode(),
            base_string.encode(),
            hashlib.sha1,
        ).digest()
        sig = base64.b64encode(raw_sig).decode()
    elif sig_method == "HMAC-SHA256":
        raw_sig = hmac.new(
            signing_key.encode(),
            base_string.encode(),
            hashlib.sha256,
        ).digest()
        sig = base64.b64encode(raw_sig).decode()
    elif sig_method == "PLAINTEXT":
        sig = signing_key
    else:
        sig = ""
        logger.warning("OAuth 1.0 %s requires external libraries", sig_method)
    oauth["oauth_signature"] = sig

    # 5. Emit — "true" = headers, "false" = URL query, "body" = request body
    if to_header_raw == "true":
        parts = [
            f'{_percent_encode(k)}="{_percent_encode(val)}"' for k, val in sorted(oauth.items())
        ]
        if realm:
            parts.insert(0, f'realm="{realm}"')
        headers["Authorization"] = f"OAuth {', '.join(parts)}"
    else:
        qs = urlencode(oauth)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{qs}"
    return url, headers


# ---------------------------------------------------------------------------
# Hawk Authentication
# ---------------------------------------------------------------------------


def _apply_hawk(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Hawk auth — ``Authorization: Hawk id=... mac=...``."""
    v = _entries_map(auth, "hawk")
    auth_id = v.get("authId", "")
    auth_key = v.get("authKey", "")
    algorithm = v.get("algorithm", "sha256")
    nonce = v.get("nonce", "") or secrets.token_hex(8)
    ext = v.get("extraData", "")
    app_id = v.get("appId", "")
    delegation = v.get("delegation", "")
    ts = v.get("timestamp", "") or str(int(time.time()))
    include_hash = v.get("includePayloadHash", "false") == "true"

    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
    resource = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    # Payload hash (gated by includePayloadHash checkbox)
    payload_hash = ""
    if include_hash and body:
        ctype = headers.get("Content-Type", "").split(";")[0].strip()
        hash_input = f"hawk.1.payload\n{ctype}\n{body}\n"
        raw = hashlib.new(algorithm, hash_input.encode()).digest()
        payload_hash = base64.b64encode(raw).decode()

    # Normalised string
    normalized = (
        f"hawk.1.header\n{ts}\n{nonce}\n{method.upper()}\n"
        f"{resource}\n{host}\n{port}\n{payload_hash}\n{ext}\n"
    )
    if app_id:
        normalized += f"{app_id}\n{delegation}\n"

    mac = base64.b64encode(
        hmac.new(auth_key.encode(), normalized.encode(), algorithm).digest(),
    ).decode()

    parts = [f'id="{auth_id}"', f'ts="{ts}"', f'nonce="{nonce}"', f'mac="{mac}"']
    if payload_hash:
        parts.append(f'hash="{payload_hash}"')
    if ext:
        parts.append(f'ext="{ext}"')
    if app_id:
        parts.append(f'app="{app_id}"')
    if delegation:
        parts.append(f'dlg="{delegation}"')
    headers["Authorization"] = f"Hawk {', '.join(parts)}"
    return url, headers


# ---------------------------------------------------------------------------
# AWS Signature V4
# ---------------------------------------------------------------------------


def _apply_awsv4(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """AWS SigV4 — ``Authorization: AWS4-HMAC-SHA256 ...``."""
    v = _entries_map(auth, "awsv4")
    access_key = v.get("accessKey", "")
    secret_key = v.get("secretKey", "")
    region = v.get("region", "us-east-1")
    service = v.get("service", "")
    session_token = v.get("sessionToken", "")

    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    parsed = urlparse(url)
    host = parsed.netloc
    uri = parsed.path or "/"
    payload_hash = hashlib.sha256((body or "").encode()).hexdigest()

    # Required headers
    headers["x-amz-date"] = amz_date
    headers["x-amz-content-sha256"] = payload_hash
    if session_token:
        headers["x-amz-security-token"] = session_token
    if not any(k.lower() == "host" for k in headers):
        headers["Host"] = host

    # Canonical query string
    qs_items = sorted(parse_qs(parsed.query, keep_blank_values=True).items())
    canonical_qs = "&".join(f"{quote(k, safe='')}={quote(vs[0], safe='')}" for k, vs in qs_items)

    # Signed headers
    signed = sorted((k.lower(), v.strip()) for k, v in headers.items())
    canonical_hdrs = "".join(f"{k}:{val}\n" for k, val in signed)
    signed_names = ";".join(k for k, _ in signed)

    canonical_request = (
        f"{method}\n{uri}\n{canonical_qs}\n{canonical_hdrs}\n{signed_names}\n{payload_hash}"
    )

    # String to sign
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    # Signing key chain
    k_date = _hmac_sha256(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    k_signing = _hmac_sha256(k_service, "aws4_request")
    signature = hmac.new(
        k_signing,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()

    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_names}, Signature={signature}"
    )
    return url, headers


# ---------------------------------------------------------------------------
# JWT Bearer
# ---------------------------------------------------------------------------

_JWT_HMAC = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}


def _build_jwt(
    payload_json: str,
    key: str,
    algorithm: str,
    headers_json: str,
    is_key_b64: bool,
) -> str | None:
    """Build a JWT token.

    HMAC algorithms (HS256 / HS384 / HS512) use stdlib only.
    RSA / EC / PS algorithms attempt ``PyJWT``; returns ``None``
    when the library is not installed.
    """
    hash_fn = _JWT_HMAC.get(algorithm)

    if hash_fn is None:
        # RSA / EC / PS — try PyJWT
        try:
            import jwt as pyjwt  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "%s requires PyJWT; install with: pip install PyJWT cryptography",
                algorithm,
            )
            return None
        try:
            payload = json.loads(payload_json) if payload_json.strip() else {}
            extra = json.loads(headers_json) if headers_json.strip() else {}
            result: str = pyjwt.encode(payload, key, algorithm=algorithm, headers=extra)
            return result
        except Exception:
            logger.exception("JWT signing failed (%s)", algorithm)
            return None

    # HMAC path — stdlib
    try:
        payload = json.loads(payload_json) if payload_json.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    try:
        extra = json.loads(headers_json) if headers_json.strip() else {}
    except json.JSONDecodeError:
        extra = {}

    header = {"alg": algorithm, "typ": "JWT", **extra}
    hdr_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    pay_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{hdr_b64}.{pay_b64}"
    key_bytes = base64.b64decode(key) if is_key_b64 else key.encode()
    sig = hmac.new(key_bytes, signing_input.encode(), hash_fn).digest()
    return f"{signing_input}.{_b64url(sig)}"


def _apply_jwt(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """JWT Bearer — ``Authorization: <prefix> <jwt>``."""
    v = _entries_map(auth, "jwt")
    algorithm = v.get("algorithm", "HS256")
    secret = v.get("secret", "")
    private_key = v.get("privateKey", "")
    payload_json = v.get("payload", "{}")
    headers_json = v.get("headers", "{}")
    is_b64 = v.get("isSecretBase64Encoded", "false") == "true"
    add_to = v.get("addTokenTo", "header")
    prefix = v.get("headerPrefix", "Bearer")
    query_key = v.get("queryParamKey", "token")

    key = private_key if algorithm.startswith(("RS", "ES", "PS")) else secret
    token = _build_jwt(payload_json, key, algorithm, headers_json, is_b64)
    if not token:
        return url, headers
    if add_to == "header":
        headers["Authorization"] = f"{prefix} {token}" if prefix else token
    else:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{_percent_encode(query_key)}={_percent_encode(token)}"
    return url, headers


# ---------------------------------------------------------------------------
# ASAP (Atlassian)
# ---------------------------------------------------------------------------


def _apply_asap(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """ASAP — ``Authorization: Bearer <jwt>`` with Atlassian claims."""
    v = _entries_map(auth, "asap")
    issuer = v.get("issuer", "")
    subject = v.get("subject", "")
    audience = v.get("audience", "")
    private_key = v.get("privateKey", "")
    kid = v.get("kid", "")
    algorithm = v.get("algorithm", "RS256")
    expires_in = int(v.get("expiresIn", "3600") or "3600")
    claims_json = v.get("claims", "{}")

    now_ts = int(time.time())
    try:
        extra_claims = json.loads(claims_json) if claims_json.strip() else {}
    except json.JSONDecodeError:
        extra_claims = {}

    payload: dict[str, object] = {
        "iss": issuer,
        "iat": now_ts,
        "exp": now_ts + expires_in,
        "jti": secrets.token_hex(16),
        **extra_claims,
    }
    if subject:
        payload["sub"] = subject
    if audience:
        payload["aud"] = audience

    extra_hdrs = json.dumps({"kid": kid}) if kid else "{}"
    token = _build_jwt(
        json.dumps(payload),
        private_key,
        algorithm,
        extra_hdrs,
        False,
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return url, headers


# ---------------------------------------------------------------------------
# NTLM Authentication
# ---------------------------------------------------------------------------


def _apply_ntlm(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """NTLM — stored for display; live negotiation is not pre-computable."""
    return url, headers


# ---------------------------------------------------------------------------
# Akamai EdgeGrid
# ---------------------------------------------------------------------------


def _apply_edgegrid(
    auth: dict,
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Akamai EdgeGrid — ``Authorization: EG1-HMAC-SHA256 ...``."""
    v = _entries_map(auth, "edgegrid")
    access_token = v.get("accessToken", "")
    client_token = v.get("clientToken", "")
    client_secret = v.get("clientSecret", "")
    nonce = v.get("nonce", "") or secrets.token_urlsafe(16)
    timestamp = v.get("timestamp", "")
    headers_to_sign = v.get("headersToSign", "")
    max_body = int(v.get("maxBody", "131072") or "131072")

    if not timestamp:
        timestamp = dt.datetime.now(dt.UTC).strftime(
            "%Y%m%dT%H:%M:%S+0000",
        )

    parsed = urlparse(url)
    path_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    # Content hash (POST / PUT only)
    content_hash = ""
    if body and method.upper() in ("POST", "PUT"):
        trimmed = body[:max_body].encode()
        content_hash = base64.b64encode(
            hashlib.sha256(trimmed).digest(),
        ).decode()

    # Canonical signed headers
    names = [h.strip().lower() for h in headers_to_sign.split(",") if h.strip()]
    canon_hdrs = ""
    for name in sorted(names):
        val = headers.get(name, "")
        canon_hdrs += f"{name}:{' '.join(val.split())}\t"

    # Auth stub (unsigned)
    auth_stub = (
        f"EG1-HMAC-SHA256 client_token={client_token};"
        f"access_token={access_token};"
        f"timestamp={timestamp};nonce={nonce};"
    )

    # Signing key
    try:
        secret_bytes = base64.b64decode(client_secret)
    except Exception:
        secret_bytes = client_secret.encode()
    signing_key = hmac.new(
        secret_bytes,
        timestamp.encode(),
        hashlib.sha256,
    ).digest()

    data_to_sign = "\t".join(
        [
            method.upper(),
            parsed.scheme,
            parsed.hostname or "",
            path_query,
            canon_hdrs,
            content_hash,
            auth_stub,
        ]
    )
    signature = base64.b64encode(
        hmac.new(signing_key, data_to_sign.encode(), hashlib.sha256).digest(),
    ).decode()

    headers["Authorization"] = f"{auth_stub}signature={signature}"
    return url, headers


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, _Handler] = {
    "bearer": _apply_bearer,
    "basic": _apply_basic,
    "apikey": _apply_apikey,
    "oauth2": _apply_oauth2,
    "digest": _apply_digest,
    "oauth1": _apply_oauth1,
    "hawk": _apply_hawk,
    "awsv4": _apply_awsv4,
    "jwt": _apply_jwt,
    "asap": _apply_asap,
    "ntlm": _apply_ntlm,
    "edgegrid": _apply_edgegrid,
}
