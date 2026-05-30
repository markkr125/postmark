"""Unit tests for :mod:`services.lsp.pm_require_types`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.lsp.pm_require_types import (
    _OPEN_BUFFER_SPECS,
    detect_npm_jsr_specs,
    pm_require_index_path,
    prune_orphan_specs,
    reset_workspace,
    sync_pm_require_types,
    unregister_pm_require_buffer,
)
from services.scripting.js_runtime import PmRequireSpec


def _immediate_thread(target=None, args=(), kwargs=None, daemon=True) -> MagicMock:
    """Run ``threading.Thread`` targets inline so cache mocks are asserted reliably."""
    if target is not None:
        target(*(args or ()))
    return MagicMock()


class TestDetectNpmJsrSpecs:
    """``detect_npm_jsr_specs`` filters npm/jsr and skips invalid literals."""

    def test_empty_script(self) -> None:
        assert detect_npm_jsr_specs("") == []

    def test_npm_spec(self) -> None:
        specs = detect_npm_jsr_specs("const x = pm.require('npm:lodash@4.17.21');")
        assert specs == [PmRequireSpec("npm", "lodash", "4.17.21")]

    def test_jsr_spec(self) -> None:
        specs = detect_npm_jsr_specs("pm.require('jsr:@std/assert@1.0.0');")
        assert specs == [PmRequireSpec("jsr", "@std/assert", "1.0.0")]

    def test_invalid_specifier_is_skipped(self) -> None:
        assert detect_npm_jsr_specs("pm.require('npm:_bad@1.0.0');") == []


class TestPmRequireIndexGeneration:
    """``sync_pm_require_types`` writes ``pm_require_index.ts``."""

    def test_writes_overloads_for_detected_specs(self, tmp_path: Path) -> None:
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        script = "const _ = pm.require('npm:lodash@4.17.21');"
        with (
            patch(
                "services.lsp.pm_require_types.threading.Thread",
                side_effect=_immediate_thread,
            ),
            patch("services.lsp.pm_require_types._deno_cache_specifiers") as cache_mock,
        ):
            changed = sync_pm_require_types(script, tmp_path)
        assert changed is True
        cache_mock.assert_called_once()
        text = pm_require_index_path(tmp_path).read_text(encoding="utf-8")
        assert "npm:lodash@4.17.21" in text or "@types/lodash" in text
        assert 'function require(spec: "npm:lodash@4.17.21")' in text
        assert 'function require(spec: "npm:lodash")' in text
        assert "@types/lodash" in text
        assert "declare global {" in text
        assert "export {};" in text

    def test_no_change_when_content_matches(self, tmp_path: Path) -> None:
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        script = "pm.require('npm:lodash@4.17.21');"
        with (
            patch(
                "services.lsp.pm_require_types.threading.Thread",
                side_effect=_immediate_thread,
            ),
            patch("services.lsp.pm_require_types._deno_cache_specifiers"),
        ):
            assert sync_pm_require_types(script, tmp_path) is True
            assert sync_pm_require_types(script, tmp_path) is False

    def test_other_buffer_does_not_wipe_overloads(self, tmp_path: Path) -> None:
        """A specless buffer must not overwrite overloads needed by another open buffer."""
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        try:
            with (
                patch(
                    "services.lsp.pm_require_types.threading.Thread",
                    side_effect=_immediate_thread,
                ),
                patch("services.lsp.pm_require_types._deno_cache_specifiers"),
            ):
                sync_pm_require_types(
                    "const _ = pm.require('npm:lodash@4.17.21');",
                    tmp_path,
                    buffer_uri="file:///A.js",
                )
                # Different buffer with no pm.require — must not wipe out A's overload.
                sync_pm_require_types(
                    "console.log('hi')",
                    tmp_path,
                    buffer_uri="file:///B.js",
                )
            text = pm_require_index_path(tmp_path).read_text(encoding="utf-8")
            assert 'function require(spec: "npm:lodash@4.17.21")' in text
        finally:
            unregister_pm_require_buffer(tmp_path, "file:///A.js")
            unregister_pm_require_buffer(tmp_path, "file:///B.js")

    def test_unregister_removes_overload(self, tmp_path: Path) -> None:
        """Closing the buffer that owned a spec drops its overload from the index."""
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        try:
            with (
                patch(
                    "services.lsp.pm_require_types.threading.Thread",
                    side_effect=_immediate_thread,
                ),
                patch("services.lsp.pm_require_types._deno_cache_specifiers"),
            ):
                sync_pm_require_types(
                    "pm.require('npm:lodash@4.17.21');",
                    tmp_path,
                    buffer_uri="file:///A.js",
                )
                unregister_pm_require_buffer(tmp_path, "file:///A.js")
                sync_pm_require_types("", tmp_path, buffer_uri="file:///B.js")
            text = pm_require_index_path(tmp_path).read_text(encoding="utf-8")
            assert "npm:lodash" not in text
        finally:
            unregister_pm_require_buffer(tmp_path, "file:///A.js")
            unregister_pm_require_buffer(tmp_path, "file:///B.js")


class TestPmRequireWorkspacePrune:
    """``prune_orphan_specs`` and ``reset_workspace``."""

    def test_prune_orphan_specs_drops_stale_buffers(self, tmp_path: Path) -> None:
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        ws_key = str(tmp_path.resolve())
        live = {(ws_key, "file:///live.js")}
        with (
            patch(
                "services.lsp.pm_require_types.threading.Thread",
                side_effect=_immediate_thread,
            ),
            patch("services.lsp.pm_require_types._deno_cache_specifiers"),
        ):
            sync_pm_require_types(
                "pm.require('npm:lodash@4.17.21');",
                tmp_path,
                buffer_uri="file:///live.js",
            )
            _OPEN_BUFFER_SPECS[(ws_key, "file:///orphan.js")] = [
                PmRequireSpec("npm", "axios", "1.0.0"),
            ]
            removed = prune_orphan_specs(tmp_path, live)
        assert removed == 1
        assert (ws_key, "file:///orphan.js") not in _OPEN_BUFFER_SPECS
        text = pm_require_index_path(tmp_path).read_text(encoding="utf-8")
        assert "axios" not in text
        assert "lodash" in text
        unregister_pm_require_buffer(tmp_path, "file:///live.js")

    def test_reset_workspace_clears_index_and_cache(self, tmp_path: Path) -> None:
        (tmp_path / "deno.json").write_text("{}", encoding="utf-8")
        ws_key = str(tmp_path.resolve())
        with (
            patch(
                "services.lsp.pm_require_types.threading.Thread",
                side_effect=_immediate_thread,
            ),
            patch("services.lsp.pm_require_types._deno_cache_specifiers"),
        ):
            sync_pm_require_types(
                "pm.require('npm:lodash@4.17.21');",
                tmp_path,
                buffer_uri="file:///A.js",
            )
        cache_path = tmp_path / ".pm_require_cached.json"
        assert cache_path.is_file()
        reset_workspace(tmp_path)
        assert not any(k[0] == ws_key for k in _OPEN_BUFFER_SPECS)
        assert not cache_path.is_file()
        assert pm_require_index_path(tmp_path).is_file()
