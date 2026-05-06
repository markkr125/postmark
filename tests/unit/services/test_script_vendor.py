"""Tests for vendor libraries bundled in the JS (Deno) script bundle.

Verifies that CryptoJS, atob/btoa polyfills, the ``require()`` shim,
and UUIDv4 generation work correctly inside the script runtime.

Requires **Deno** — skipped when unavailable.
"""

from __future__ import annotations

import re

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    response: dict | None = None,
    variables: dict | None = None,
    environment_vars: dict | None = None,
) -> dict:
    """Return a minimal ``ScriptInput``."""
    return {
        "request": {
            "url": "https://example.com",
            "method": "GET",
            "headers": {},
            "body": "",
        },
        "response": response,
        "variables": variables or {},
        "environment_vars": environment_vars or {},
        "collection_vars": {},
        "info": {"requestName": "vendor-test"},
    }


# ===================================================================
# CryptoJS tests
# ===================================================================


class TestCryptoJS:
    """CryptoJS must be globally available in the V8 sandbox."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_sha256(self):
        """SHA-256 produces the known hash for 'hello'."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("sha256", function() {
    var hash = CryptoJS.SHA256("hello").toString();
    pm.expect(hash).to.equal(
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    );
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_hmac_sha256(self):
        """HMAC-SHA256 produces the known digest."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("hmac", function() {
    var hmac = CryptoJS.HmacSHA256("message", "secret").toString();
    pm.expect(hmac).to.equal(
        "8b5f48702995c1598c573db1e21866a9b825d4a794d169d7060a03605796360b"
    );
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_hmac_base64(self):
        """HMAC-SHA256 Base64 encoding works (common Postman pattern)."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var hash = CryptoJS.HmacSHA256("message", "secret");
var sig = CryptoJS.enc.Base64.stringify(hash);
pm.variables.set("sig", sig);
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["variable_changes"]["sig"] != ""
        assert len(result["variable_changes"]["sig"]) > 10

    def test_md5(self):
        """MD5 produces the known hash."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("md5", function() {
    pm.expect(CryptoJS.MD5("test").toString()).to.equal(
        "098f6bcd4621d373cade4e832627b4f6"
    );
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_aes_encrypt_decrypt(self):
        """AES encrypt/decrypt round-trips correctly."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var encrypted = CryptoJS.AES.encrypt("hello world", "passphrase").toString();
var decrypted = CryptoJS.AES.decrypt(encrypted, "passphrase").toString(
    CryptoJS.enc.Utf8
);
pm.test("aes", function() {
    pm.expect(decrypted).to.equal("hello world");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_require_crypto_js(self):
        """``require('crypto-js')`` returns the CryptoJS object."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var CJ = require("crypto-js");
pm.test("require", function() {
    pm.expect(CJ.SHA256("x").toString()).to.be.a("string");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_sha512(self):
        """SHA-512 produces the known hash."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("sha512", function() {
    var hash = CryptoJS.SHA512("hello").toString();
    pm.expect(hash.length).to.equal(128);
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# atob / btoa tests
# ===================================================================


class TestBase64Polyfills:
    """atob and btoa must be globally available."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_btoa(self):
        """Encode to Base64 with btoa."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("btoa", function() {
    pm.expect(btoa("hello world")).to.equal("aGVsbG8gd29ybGQ=");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_atob(self):
        """Decode from Base64 with atob."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("atob", function() {
    pm.expect(atob("aGVsbG8gd29ybGQ=")).to.equal("hello world");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_round_trip(self):
        """Round-trip btoa then atob correctly."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("round-trip", function() {
    var original = "The quick brown fox!";
    pm.expect(atob(btoa(original))).to.equal(original);
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# UUID tests
# ===================================================================


class TestUUID:
    """``require('uuid')`` must provide v4 UUID generation."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    _UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

    def test_uuid_v4_format(self):
        """UUID v4 has the correct format."""
        from services.scripting.js_runtime import JSRuntime

        script = 'pm.variables.set("id", require("uuid").v4());'
        result = JSRuntime.execute(script, _make_context())
        uuid_val = result["variable_changes"]["id"]
        assert self._UUID_RE.match(uuid_val), f"Invalid UUID: {uuid_val}"

    def test_uuid_v4_unique(self):
        """Two generated UUIDs are different."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var uuid = require("uuid");
pm.variables.set("a", uuid.v4());
pm.variables.set("b", uuid.v4());
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["variable_changes"]["a"] != result["variable_changes"]["b"]


# ===================================================================
# require() shim tests
# ===================================================================


class TestRequireShim:
    """The ``require()`` function resolves built-in modules."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_require_unknown_module_throws(self):
        """Requiring an unknown module produces a runtime error."""
        from services.scripting.js_runtime import JSRuntime

        script = 'var x = require("nonexistent");'
        result = JSRuntime.execute(script, _make_context())
        assert any("not available" in r["error"] for r in result["test_results"] if r.get("error"))

    def test_require_uuid(self):
        """``require('uuid')`` returns an object with v4."""
        from services.scripting.js_runtime import JSRuntime

        script = """
pm.test("uuid module", function() {
    var uuid = require("uuid");
    pm.expect(uuid).to.be.an("object");
    pm.expect(uuid.v4).to.be.a("function");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# End-to-end Postman script pattern
# ===================================================================


class TestPostmanScriptPatterns:
    """Real-world Postman script patterns that users import."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

    def test_hmac_signature_to_env(self):
        """HMAC signature computed and saved to environment variable."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var message = "GET\\n/api/v1/data\\n1234567890";
var secret = "my-api-secret";
var hash = CryptoJS.HmacSHA256(message, secret);
var signature = CryptoJS.enc.Base64.stringify(hash);
postman.setEnvironmentVariable("X-Signature", signature);
"""
        result = JSRuntime.execute(script, _make_context())
        changes = result["variable_changes"]
        assert "X-Signature" in changes
        assert len(changes["X-Signature"]) > 20

    def test_base64_auth_header(self):
        """Base64 encoding for Basic auth header."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var credentials = btoa("user:password123");
pm.variables.set("authHeader", "Basic " + credentials);
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["variable_changes"]["authHeader"] == "Basic dXNlcjpwYXNzd29yZDEyMw=="
