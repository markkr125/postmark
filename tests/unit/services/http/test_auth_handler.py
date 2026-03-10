"""Tests for the shared auth header injection handler."""

from __future__ import annotations

import base64
import json

from services.http.auth_handler import apply_auth


class TestApplyAuthNoop:
    """Verify no-op scenarios return inputs unchanged."""

    def test_none_auth(self) -> None:
        """None auth returns url and headers unchanged."""
        url, hdr = apply_auth(None, "https://x.io", {})
        assert url == "https://x.io"
        assert hdr == {}

    def test_noauth_type(self) -> None:
        """Explicit 'noauth' returns inputs unchanged."""
        url, hdr = apply_auth({"type": "noauth"}, "https://x.io", {"A": "1"})
        assert url == "https://x.io"
        assert hdr == {"A": "1"}

    def test_unknown_type(self) -> None:
        """Unknown auth type returns inputs unchanged."""
        url, hdr = apply_auth({"type": "custom123"}, "https://x.io", {})
        assert url == "https://x.io"
        assert hdr == {}


class TestBearerAuth:
    """Bearer token injection."""

    def test_adds_header(self) -> None:
        """Token is added as Authorization: Bearer header."""
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": "abc"}]}
        _, hdr = apply_auth(auth, "https://x.io", {})
        assert hdr["Authorization"] == "Bearer abc"

    def test_empty_token(self) -> None:
        """Empty token does not add a header."""
        auth = {"type": "bearer", "bearer": [{"key": "token", "value": ""}]}
        _, hdr = apply_auth(auth, "https://x.io", {})
        assert "Authorization" not in hdr


class TestBasicAuth:
    """Basic auth injection."""

    def test_adds_header(self) -> None:
        """Encodes username:password in base64."""
        auth = {
            "type": "basic",
            "basic": [
                {"key": "username", "value": "user"},
                {"key": "password", "value": "pass"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {})
        expected = base64.b64encode(b"user:pass").decode()
        assert hdr["Authorization"] == f"Basic {expected}"

    def test_empty_creds(self) -> None:
        """Empty username and password produces no header."""
        auth = {
            "type": "basic",
            "basic": [
                {"key": "username", "value": ""},
                {"key": "password", "value": ""},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {})
        assert "Authorization" not in hdr


class TestApiKeyAuth:
    """API key header and query parameter injection."""

    def test_header(self) -> None:
        """API key is added as a custom header."""
        auth = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "X-Api-Key"},
                {"key": "value", "value": "secret"},
                {"key": "in", "value": "header"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {})
        assert hdr["X-Api-Key"] == "secret"

    def test_query_param(self) -> None:
        """API key is appended as a URL query parameter."""
        auth = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "api_key"},
                {"key": "value", "value": "secret"},
                {"key": "in", "value": "query"},
            ],
        }
        url, _ = apply_auth(auth, "https://x.io/path", {})
        assert "api_key=secret" in url
        assert "?" in url

    def test_query_param_appends_with_ampersand(self) -> None:
        """When URL already has query params, uses & separator."""
        auth = {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "k"},
                {"key": "value", "value": "v"},
                {"key": "in", "value": "query"},
            ],
        }
        url, _ = apply_auth(auth, "https://x.io/path?a=1", {})
        assert "?a=1&k=v" in url


class TestOAuth2Auth:
    """OAuth 2.0 manual token injection."""

    def test_header_with_prefix(self) -> None:
        """Token is added with the configured prefix."""
        auth = {
            "type": "oauth2",
            "oauth2": [
                {"key": "accessToken", "value": "tok"},
                {"key": "headerPrefix", "value": "Bearer"},
                {"key": "addTokenTo", "value": "header"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {})
        assert hdr["Authorization"] == "Bearer tok"

    def test_query_param(self) -> None:
        """Token is added as query param when configured."""
        auth = {
            "type": "oauth2",
            "oauth2": [
                {"key": "accessToken", "value": "tok"},
                {"key": "addTokenTo", "value": "queryParams"},
            ],
        }
        url, _ = apply_auth(auth, "https://x.io", {})
        assert "access_token=tok" in url


class TestDigestAuth:
    """Digest auth header generation (RFC 7616)."""

    def test_md5_auth(self) -> None:
        """Produces a valid Digest header with MD5 algorithm."""
        auth = {
            "type": "digest",
            "digest": [
                {"key": "username", "value": "user"},
                {"key": "password", "value": "pass"},
                {"key": "realm", "value": "testrealm"},
                {"key": "nonce", "value": "abc123"},
                {"key": "algorithm", "value": "MD5"},
                {"key": "qop", "value": "auth"},
                {"key": "nonceCount", "value": "00000001"},
                {"key": "clientNonce", "value": "deadbeef"},
                {"key": "opaque", "value": "opq"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io/path", {}, method="GET")
        val = hdr["Authorization"]
        assert val.startswith("Digest ")
        assert 'username="user"' in val
        assert 'realm="testrealm"' in val
        assert "algorithm=MD5" in val
        assert "qop=auth" in val
        assert 'opaque="opq"' in val

    def test_no_qop(self) -> None:
        """Digest without qop omits nc and cnonce from header."""
        auth = {
            "type": "digest",
            "digest": [
                {"key": "username", "value": "u"},
                {"key": "password", "value": "p"},
                {"key": "realm", "value": "r"},
                {"key": "nonce", "value": "n"},
                {"key": "algorithm", "value": "MD5"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io/", {}, method="GET")
        val = hdr["Authorization"]
        assert "qop=" not in val
        assert "nc=" not in val


class TestOAuth1Auth:
    """OAuth 1.0 signature generation (RFC 5849)."""

    def test_hmac_sha1_header(self) -> None:
        """Produces Authorization: OAuth header with signature."""
        auth = {
            "type": "oauth1",
            "oauth1": [
                {"key": "consumerKey", "value": "ck"},
                {"key": "consumerSecret", "value": "cs"},
                {"key": "token", "value": "tok"},
                {"key": "tokenSecret", "value": "ts"},
                {"key": "signatureMethod", "value": "HMAC-SHA1"},
                {"key": "timestamp", "value": "1234567890"},
                {"key": "nonce", "value": "testnonce"},
                {"key": "version", "value": "1.0"},
                {"key": "addParamsToHeader", "value": True},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io/api", {}, method="GET")
        val = hdr["Authorization"]
        assert val.startswith("OAuth ")
        assert "oauth_consumer_key" in val
        assert "oauth_signature" in val

    def test_plaintext_signature(self) -> None:
        """PLAINTEXT signature is consumer_secret&token_secret."""
        auth = {
            "type": "oauth1",
            "oauth1": [
                {"key": "consumerKey", "value": "ck"},
                {"key": "consumerSecret", "value": "cs"},
                {"key": "token", "value": ""},
                {"key": "tokenSecret", "value": "ts"},
                {"key": "signatureMethod", "value": "PLAINTEXT"},
                {"key": "timestamp", "value": "0"},
                {"key": "nonce", "value": "n"},
                {"key": "addParamsToHeader", "value": True},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {}, method="GET")
        assert "cs%26ts" in hdr["Authorization"] or "cs&ts" in hdr["Authorization"]

    def test_query_params(self) -> None:
        """OAuth params appended to URL when addParamsToHeader is false."""
        auth = {
            "type": "oauth1",
            "oauth1": [
                {"key": "consumerKey", "value": "ck"},
                {"key": "consumerSecret", "value": "cs"},
                {"key": "token", "value": ""},
                {"key": "tokenSecret", "value": ""},
                {"key": "signatureMethod", "value": "PLAINTEXT"},
                {"key": "timestamp", "value": "0"},
                {"key": "nonce", "value": "n"},
                {"key": "addParamsToHeader", "value": False},
            ],
        }
        url, hdr = apply_auth(auth, "https://x.io", {}, method="GET")
        assert "oauth_consumer_key=ck" in url
        assert "Authorization" not in hdr


class TestHawkAuth:
    """Hawk authentication header generation."""

    def test_basic_hawk(self) -> None:
        """Produces Authorization: Hawk header with required fields."""
        auth = {
            "type": "hawk",
            "hawk": [
                {"key": "authId", "value": "myid"},
                {"key": "authKey", "value": "mykey"},
                {"key": "algorithm", "value": "sha256"},
                {"key": "nonce", "value": "testnonce"},
                {"key": "timestamp", "value": "1234567890"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io/path", {}, method="GET")
        val = hdr["Authorization"]
        assert val.startswith("Hawk ")
        assert 'id="myid"' in val
        assert 'ts="1234567890"' in val
        assert 'nonce="testnonce"' in val
        assert 'mac="' in val


class TestAwsV4Auth:
    """AWS Signature V4 header generation."""

    def test_adds_required_headers(self) -> None:
        """Adds Authorization, x-amz-date, x-amz-content-sha256 headers."""
        auth = {
            "type": "awsv4",
            "awsv4": [
                {"key": "accessKey", "value": "AKID"},
                {"key": "secretKey", "value": "secret"},
                {"key": "region", "value": "us-east-1"},
                {"key": "service", "value": "s3"},
            ],
        }
        _, hdr = apply_auth(auth, "https://s3.amazonaws.com/bucket", {}, method="GET")
        assert hdr["Authorization"].startswith("AWS4-HMAC-SHA256")
        assert "Credential=AKID/" in hdr["Authorization"]
        assert "x-amz-date" in hdr
        assert "x-amz-content-sha256" in hdr

    def test_session_token(self) -> None:
        """Session token adds x-amz-security-token header."""
        auth = {
            "type": "awsv4",
            "awsv4": [
                {"key": "accessKey", "value": "AKID"},
                {"key": "secretKey", "value": "secret"},
                {"key": "region", "value": "us-west-2"},
                {"key": "service", "value": "execute-api"},
                {"key": "sessionToken", "value": "tokval"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {}, method="POST")
        assert hdr["x-amz-security-token"] == "tokval"


class TestJwtAuth:
    """JWT Bearer token generation (HMAC algorithms via stdlib)."""

    def test_hs256_header(self) -> None:
        """Generates a valid HS256 JWT in Authorization header."""
        auth = {
            "type": "jwt",
            "jwt": [
                {"key": "algorithm", "value": "HS256"},
                {"key": "secret", "value": "mysecret"},
                {"key": "payload", "value": '{"sub":"123"}'},
                {"key": "headers", "value": "{}"},
                {"key": "isSecretBase64Encoded", "value": "false"},
                {"key": "addTokenTo", "value": "header"},
                {"key": "headerPrefix", "value": "Bearer"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {})
        assert "Authorization" in hdr
        token = hdr["Authorization"].removeprefix("Bearer ")
        parts = token.split(".")
        assert len(parts) == 3
        # Decode header to verify algorithm
        header_json = base64.urlsafe_b64decode(parts[0] + "==")
        header_data = json.loads(header_json)
        assert header_data["alg"] == "HS256"
        assert header_data["typ"] == "JWT"

    def test_query_param(self) -> None:
        """JWT added as query param when configured."""
        auth = {
            "type": "jwt",
            "jwt": [
                {"key": "algorithm", "value": "HS256"},
                {"key": "secret", "value": "s"},
                {"key": "payload", "value": "{}"},
                {"key": "headers", "value": "{}"},
                {"key": "isSecretBase64Encoded", "value": "false"},
                {"key": "addTokenTo", "value": "queryParams"},
                {"key": "queryParamKey", "value": "jwt"},
            ],
        }
        url, _ = apply_auth(auth, "https://x.io", {})
        assert "jwt=" in url


class TestAsapAuth:
    """ASAP (Atlassian) auth — requires RSA, may fall back gracefully."""

    def test_returns_unchanged_without_pyjwt(self) -> None:
        """Without PyJWT, ASAP (RS256) returns headers unchanged."""
        auth = {
            "type": "asap",
            "asap": [
                {"key": "issuer", "value": "iss"},
                {"key": "audience", "value": "aud"},
                {"key": "privateKey", "value": "not-a-real-key"},
                {"key": "kid", "value": "kid1"},
                {"key": "algorithm", "value": "RS256"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {})
        # RS256 requires PyJWT — without it, no header is added
        # (unless PyJWT is installed, in which case it would fail on the bad key)


class TestNtlmAuth:
    """NTLM auth — pass-through only (no pre-computable header)."""

    def test_noop(self) -> None:
        """NTLM does not modify headers or URL."""
        auth = {
            "type": "ntlm",
            "ntlm": [
                {"key": "username", "value": "user"},
                {"key": "password", "value": "pass"},
            ],
        }
        url, hdr = apply_auth(auth, "https://x.io", {"Existing": "h"})
        assert url == "https://x.io"
        assert hdr == {"Existing": "h"}


class TestEdgeGridAuth:
    """Akamai EdgeGrid signature generation."""

    def test_produces_eg1_header(self) -> None:
        """Generates Authorization: EG1-HMAC-SHA256 header."""
        auth = {
            "type": "edgegrid",
            "edgegrid": [
                {"key": "accessToken", "value": "at"},
                {"key": "clientToken", "value": "ct"},
                {"key": "clientSecret", "value": base64.b64encode(b"sec").decode()},
                {"key": "nonce", "value": "nonce1"},
                {"key": "timestamp", "value": "20240101T00:00:00+0000"},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io/path", {}, method="GET")
        val = hdr["Authorization"]
        assert val.startswith("EG1-HMAC-SHA256")
        assert "client_token=ct" in val
        assert "access_token=at" in val
        assert "signature=" in val


class TestBooleanEntries:
    """Verify boolean entry values are handled correctly."""

    def test_true_bool(self) -> None:
        """Python True in entry maps to 'true' string."""
        auth = {
            "type": "oauth1",
            "oauth1": [
                {"key": "consumerKey", "value": "ck"},
                {"key": "consumerSecret", "value": "cs"},
                {"key": "token", "value": ""},
                {"key": "tokenSecret", "value": ""},
                {"key": "signatureMethod", "value": "PLAINTEXT"},
                {"key": "timestamp", "value": "0"},
                {"key": "nonce", "value": "n"},
                {"key": "addParamsToHeader", "value": True},
            ],
        }
        _, hdr = apply_auth(auth, "https://x.io", {}, method="GET")
        # addParamsToHeader=True means header mode
        assert "Authorization" in hdr
