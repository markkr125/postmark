"""Repository tests for user-authored script snippets."""

from __future__ import annotations

from database.models.snippets.snippet_repository import (
    create_snippet,
    delete_snippet,
    list_snippets,
)


def test_create_and_list_snippet() -> None:
    """Created snippets are listed for their language."""
    row = create_snippet(
        name="My log",
        language="js",
        category="Helpers",
        body="console.log('hi');",
        context="both",
    )
    rows = list_snippets(language="js")
    assert any(r["id"] == row.id for r in rows)


def test_delete_snippet() -> None:
    """Deleting removes the row from subsequent list calls."""
    row = create_snippet(
        name="Temp",
        language="py",
        category="Helpers",
        body="pass",
        context="both",
    )
    delete_snippet(int(row.id))
    assert not any(r["id"] == row.id for r in list_snippets(language="py"))


def test_migrate_drops_legacy_scope_columns(tmp_path) -> None:
    """The one-time migration rebuilds snippets without the legacy scope columns."""
    from sqlalchemy import create_engine, inspect, text

    from database.database import _migrate_drop_snippet_scope_columns

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE snippets ("
                "id INTEGER PRIMARY KEY, name VARCHAR, language VARCHAR, "
                "category VARCHAR, body TEXT, context VARCHAR, "
                "scope_collection_id INTEGER, scope_local_script_id INTEGER, "
                "created_at DATETIME)"
            )
        )
        for index_sql in (
            "CREATE INDEX ix_snippets_id ON snippets (id)",
            "CREATE INDEX ix_snippets_name ON snippets (name)",
            "CREATE INDEX ix_snippets_language ON snippets (language)",
            "CREATE INDEX ix_snippets_scope_collection_id ON snippets (scope_collection_id)",
            "CREATE INDEX ix_snippets_scope_local_script_id ON snippets (scope_local_script_id)",
        ):
            conn.execute(text(index_sql))
        conn.execute(
            text(
                "INSERT INTO snippets (id, name, language, category, body, context) "
                "VALUES (1, 'Keep', 'js', 'Helpers', 'x=1;', 'both')"
            )
        )

    _migrate_drop_snippet_scope_columns(engine)

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("snippets")}
    assert "scope_collection_id" not in cols
    assert "scope_local_script_id" not in cols
    index_names = {idx["name"] for idx in insp.get_indexes("snippets")}
    assert {"ix_snippets_id", "ix_snippets_name", "ix_snippets_language"} <= index_names
    assert not insp.has_table("snippets__old")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM snippets WHERE id = 1")).scalar() == "Keep"

    _migrate_drop_snippet_scope_columns(engine)  # idempotent: second run is a no-op
