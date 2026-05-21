"""Tests for script version history keyed by local_script_id."""

from __future__ import annotations

from database.models.local_scripts.local_script_repository import create_folder, create_script
from services.script_version_service import ScriptVersionService


def test_capture_and_list_local_script_versions() -> None:
    """Versions for a local script use ``local_script_id`` and ``local_script`` type."""
    folder = create_folder("Versions")
    script = create_script(folder.id, "vtest", language="javascript", content="v1")

    captured = ScriptVersionService.capture(
        local_script_id=script.id,
        script_type="local_script",
        content="v1",
        language="javascript",
    )
    assert captured is not None

    ScriptVersionService.capture(
        local_script_id=script.id,
        script_type="local_script",
        content="v2",
        language="javascript",
    )

    versions = ScriptVersionService.list_versions(
        local_script_id=script.id,
        script_type="local_script",
    )
    assert len(versions) == 2
    assert versions[0]["content"] == "v2"
