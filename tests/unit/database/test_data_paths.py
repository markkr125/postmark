"""Tests for database.data_paths helpers."""

from __future__ import annotations

import database.data_paths as data_paths
from database.data_paths import project_root, user_history_root


def test_project_root_is_repo_not_src() -> None:
    """SQLite and project ``data/`` live at the repo root, not under ``src/``."""
    root = project_root()
    assert root.name != "src"
    assert (root / "src" / "main.py").is_file()
    assert (root / "data" / "database").is_dir()


def test_user_history_under_postmark_user_data_dir(tmp_path, monkeypatch) -> None:
    """History bodies/snapshots use the OS user-data dir, not the project tree."""
    monkeypatch.setattr(
        "database.data_paths.postmark_user_data_dir",
        lambda: tmp_path / "postmark",
    )
    history = user_history_root()
    assert history == tmp_path / "postmark" / "history"
    assert data_paths.postmark_user_data_dir() == tmp_path / "postmark"
    assert project_root() / "data" / "database" != history
