"""Unit tests for private-PyPI plumbing in :mod:`pyodide_runtime`."""

from __future__ import annotations

import pytest

from services.scripting.pyodide_runtime import (
    _pypi_index_hosts,
    _resolve_pypi_index_urls,
)


@pytest.fixture(autouse=True)
def _isolate_default_store():  # type: ignore[no-untyped-def]
    """B7: clear the module-level ``_default_store`` cache around each test."""
    from services.scripting.secret_store import reset_default_store

    reset_default_store()
    yield
    reset_default_store()


class _MemoryStore:
    backend_id = "memory"

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._d = dict(mapping or {})

    def put(self, ref: str, secret: str) -> None:
        self._d[ref] = secret

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)


class TestPypiIndexHosts:
    def test_extracts_host_and_port(self) -> None:
        urls = [
            "https://pypi.mycorp.io/simple/",
            "https://pypi.public.example:8443/simple/",
        ]
        assert _pypi_index_hosts(urls) == [
            "pypi.mycorp.io",
            "pypi.public.example:8443",
        ]

    def test_skips_empty_and_invalid(self) -> None:
        assert _pypi_index_hosts(["", "not a url"]) == []

    def test_dedupes(self) -> None:
        urls = [
            "https://pypi.mycorp.io/simple/",
            "https://pypi.mycorp.io/simple/extra/",
        ]
        assert _pypi_index_hosts(urls) == ["pypi.mycorp.io"]


class TestResolvePypiIndexUrls:
    """``_resolve_pypi_index_urls`` embeds auth into the index URLs."""

    def _stub_indexes(self, monkeypatch: pytest.MonkeyPatch, rows: list[dict]) -> None:
        """Helper: mock ``get_pypi_indexes`` to return *rows* verbatim."""
        monkeypatch.setattr(
            "services.scripting.runtime_settings.RuntimeSettings.get_pypi_indexes",
            staticmethod(lambda: rows),
        )

    def test_empty_config_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_indexes(monkeypatch, [])
        assert _resolve_pypi_index_urls() == []

    def test_primary_only_no_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "row1",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_ref": "",
                    "auth_kind": "none",
                }
            ],
        )
        assert _resolve_pypi_index_urls() == ["https://pypi.mycorp.io/simple/"]

    def test_auth_token_embedded_in_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _MemoryStore({"pypi:row1": "tok123"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "row1",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_ref": "pypi:row1",
                    "auth_kind": "token",
                }
            ],
        )
        assert _resolve_pypi_index_urls() == ["https://tok123@pypi.mycorp.io/simple/"]

    def test_multi_row_preserves_priority_order_and_mixes_auth_kinds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple rows with different auth kinds keep order + per-row auth."""
        import base64 as _b64

        basic_blob = _b64.b64encode(b"user:p@ss").decode()
        store = _MemoryStore(
            {
                "pypi:primary": "primary-tok",
                "pypi:secondary": basic_blob,
            }
        )
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "primary",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_ref": "pypi:primary",
                    "auth_kind": "token",
                },
                {
                    "id": "secondary",
                    "url": "https://pypi.backup.io/simple/",
                    "auth_ref": "pypi:secondary",
                    "auth_kind": "basic",
                },
                {
                    "id": "fallback",
                    "url": "https://pypi.org/simple/",
                    "auth_ref": "",
                    "auth_kind": "none",
                },
            ],
        )
        urls = _resolve_pypi_index_urls()
        assert len(urls) == 3
        assert urls[0] == "https://primary-tok@pypi.mycorp.io/simple/"
        assert "user:p%40ss@pypi.backup.io" in urls[1]
        assert urls[2] == "https://pypi.org/simple/"

    def test_basic_auth_decodes_base64_blob(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Audit-flagged B1: base64 ``user:password`` blob must be decoded."""
        import base64 as _b64

        secret = _b64.b64encode(b"user:p@ss/wd").decode()
        store = _MemoryStore({"pypi:row1": secret})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "row1",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_ref": "pypi:row1",
                    "auth_kind": "basic",
                }
            ],
        )
        urls = _resolve_pypi_index_urls()
        from urllib.parse import unquote, urlparse

        parsed = urlparse(urls[0])
        assert unquote(parsed.username or "") == "user"
        assert unquote(parsed.password or "") == "p@ss/wd"

    def test_basic_auth_invalid_blob_skips_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A corrupt base64 blob should not crash; URL goes through without auth."""
        store = _MemoryStore({"pypi:row1": "not-valid-base64!@#"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "row1",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_ref": "pypi:row1",
                    "auth_kind": "basic",
                }
            ],
        )
        assert _resolve_pypi_index_urls() == ["https://pypi.mycorp.io/simple/"]

    def test_auth_kind_none_skips_secret_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ``auth_kind == 'none'`` the secret store must not be consulted."""

        def _boom() -> None:  # pragma: no cover - asserts store stays untouched
            raise AssertionError("secret store should not be consulted")

        class _BoomStore:
            backend_id = "boom"

            def put(self, r, s):
                _boom()

            def get(self, r):
                _boom()

            def delete(self, r):
                _boom()

        monkeypatch.setattr("services.scripting.secret_store.get_default_store", _BoomStore)
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "row1",
                    "url": "https://pypi.mycorp.io/simple/",
                    "auth_ref": "pypi:row1",
                    "auth_kind": "none",
                }
            ],
        )
        assert _resolve_pypi_index_urls() == ["https://pypi.mycorp.io/simple/"]

    def test_existing_url_credentials_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the user pre-embedded credentials, don't double them up."""
        store = _MemoryStore({"pypi:row1": "ignored-token"})
        monkeypatch.setattr("services.scripting.secret_store.get_default_store", lambda: store)
        self._stub_indexes(
            monkeypatch,
            [
                {
                    "id": "row1",
                    "url": "https://baked:in@pypi.mycorp.io/simple/",
                    "auth_ref": "pypi:row1",
                    "auth_kind": "token",
                }
            ],
        )
        urls = _resolve_pypi_index_urls()
        assert urls == ["https://baked:in@pypi.mycorp.io/simple/"]
