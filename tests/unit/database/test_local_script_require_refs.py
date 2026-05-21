"""Tests for ``pm.require("local:…")`` reference rewriting."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from database.database import get_session
from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
)
from database.models.collections.model.request_model import RequestModel
from database.models.local_scripts.local_script_repository import (
    create_folder,
    create_script,
    rename_folder_and_rewrite_refs,
    rename_script_and_rewrite_refs,
)
from database.models.local_scripts.require_refs_rewrite import rewrite_local_requires_in_text
from database.models.local_scripts.virtual_paths import script_virtual_rel_path
from ui.local_scripts.script_filename import script_basename_from_stored


def test_rewrite_exact_script_path_preserves_double_quotes() -> None:
    """Exact rename keeps double-quoted ``pm.require`` literals."""
    text = 'const x = pm.require("local:auth/helper.js");\n'
    out = rewrite_local_requires_in_text(
        text,
        "auth/helper.js",
        "auth/utilities.js",
        prefix=False,
    )
    assert out == 'const x = pm.require("local:auth/utilities.js");\n'


def test_rewrite_exact_script_path_preserves_single_quotes() -> None:
    """Exact rename keeps single-quoted literals."""
    text = "pm.require('local:auth/helper.js')"
    out = rewrite_local_requires_in_text(
        text,
        "auth/helper.js",
        "auth/utilities.js",
        prefix=False,
    )
    assert out == "pm.require('local:auth/utilities.js')"


def test_rewrite_prefix_does_not_over_match() -> None:
    """Prefix rename must not rewrite ``auth_v2`` or ``authentication_legacy``."""
    text = (
        'pm.require("local:auth/utils/a.js");\n'
        'pm.require("local:auth_v2/utils/b.js");\n'
        'pm.require("local:authentication_legacy/c.js");\n'
    )
    out = rewrite_local_requires_in_text(text, "auth", "authentication", prefix=True)
    assert "local:authentication/utils/a.js" in out
    assert "local:auth_v2/utils/b.js" in out
    assert "local:authentication_legacy/c.js" in out


def test_rewrite_nested_folder_prefix() -> None:
    """Nested folder prefix ``auth/utils`` -> ``auth/helpers``."""
    text = 'pm.require("local:auth/utils/helper.js")'
    out = rewrite_local_requires_in_text(text, "auth/utils", "auth/helpers", prefix=True)
    assert out == 'pm.require("local:auth/helpers/helper.js")'


def test_rewrite_ignores_non_pm_require_strings() -> None:
    """Plain strings mentioning ``local:`` outside ``pm.require`` are untouched."""
    text = 'const hint = "local:auth/helper.js";\npm.require("local:auth/helper.js");'
    out = rewrite_local_requires_in_text(text, "auth/helper.js", "auth/x.js", prefix=False)
    assert 'hint = "local:auth/helper.js"' in out
    assert 'pm.require("local:auth/x.js")' in out


def test_helper_test_js_virtual_path_round_trip() -> None:
    """Multi-dot basename ``helper.test`` maps to ``helper.test.js``."""
    root = create_folder("lib")
    script = create_script(root.id, "helper.test", language="javascript")
    with get_session() as session:
        rel = script_virtual_rel_path(session, script.id)
    assert rel == "lib/helper.test.js"
    assert script_basename_from_stored("helper.test") == "helper.test"


def test_rename_script_rewrites_request_scripts_json() -> None:
    """Rewriter updates ``RequestModel.scripts`` dict string values."""
    root = create_folder("auth")
    script = create_script(root.id, "helper", language="javascript")
    with get_session() as session:
        old_path = script_virtual_rel_path(session, script.id)

    coll = create_new_collection("API")
    create_new_request(
        coll.id,
        "GET",
        "https://example.com",
        "Req",
        scripts={"pre_request": f'pm.require("local:{old_path}")'},
    )

    rename_script_and_rewrite_refs(script.id, "utilities", language="javascript")

    with get_session() as session:
        new_path = script_virtual_rel_path(session, script.id)

    with get_session() as session:
        req = session.execute(select(RequestModel).limit(1)).scalar_one()
        assert req.scripts is not None
        assert f"local:{new_path}" in req.scripts["pre_request"]
        assert f"local:{old_path}" not in req.scripts["pre_request"]


def test_rename_folder_rewrites_prefix_in_local_script_content() -> None:
    """Folder rename updates prefix references in another script's body."""
    auth = create_folder("auth")
    utils = create_folder("utils", parent_id=auth.id)
    target = create_script(
        utils.id,
        "helper",
        language="javascript",
        content='pm.require("local:auth/utils/helper.js")',
    )
    consumer = create_script(
        auth.id,
        "consumer",
        language="javascript",
        content='pm.require("local:auth/utils/helper.js")',
    )

    rename_folder_and_rewrite_refs(utils.id, "helpers")

    with get_session() as session:
        from database.models.local_scripts.model.local_script_model import LocalScriptModel

        for sid in (target.id, consumer.id):
            row = session.get(LocalScriptModel, sid)
            assert row is not None
            assert "local:auth/helpers/helper.js" in (row.content or "")
            assert "local:auth/utils/" not in (row.content or "")


def test_rename_script_collision_skips_rewrite() -> None:
    """Duplicate sibling name raises before any reference rewrite."""
    root = create_folder("auth")
    create_script(root.id, "a", language="javascript", content='pm.require("local:auth/a.js")')
    second = create_script(
        root.id,
        "b",
        language="javascript",
        content='pm.require("local:auth/b.js")',
    )

    with pytest.raises(ValueError, match="already exists"):
        rename_script_and_rewrite_refs(second.id, "a")

    with get_session() as session:
        from database.models.local_scripts.model.local_script_model import LocalScriptModel

        row = session.get(LocalScriptModel, second.id)
        assert row is not None
        assert row.content == 'pm.require("local:auth/b.js")'
