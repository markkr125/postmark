"""Unit tests for the environment repository CRUD layer."""

from __future__ import annotations

import pytest

from database.models.environments.environment_repository import (
    create_environment,
    delete_environment,
    fetch_all_environments,
    get_environment_by_id,
    rename_environment,
)


class TestEnvironmentCRUD:
    """Tests for environment repository functions."""

    def test_create_environment(self) -> None:
        """Creating an environment persists name and values."""
        env = create_environment(
            "Production",
            values=[{"key": "base_url", "value": "https://prod.example.com"}],
        )
        assert env.id is not None
        assert env.name == "Production"
        assert env.values is not None
        assert len(env.values) == 1
        assert env.values[0]["key"] == "base_url"

    def test_create_environment_no_values(self) -> None:
        """An environment with no values defaults to None."""
        env = create_environment("Empty")
        assert env.id is not None
        assert env.values is None

    def test_fetch_all_environments(self) -> None:
        """fetch_all_environments returns every environment as dicts."""
        create_environment("Env A", values=[{"key": "a", "value": "1"}])
        create_environment("Env B", values=[{"key": "b", "value": "2"}])

        result = fetch_all_environments()
        assert len(result) == 2
        names = {e["name"] for e in result}
        assert names == {"Env A", "Env B"}

    def test_fetch_all_empty(self) -> None:
        """fetch_all_environments returns an empty list when no envs exist."""
        result = fetch_all_environments()
        assert result == []

    def test_get_environment_by_id(self) -> None:
        """An environment can be retrieved by its ID."""
        env = create_environment("Fetchable")
        fetched = get_environment_by_id(env.id)
        assert fetched is not None
        assert fetched.name == "Fetchable"

    def test_get_environment_by_id_not_found(self) -> None:
        """Missing ID returns None."""
        assert get_environment_by_id(99999) is None

    def test_rename_environment(self) -> None:
        """Renaming updates the persisted name."""
        env = create_environment("Old Name")
        rename_environment(env.id, "New Name")
        updated = get_environment_by_id(env.id)
        assert updated is not None
        assert updated.name == "New Name"

    def test_delete_environment(self) -> None:
        """Deleting removes the environment from the database."""
        env = create_environment("Doomed")
        delete_environment(env.id)
        assert get_environment_by_id(env.id) is None

    def test_delete_nonexistent_environment_raises(self) -> None:
        """Deleting a missing environment raises ValueError."""
        with pytest.raises(ValueError, match="No environment found"):
            delete_environment(99999)

    def test_environment_values_structure(self) -> None:
        """Values with multiple fields are stored correctly."""
        values = [
            {"key": "host", "value": "localhost", "enabled": True, "type": "default"},
            {"key": "secret", "value": "abc", "enabled": False, "type": "secret"},
        ]
        env = create_environment("Structured", values=values)
        fetched = get_environment_by_id(env.id)
        assert fetched is not None
        assert fetched.values is not None
        assert len(fetched.values) == 2
        assert fetched.values[0]["enabled"] is True
        assert fetched.values[1]["type"] == "secret"
