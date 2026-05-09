"""Tests for inherited script banner, chain ordering, and save of ``disabled_inherited``."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

from database.database import get_session
from database.models.collections.model.collection_model import CollectionModel
from database.models.collections.model.request_model import RequestModel
from ui.request.request_editor import RequestEditorWidget
from ui.request.request_editor.scripts.scripts_mixin import _ScriptsMixin


class TestInheritedBlocksOrder:
    """``_inherited_blocks_for_type`` must match script execution order for inherited only."""

    def test_pre_root_to_leaf(self) -> None:
        chain: list[dict[str, Any]] = [
            {
                "source": "collection",
                "id": 1,
                "name": "Root",
                "scripts": {"pre_request": "pre1"},
            },
            {
                "source": "collection",
                "id": 2,
                "name": "Leaf",
                "scripts": {"pre_request": "pre2"},
            },
            {"source": "request", "id": 9, "name": "R", "scripts": {}},
        ]
        out = _ScriptsMixin._inherited_blocks_for_type(chain, "pre_request")
        assert [b["code"] for b in out] == ["pre1", "pre2"]
        assert [b["name"] for b in out] == ["Root", "Leaf"]

    def test_test_nearest_to_root(self) -> None:
        """Inherited post-response: parent folder before grandparent (execution order)."""
        chain: list[dict[str, Any]] = [
            {
                "source": "collection",
                "id": 1,
                "name": "Root",
                "scripts": {"test": "t1"},
            },
            {
                "source": "collection",
                "id": 2,
                "name": "Leaf",
                "scripts": {"test": "t2"},
            },
            {"source": "request", "id": 9, "name": "R", "scripts": {}},
        ]
        out = _ScriptsMixin._inherited_blocks_for_type(chain, "test")
        assert [b["code"] for b in out] == ["t2", "t1"]


class TestInheritedScriptsUI:
    """Widget-level tests for inherited script banner and chain drawer."""

    def test_banner_hidden_when_no_ancestor_scripts(
        self,
        qapp: QApplication,
        make_collection_with_request: Any,
    ) -> None:
        coll, req = make_collection_with_request()
        with get_session() as session:
            c = session.get(CollectionModel, coll.id)
            assert c is not None
            c.events = {}
            r = session.get(RequestModel, req.id)
            assert r is not None
            r.scripts = None
            session.commit()
        ed = RequestEditorWidget()
        ed.load_request(
            {
                "name": "N",
                "method": "GET",
                "url": "http://x",
                "body": "",
                "scripts": None,
            },
            request_id=req.id,
        )
        # Banners are in the Scripts tab; hidden tabs report isVisible() false.
        ed._tabs.setCurrentIndex(5)
        ed._scripts_sub_tabs.setCurrentIndex(0)
        assert "inherit" not in ed._pre_inherited_banner._text.text().lower()
        ed._scripts_sub_tabs.setCurrentIndex(1)
        assert "inherit" not in ed._test_inherited_banner._text.text().lower()

    def test_banner_shows_when_collection_has_pre(
        self,
        qapp: QApplication,
        make_collection_with_request: Any,
    ) -> None:
        coll, req = make_collection_with_request()
        with get_session() as session:
            c = session.get(CollectionModel, coll.id)
            assert c is not None
            c.events = {"pre_request": "//p"}
            session.commit()
        ed = RequestEditorWidget()
        ed.load_request(
            {
                "name": "N",
                "method": "GET",
                "url": "http://x",
                "body": "",
                "scripts": None,
            },
            request_id=req.id,
        )
        ed._tabs.setCurrentIndex(5)
        ed._scripts_sub_tabs.setCurrentIndex(0)
        assert "1" in ed._pre_inherited_banner._text.text()
        assert "inherit" in ed._pre_inherited_banner._text.text().lower()

    def test_get_scripts_data_persists_disabled_only(
        self,
        qapp: QApplication,
        make_collection_with_request: Any,
    ) -> None:
        coll, req = make_collection_with_request()
        ed = RequestEditorWidget()
        ed.load_request(
            {
                "name": "N",
                "method": "GET",
                "url": "http://x",
                "body": "",
                "scripts": None,
            },
            request_id=req.id,
        )
        ed._ensure_scripts_editors()
        ed._disabled_inherited = [{"collection_id": coll.id, "script_type": "pre_request"}]
        data = ed.get_request_data()["scripts"]
        assert data is not None
        assert data.get("pre_request") in (None, "")
        assert "disabled_inherited" in data
        assert any(
            d.get("collection_id") == coll.id and d.get("script_type") == "pre_request"
            for d in (data.get("disabled_inherited") or [])
        )
