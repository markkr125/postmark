"""Tests for binary body path policy and HttpService binary send."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from services.ai.chat.execution.binary.path_policy import (
    is_binary_path_allowed,
    validate_binary_path,
)
from services.http.binary_body import resolve_binary_body_bytes
from services.http.http_service import HttpService


class TestBinaryPathPolicy:
    """Agent binary path allowlist."""

    def test_allows_temp_file(self, tmp_path: Path) -> None:
        """Files under the system temp dir are allowed."""
        target = tmp_path / "payload.bin"
        target.write_bytes(b"abc")
        path, err = validate_binary_path(str(target))
        assert err is None
        assert path is not None
        assert is_binary_path_allowed(str(target))

    def test_rejects_ssh(self, tmp_path: Path) -> None:
        """Paths under ``.ssh`` are rejected."""
        ssh = Path.home() / ".ssh" / "id_rsa"
        _path, err = validate_binary_path(str(ssh))
        assert err in {"binary_path_sensitive", "binary_path_forbidden", "binary_path_not_allowed"}

    def test_rejects_traversal(self) -> None:
        """``..`` segments are rejected before resolve."""
        _path, err = validate_binary_path("/tmp/foo/../etc/passwd")
        assert err == "binary_path_traversal"


class TestResolveBinaryBody:
    """Filesystem byte resolution."""

    def test_reads_bytes(self, tmp_path: Path) -> None:
        """Existing file bytes are returned."""
        target = tmp_path / "blob.bin"
        target.write_bytes(b"\x00\x01\xff")
        content, err = resolve_binary_body_bytes(str(target))
        assert err is None
        assert content == b"\x00\x01\xff"

    def test_missing_file(self, tmp_path: Path) -> None:
        """Missing path returns an error."""
        content, err = resolve_binary_body_bytes(str(tmp_path / "missing.bin"))
        assert content is None
        assert err is not None
        assert "not found" in err.casefold()


class TestHttpServiceBinarySend:
    """HttpService sends file bytes when body_mode is binary."""

    def test_sends_file_bytes_not_path_string(self, tmp_path: Path) -> None:
        """Wire content must be file bytes, not the path UTF-8 string."""
        from tests.unit.services.http.test_http_service import _mock_client, _mock_response

        target = tmp_path / "upload.bin"
        payload = b"BINDATA\x00\x01"
        target.write_bytes(payload)

        with (
            patch(
                "services.http.http_service.HttpService._resolve_dns",
                return_value=(0.0, "127.0.0.1"),
            ),
            patch("services.http.http_service.httpx.Client") as client_cls,
        ):
            client_cls.return_value = _mock_client(_mock_response())
            result = HttpService.send_request(
                method="POST",
                url="http://example.com/upload",
                body=str(target),
                body_mode="binary",
            )
            assert "error" not in result
            call_kwargs = client_cls.return_value.request.call_args
            assert call_kwargs.kwargs["content"] == payload
            assert call_kwargs.kwargs["content"] != str(target).encode("utf-8")
