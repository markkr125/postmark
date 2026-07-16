"""Tests for debug_metadata mutate via merge APIs."""

from __future__ import annotations

from services.ai.chat.tools.workspace_mutate.debug_ops import (
    apply_debug_metadata_mutation,
    filter_debug_metadata_fields,
)
from services.collection_service import CollectionService
from services.local_script_service import LocalScriptService


class TestDebugMetadataMutate:
    """Breakpoints/watches without wiping script bodies."""

    def test_request_breakpoints_preserve_script_text(self) -> None:
        """Merging debug metadata must not clear request script bodies."""
        col = CollectionService.create_collection("Dbg Col")
        req = CollectionService.create_request(
            int(col.id),
            "GET",
            "https://example.com",
            "Dbg Req",
            scripts={"test": "pm.test('x', () => {});", "test_language": "javascript"},
        )
        fields, err = filter_debug_metadata_fields(
            "update",
            {
                "target_kind": "request",
                "target_id": int(req.id),
                "per_type": {
                    "test": {
                        "breakpoints": [{"line": 0, "condition": None}],
                        "watches": ["pm.response"],
                    }
                },
            },
        )
        assert err is None
        assert fields is not None
        obs = apply_debug_metadata_mutation(verb="update", fields=fields, open_after=False)
        text = obs.to_text() if hasattr(obs, "to_text") else str(obs)
        assert "ok: true" in text
        reloaded = CollectionService.get_request(int(req.id))
        assert reloaded is not None
        scripts = reloaded.scripts or {}
        assert scripts.get("test") == "pm.test('x', () => {});"
        debug = scripts.get("debug") or {}
        assert debug.get("test", {}).get("breakpoints")

    def test_local_script_watches(self) -> None:
        """Local script flat debug metadata updates watches."""
        folder = LocalScriptService.create_folder("DbgFolder")
        created = LocalScriptService.create_script(
            int(folder.id),
            "helper.js",
            language="javascript",
        )
        script_id = int(created.id)
        fields, err = filter_debug_metadata_fields(
            "update",
            {
                "target_kind": "local_script",
                "target_id": script_id,
                "breakpoints": [{"line": 2}],
                "watches": ["x"],
            },
        )
        assert err is None
        assert fields is not None
        obs = apply_debug_metadata_mutation(verb="update", fields=fields, open_after=False)
        text = obs.to_text() if hasattr(obs, "to_text") else str(obs)
        assert "ok: true" in text
        load = LocalScriptService.get_script_load_dict(script_id)
        assert load is not None
        meta = load.get("debug_metadata") or {}
        assert meta.get("watches") == ["x"]
