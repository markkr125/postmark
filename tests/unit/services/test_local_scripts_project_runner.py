"""Tests for local script entry runner bundle generation."""

from __future__ import annotations

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.scripting.context import build_pre_request_context
from services.scripting.local_scripts_project.mirror import mirror_path_for_rel, sync_script
from services.scripting.local_scripts_project.runner import build_local_entry_bundle_text


def test_local_entry_bundle_imports_mirrored_file() -> None:
    """Preamble bundle ends with a dynamic import of the mirrored entry URL."""
    root = create_folder("runner_test")
    row = create_script(
        root.id,
        "entry",
        language="javascript",
        content="console.log('hi');",
    )
    sync_script(row.id)
    entry = mirror_path_for_rel("runner_test/entry.js")
    context = build_pre_request_context(
        method="GET",
        url="https://example.com",
        headers={},
        body="",
        variables={},
        environment_vars={},
        collection_vars={},
        info={"requestName": "(test)"},
    )
    text, _needs_net, _mods = build_local_entry_bundle_text(
        "console.log('hi');",
        context,
        language="javascript",
        entry_uri=entry.resolve().as_uri(),
    )
    assert "await import(" in text
    assert entry.resolve().as_uri() in text
    assert "deno_drain" in text or "__denoIpcDrain" in text
