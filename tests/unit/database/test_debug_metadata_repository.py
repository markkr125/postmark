"""Repository merge tests for script debug metadata."""

from __future__ import annotations

from database.database import get_session
from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
    merge_request_scripts_debug,
)
from database.models.local_scripts.local_script_repository import (
    create_folder,
    create_script,
    update_local_script_debug_metadata,
)


def test_merge_request_scripts_debug_preserves_script_text() -> None:
    """Debug merge must not remove ``pre_request`` script body."""
    coll = create_new_collection("C")
    req = create_new_request(
        coll.id,
        "GET",
        "https://example.com",
        "R",
        scripts={"pre_request": "console.log(1)", "test": ""},
    )
    merge_request_scripts_debug(
        req.id,
        {"pre_request": {"breakpoints": [{"line": 2, "condition": None}], "watches": []}},
    )
    with get_session() as session:
        from database.models.collections.model.request_model import RequestModel

        row = session.get(RequestModel, req.id)
        assert row is not None
        scripts = row.scripts
        assert isinstance(scripts, dict)
        assert scripts.get("pre_request") == "console.log(1)"
        assert scripts["debug"]["pre_request"]["breakpoints"][0]["line"] == 2


def test_update_local_script_debug_metadata() -> None:
    """Flat metadata is stored on the local script row."""
    folder = create_folder("lib")
    script = create_script(folder.id, "util", content="export {}")
    update_local_script_debug_metadata(
        script.id,
        {"breakpoints": [{"line": 0, "condition": None}], "watches": ["1+1"]},
    )
    with get_session() as session:
        from database.models.local_scripts.model.local_script_model import LocalScriptModel

        row = session.get(LocalScriptModel, script.id)
        assert row is not None
        assert row.content == "export {}"
        assert row.debug_metadata is not None
        assert row.debug_metadata.get("watches") == ["1+1"]
