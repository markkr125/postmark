"""Tests for :mod:`services.script_service` — chain resolution."""

from __future__ import annotations

from typing import Any

from services.script_service import (
    ScriptService,
    _build_chains,
    normalize_disabled_inherited,
)
from services.scripting.context import normalize_events

# ===================================================================
# normalize_events (shared helper)
# ===================================================================


class TestNormalizeEvents:
    """Verify the canonical event normalizer handles all formats."""

    def test_none_returns_empty(self) -> None:
        assert normalize_events(None) == {}

    def test_empty_list_returns_empty(self) -> None:
        assert normalize_events([]) == {}

    def test_dict_passthrough(self) -> None:
        events: dict[str, str] = {"pre_request": "code", "test": "code2"}
        assert normalize_events(events) == events

    def test_postman_list_format(self) -> None:
        postman: list[dict[str, Any]] = [
            {
                "listen": "prerequest",
                "script": {"exec": ["console.log('pre');"]},
            },
            {
                "listen": "test",
                "script": {"exec": ["pm.test('ok', function(){});"]},
            },
        ]
        result = normalize_events(postman)
        assert result["pre_request"] == "console.log('pre');"
        assert result["test"] == "pm.test('ok', function(){});"

    def test_unknown_listen_key_skipped(self) -> None:
        events: list[dict[str, Any]] = [{"listen": "unknown", "script": {"exec": ["x"]}}]
        assert normalize_events(events) == {}

    def test_non_dict_entries_skipped(self) -> None:
        assert normalize_events(["bad", 123]) == {}

    def test_invalid_type_returns_empty(self) -> None:
        assert normalize_events("bad") == {}


# ===================================================================
# ScriptService.build_script_chain (DB-backed)
# ===================================================================


class TestBuildScriptChain:
    """Verify script chain resolution from the database."""

    def test_no_request_returns_empty(self) -> None:
        pre, test = ScriptService.build_script_chain(999_999)
        assert pre == []
        assert test == []

    def test_request_with_scripts(self, make_collection_with_request: Any) -> None:
        """Request with scripts only — no collection-level events."""
        coll, req = make_collection_with_request()
        from database.database import get_session
        from database.models.collections.model.request_model import RequestModel

        with get_session() as session:
            r = session.get(RequestModel, req.id)
            assert r is not None
            r.scripts = {
                "pre_request": "pm.variables.set('a', '1');",
                "test": "pm.test('ok', function(){});",
                "language": "javascript",
            }
            session.commit()

        pre, test = ScriptService.build_script_chain(req.id)
        assert len(pre) == 1
        assert pre[0]["code"] == "pm.variables.set('a', '1');"
        assert pre[0]["language"] == "javascript"

        assert len(test) == 1
        assert test[0]["code"] == "pm.test('ok', function(){});"

    def test_collection_and_request_chain(self, make_collection_with_request: Any) -> None:
        """Collection-level events + request-level scripts → correct ordering."""
        coll, req = make_collection_with_request()
        from database.database import get_session
        from database.models.collections.model.collection_model import CollectionModel
        from database.models.collections.model.request_model import RequestModel

        with get_session() as session:
            c = session.get(CollectionModel, coll.id)
            assert c is not None
            c.events = {"pre_request": "// coll pre", "test": "// coll test"}
            r = session.get(RequestModel, req.id)
            assert r is not None
            r.scripts = {"pre_request": "// req pre", "test": "// req test"}
            session.commit()

        pre, test = ScriptService.build_script_chain(req.id)

        # Pre-request: collection first, then request (top-down).
        assert len(pre) == 2
        assert pre[0]["code"] == "// coll pre"
        assert pre[1]["code"] == "// req pre"

        # Test: request first, then collection (bottom-up).
        assert len(test) == 2
        assert test[0]["code"] == "// req test"
        assert test[1]["code"] == "// coll test"

    def test_empty_scripts_are_omitted(self, make_collection_with_request: Any) -> None:
        """Layers with no script content are excluded from the chain."""
        coll, req = make_collection_with_request()
        from database.database import get_session
        from database.models.collections.model.collection_model import CollectionModel
        from database.models.collections.model.request_model import RequestModel

        with get_session() as session:
            c = session.get(CollectionModel, coll.id)
            assert c is not None
            c.events = {"pre_request": "", "test": ""}
            r = session.get(RequestModel, req.id)
            assert r is not None
            r.scripts = {"pre_request": "// only this", "test": ""}
            session.commit()

        pre, test = ScriptService.build_script_chain(req.id)
        assert len(pre) == 1
        assert pre[0]["code"] == "// only this"
        assert len(test) == 0

    def test_default_language_is_javascript(self, make_collection_with_request: Any) -> None:
        """When no language key is set, default to JavaScript."""
        coll, req = make_collection_with_request()
        from database.database import get_session
        from database.models.collections.model.request_model import RequestModel

        with get_session() as session:
            r = session.get(RequestModel, req.id)
            assert r is not None
            r.scripts = {"pre_request": "code"}
            session.commit()

        pre, _test = ScriptService.build_script_chain(req.id)
        assert pre[0]["language"] == "javascript"


# ===================================================================
# disabled_inherited + _build_chains
# ===================================================================


class TestNormalizeDisabledInherited:
    """Tests for :func:`normalize_disabled_inherited`."""

    def test_dedupes_and_drops_invalid(self) -> None:
        raw: list[dict[str, int | str]] = [
            {"collection_id": 1, "script_type": "pre_request"},
            {"collection_id": 1, "script_type": "pre_request"},
            {"collection_id": 1, "script_type": "test"},
            {"collection_id": 2, "script_type": "bad_type"},  # ignored
        ]
        out = normalize_disabled_inherited(raw)
        keys = {(d["collection_id"], d["script_type"]) for d in out}  # type: ignore[union-attr]
        assert keys == {(1, "pre_request"), (1, "test")}


class TestBuildChainsWithDisabled:
    """Script chain building respects ``disabled_inherited`` entries."""

    def test_skips_only_matching_collection_block(self) -> None:
        raw_chain: list[dict[str, Any]] = [
            {
                "source": "collection",
                "id": 7,
                "name": "Folder",
                "scripts": {"pre_request": "//a", "test": "//b"},
            },
            {
                "source": "request",
                "id": 2,
                "name": "Req",
                "scripts": {"pre_request": None, "test": None},
                "disabled_inherited": [{"collection_id": 7, "script_type": "pre_request"}],
            },
        ]
        pre, test = _build_chains(raw_chain)
        assert pre == []
        # request has no pre; test: collection + (empty request) => after reverse, collection test
        assert len(test) == 1
        assert test[0]["code"] == "//b"

    def test_request_layer_never_stripped(self) -> None:
        """Even if the disable list is malicious, the request's own code always runs."""
        raw_chain: list[dict[str, Any]] = [
            {
                "source": "collection",
                "id": 1,
                "name": "C",
                "scripts": {"pre_request": "//c"},
            },
            {
                "source": "request",
                "id": 9,
                "name": "R",
                "scripts": {"pre_request": "//r"},
                "disabled_inherited": [
                    {"collection_id": 9, "script_type": "pre_request"},
                ],
            },
        ]
        pre, _ = _build_chains(raw_chain)
        assert len(pre) == 2
        assert [p["code"] for p in pre] == ["//c", "//r"]

    def test_build_script_chain_db_respects_disable(
        self, make_collection_with_request: Any
    ) -> None:
        """Full chain from DB: disabled collection pre is omitted; tests unchanged."""
        coll, req = make_collection_with_request()
        from database.database import get_session
        from database.models.collections.model.collection_model import CollectionModel
        from database.models.collections.model.request_model import RequestModel

        with get_session() as session:
            c = session.get(CollectionModel, coll.id)
            assert c is not None
            c.events = {"pre_request": "// coll", "test": "// coll t"}
            r = session.get(RequestModel, req.id)
            assert r is not None
            r.scripts = {
                "disabled_inherited": [
                    {"collection_id": coll.id, "script_type": "pre_request"},
                ],
            }
            session.commit()

        pre, test = ScriptService.build_script_chain(req.id)
        assert pre == []
        assert len(test) == 1
        assert test[0]["code"] == "// coll t"


# ===================================================================
# ScriptService.build_collection_script_chain (inline, no DB)
# ===================================================================


class TestBuildCollectionScriptChain:
    """Verify inline chain builder (for draft requests)."""

    def test_none_returns_empty(self) -> None:
        pre, test = ScriptService.build_collection_script_chain(None)
        assert pre == [] and test == []

    def test_with_scripts(self) -> None:
        events: dict[str, str] = {
            "pre_request": "// pre code",
            "test": "// test code",
            "language": "python",
        }
        pre, test = ScriptService.build_collection_script_chain(events, name="Draft")
        assert len(pre) == 1
        assert pre[0]["code"] == "// pre code"
        assert pre[0]["language"] == "python"
        assert pre[0]["source_name"] == "Draft"
        assert len(test) == 1

    def test_empty_scripts_omitted(self) -> None:
        """Empty or whitespace-only scripts are not included in the chain."""
        events: dict[str, str] = {"pre_request": "  ", "test": ""}
        pre, test = ScriptService.build_collection_script_chain(events)
        assert pre == [] and test == []
