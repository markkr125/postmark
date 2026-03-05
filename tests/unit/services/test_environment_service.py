"""Unit tests for the environment service layer."""

from __future__ import annotations

import pytest

from database.models.collections.collection_repository import (
    create_new_collection,
    create_new_request,
    update_collection,
)
from services.environment_service import EnvironmentService


class TestEnvironmentService:
    """Tests verifying the environment service delegates correctly."""

    def test_create_environment(self) -> None:
        """Creating an environment returns a persisted model with an id."""
        env = EnvironmentService.create_environment("Dev")
        assert env.id is not None
        assert env.name == "Dev"

    def test_create_environment_rejects_empty_name(self) -> None:
        """An empty name raises ValueError."""
        with pytest.raises(ValueError, match="Environment name must not be empty"):
            EnvironmentService.create_environment("   ")

    def test_fetch_all(self) -> None:
        """fetch_all returns list of dicts with id, name, values."""
        EnvironmentService.create_environment("A")
        EnvironmentService.create_environment("B")
        envs = EnvironmentService.fetch_all()
        assert len(envs) >= 2
        names = {e["name"] for e in envs}
        assert "A" in names
        assert "B" in names

    def test_get_environment(self) -> None:
        """A created environment can be fetched by id."""
        env = EnvironmentService.create_environment("Fetchable")
        fetched = EnvironmentService.get_environment(env.id)
        assert fetched is not None
        assert fetched.name == "Fetchable"

    def test_rename_environment(self) -> None:
        """Renaming an environment updates its name."""
        env = EnvironmentService.create_environment("Old")
        EnvironmentService.rename_environment(env.id, "New")
        renamed = EnvironmentService.get_environment(env.id)
        assert renamed is not None
        assert renamed.name == "New"

    def test_rename_rejects_empty(self) -> None:
        """An empty new name raises ValueError."""
        env = EnvironmentService.create_environment("Existing")
        with pytest.raises(ValueError, match="Environment name must not be empty"):
            EnvironmentService.rename_environment(env.id, "   ")

    def test_delete_environment(self) -> None:
        """Deleting an environment removes it from the database."""
        env = EnvironmentService.create_environment("Doomed")
        EnvironmentService.delete_environment(env.id)
        assert EnvironmentService.get_environment(env.id) is None


class TestVariableSubstitution:
    """Tests for environment variable substitution."""

    def test_build_variable_map_none(self) -> None:
        """None environment_id returns empty dict."""
        result = EnvironmentService.build_variable_map(None)
        assert result == {}

    def test_build_variable_map_nonexistent(self) -> None:
        """Non-existent environment_id returns empty dict."""
        result = EnvironmentService.build_variable_map(99999)
        assert result == {}

    def test_build_variable_map(self) -> None:
        """build_variable_map extracts enabled variables."""
        env = EnvironmentService.create_environment(
            "Test",
            values=[
                {"key": "base_url", "value": "https://api.test", "enabled": True},
                {"key": "secret", "value": "hidden", "enabled": False},
                {"key": "token", "value": "abc123"},
            ],
        )
        var_map = EnvironmentService.build_variable_map(env.id)
        assert var_map["base_url"] == "https://api.test"
        assert "secret" not in var_map
        assert var_map["token"] == "abc123"

    def test_substitute_simple(self) -> None:
        """Simple variable substitution replaces placeholders."""
        result = EnvironmentService.substitute(
            "{{base_url}}/users",
            {"base_url": "https://api.test"},
        )
        assert result == "https://api.test/users"

    def test_substitute_multiple(self) -> None:
        """Multiple variables are all replaced."""
        result = EnvironmentService.substitute(
            "{{host}}:{{port}}/api",
            {"host": "localhost", "port": "8080"},
        )
        assert result == "localhost:8080/api"

    def test_substitute_unknown_left_unchanged(self) -> None:
        """Unknown variables are left as-is."""
        result = EnvironmentService.substitute(
            "{{known}}/{{unknown}}",
            {"known": "value"},
        )
        assert result == "value/{{unknown}}"

    def test_substitute_no_variables(self) -> None:
        """Text without placeholders is returned unchanged."""
        result = EnvironmentService.substitute("hello world", {"key": "val"})
        assert result == "hello world"

    def test_substitute_empty_map(self) -> None:
        """Empty variable map returns text unchanged."""
        result = EnvironmentService.substitute("{{foo}}", {})
        assert result == "{{foo}}"

    def test_substitute_with_spaces(self) -> None:
        """Variables with surrounding spaces are trimmed."""
        result = EnvironmentService.substitute(
            "{{ base_url }}/path",
            {"base_url": "https://api"},
        )
        assert result == "https://api/path"


class TestUpdateEnvironmentValues:
    """Tests for updating environment variable values."""

    def test_update_values(self) -> None:
        """Updating values replaces the stored variable list."""
        env = EnvironmentService.create_environment("Updatable")
        new_values = [{"key": "host", "value": "localhost", "enabled": True}]
        EnvironmentService.update_environment_values(env.id, new_values)
        fetched = EnvironmentService.get_environment(env.id)
        assert fetched is not None
        assert fetched.values == new_values


class TestCombinedVariableMap:
    """Tests for ``build_combined_variable_map`` merging collection + env."""

    def test_no_env_no_request(self) -> None:
        """Both None returns empty dict."""
        result = EnvironmentService.build_combined_variable_map(None, None)
        assert result == {}

    def test_only_collection_variables(self) -> None:
        """Collection variables are returned when no environment is set."""
        coll = create_new_collection("Root")
        update_collection(
            coll.id,
            variables=[{"key": "host", "value": "coll-host", "enabled": True}],
        )
        req = create_new_request(coll.id, "GET", "http://x", "R")
        result = EnvironmentService.build_combined_variable_map(None, req.id)
        assert result == {"host": "coll-host"}

    def test_only_environment_variables(self) -> None:
        """Environment variables are returned when no request is set."""
        env = EnvironmentService.create_environment(
            "Dev",
            values=[{"key": "base_url", "value": "https://api", "enabled": True}],
        )
        result = EnvironmentService.build_combined_variable_map(env.id, None)
        assert result == {"base_url": "https://api"}

    def test_env_overrides_collection(self) -> None:
        """Environment variables take precedence over collection variables."""
        coll = create_new_collection("Root")
        update_collection(
            coll.id,
            variables=[
                {"key": "host", "value": "coll-host", "enabled": True},
                {"key": "port", "value": "8080", "enabled": True},
            ],
        )
        req = create_new_request(coll.id, "GET", "http://x", "R")
        env = EnvironmentService.create_environment(
            "Dev",
            values=[{"key": "host", "value": "env-host", "enabled": True}],
        )
        result = EnvironmentService.build_combined_variable_map(env.id, req.id)
        # Environment overrides collection for 'host'
        assert result["host"] == "env-host"
        # Collection-only var is inherited
        assert result["port"] == "8080"

    def test_merged_from_nested_collections_and_env(self) -> None:
        """Variables merge from nested collections and environment."""
        root = create_new_collection("Root")
        update_collection(
            root.id,
            variables=[{"key": "a", "value": "from-root", "enabled": True}],
        )
        child = create_new_collection("Child", parent_id=root.id)
        update_collection(
            child.id,
            variables=[{"key": "b", "value": "from-child", "enabled": True}],
        )
        req = create_new_request(child.id, "GET", "http://x", "R")
        env = EnvironmentService.create_environment(
            "Dev",
            values=[{"key": "c", "value": "from-env", "enabled": True}],
        )
        result = EnvironmentService.build_combined_variable_map(env.id, req.id)
        assert result == {"a": "from-root", "b": "from-child", "c": "from-env"}
