"""Migration tests for AI chat session schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import inspect

import database.database as db_mod
from database.database import init_db


def test_init_db_adds_agent_id_column_on_legacy_ai_chat_sessions(tmp_path: Path) -> None:
    """``_migrate_add_missing_columns`` adds ``agent_id`` with a server default."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE ai_chat_sessions (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                model_id VARCHAR(128),
                mode VARCHAR(32) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                last_preview TEXT,
                archived BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    db_mod._engine = None
    db_mod._SessionLocal = None
    init_db(db_path)
    assert db_mod._engine is not None
    insp = inspect(db_mod._engine)
    col_names = {c["name"] for c in insp.get_columns("ai_chat_sessions")}
    assert "agent_id" in col_names


def test_init_db_adds_thinking_duration_on_legacy_ai_chat_messages(tmp_path: Path) -> None:
    """``_migrate_add_missing_columns`` adds ``thinking_duration_seconds``."""
    db_path = tmp_path / "legacy_messages.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE ai_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(36) NOT NULL,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                thinking TEXT NOT NULL DEFAULT '',
                created_at DATETIME
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    db_mod._engine = None
    db_mod._SessionLocal = None
    init_db(db_path)
    assert db_mod._engine is not None
    insp = inspect(db_mod._engine)
    col_names = {c["name"] for c in insp.get_columns("ai_chat_messages")}
    assert "thinking_duration_seconds" in col_names


def test_init_db_adds_model_label_on_legacy_ai_chat_messages(tmp_path: Path) -> None:
    """``_migrate_add_missing_columns`` adds ``model_label``."""
    db_path = tmp_path / "legacy_model_label.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE ai_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(36) NOT NULL,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                thinking TEXT NOT NULL DEFAULT '',
                created_at DATETIME
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    db_mod._engine = None
    db_mod._SessionLocal = None
    init_db(db_path)
    assert db_mod._engine is not None
    insp = inspect(db_mod._engine)
    col_names = {c["name"] for c in insp.get_columns("ai_chat_messages")}
    assert "model_label" in col_names


def test_init_db_adds_cost_usd_on_legacy_ai_chat_messages(tmp_path: Path) -> None:
    """``_migrate_add_missing_columns`` adds ``cost_usd``."""
    db_path = tmp_path / "legacy_cost_usd.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE ai_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(36) NOT NULL,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                thinking TEXT NOT NULL DEFAULT '',
                created_at DATETIME
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    db_mod._engine = None
    db_mod._SessionLocal = None
    init_db(db_path)
    assert db_mod._engine is not None
    insp = inspect(db_mod._engine)
    col_names = {c["name"] for c in insp.get_columns("ai_chat_messages")}
    assert "cost_usd" in col_names
