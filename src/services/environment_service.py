"""Service layer for environment management and variable substitution.

All environment-related database access from the UI should go through
this module so that widgets never import ``environment_repository``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, TypedDict

from database.models.environments.environment_repository import (
    create_environment, delete_environment, fetch_all_environments,
    get_environment_by_id, rename_environment, update_environment_values)
from database.models.environments.model.environment_model import \
    EnvironmentModel

logger = logging.getLogger(__name__)

# Regex pattern for {{variable}} substitution
_VAR_PATTERN = re.compile(r"\{\{(.+?)\}\}")


class _VariableDetailRequired(TypedDict):
    """Required fields for variable metadata."""

    value: str
    source: str  # "collection", "environment", or "local"
    source_id: int  # collection_id or environment_id (0 for local)


class VariableDetail(_VariableDetailRequired, total=False):
    """Variable metadata exposed to the UI for popups and tooltips.

    The optional *is_local* flag is ``True`` when the value shown is a
    per-request override rather than the persisted value.
    """

    is_local: bool


class LocalOverride(TypedDict):
    """Per-request variable override stored in ``TabContext``.

    Captures the overridden value together with the original source
    so that the popup can offer **Update** (persist globally) and
    **Reset** (remove override) actions.
    """

    value: str
    original_source: str
    original_source_id: int


class EnvironmentService:
    """Service that wraps environment repository calls with validation.

    All methods are ``@staticmethod`` — the class exists so it can
    later gain instance state for caching.
    """

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_all() -> list[dict[str, Any]]:
        """Return all environments as a list of dicts."""
        result = fetch_all_environments()
        logger.debug("Fetched %d environments", len(result))
        return result

    @staticmethod
    def get_environment(environment_id: int) -> EnvironmentModel | None:
        """Look up a single environment by primary key."""
        return get_environment_by_id(environment_id)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    @staticmethod
    def create_environment(
        name: str,
        values: list[dict[str, Any]] | None = None,
    ) -> EnvironmentModel:
        """Create a new environment.

        Raises:
            ValueError: If *name* is empty or whitespace-only.
        """
        name = name.strip()
        if not name:
            raise ValueError("Environment name must not be empty")
        result = create_environment(name, values)
        logger.info("Created environment id=%s name=%r", result.id, name)
        return result

    @staticmethod
    def rename_environment(environment_id: int, new_name: str) -> None:
        """Rename an existing environment.

        Raises:
            ValueError: If *new_name* is empty or whitespace-only.
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Environment name must not be empty")
        rename_environment(environment_id, new_name)
        logger.info("Renamed environment id=%s to %r", environment_id, new_name)

    @staticmethod
    def delete_environment(environment_id: int) -> None:
        """Delete an environment."""
        delete_environment(environment_id)
        logger.info("Deleted environment id=%s", environment_id)

    @staticmethod
    def update_environment_values(
        environment_id: int,
        values: list[dict[str, Any]],
    ) -> None:
        """Replace the variable values of an existing environment."""
        update_environment_values(environment_id, values)
        logger.info("Updated environment values id=%s", environment_id)

    # ------------------------------------------------------------------
    # Variable substitution
    # ------------------------------------------------------------------
    @staticmethod
    def build_variable_map(environment_id: int | None) -> dict[str, str]:
        """Build a key→value map from the selected environment.

        Only includes variables with ``enabled`` set to ``True`` (or
        missing the ``enabled`` key, which defaults to enabled).

        Returns an empty dict if *environment_id* is ``None`` or the
        environment is not found.
        """
        if environment_id is None:
            return {}
        env = get_environment_by_id(environment_id)
        if env is None:
            return {}
        variables: dict[str, str] = {}
        for entry in env.values or []:
            if not entry.get("enabled", True):
                continue
            key = entry.get("key", "")
            value = entry.get("value", "")
            if key:
                variables[key] = value
        return variables

    @staticmethod
    def build_combined_variable_map(
        environment_id: int | None,
        request_id: int | None,
    ) -> dict[str, str]:
        """Build a merged variable map from collection and environment.

        Collection variables are inherited upward from the request's
        parent chain.  Environment variables take precedence over
        collection variables when keys overlap.

        Returns an empty dict if neither source provides variables.
        """
        from database.models.collections.collection_repository import \
            get_request_variable_chain

        # 1. Collection-level variables (inherited up the tree)
        variables: dict[str, str] = {}
        if request_id is not None:
            variables = get_request_variable_chain(request_id)

        # 2. Environment variables override collection variables
        env_vars = EnvironmentService.build_variable_map(environment_id)
        variables.update(env_vars)

        return variables

    @staticmethod
    def build_combined_variable_detail_map(
        environment_id: int | None,
        request_id: int | None,
    ) -> dict[str, VariableDetail]:
        """Build a merged variable map with source metadata.

        Like :meth:`build_combined_variable_map` but each value is a
        :class:`VariableDetail` recording the resolved value **and**
        whether it came from ``"collection"`` or ``"environment"``.
        Environment variables take precedence over collection variables.
        """
        from database.models.collections.collection_repository import \
            get_request_variable_chain_detailed

        details: dict[str, VariableDetail] = {}

        # 1. Collection-level variables (inherited up the tree)
        if request_id is not None:
            for key, (value, coll_id) in get_request_variable_chain_detailed(request_id).items():
                details[key] = {
                    "value": value,
                    "source": "collection",
                    "source_id": coll_id,
                }

        # 2. Environment variables override collection variables
        if environment_id is not None:
            for key, value in EnvironmentService.build_variable_map(environment_id).items():
                details[key] = {
                    "value": value,
                    "source": "environment",
                    "source_id": environment_id,
                }

        return details

    @staticmethod
    def update_variable_value(
        source: str,
        source_id: int,
        key: str,
        new_value: str,
    ) -> None:
        """Update a single variable's value at its source.

        Reads the full variable list from the source (collection or
        environment), patches the matching entry, and writes it back.

        Raises:
            ValueError: If *source* is not ``"collection"`` or
                ``"environment"``.
        """
        if source == "collection":
            EnvironmentService._update_collection_variable(source_id, key, new_value)
        elif source == "environment":
            EnvironmentService._update_environment_variable(source_id, key, new_value)
        else:
            raise ValueError(f"Unknown variable source: {source!r}")

    @staticmethod
    def _update_collection_variable(
        collection_id: int,
        key: str,
        new_value: str,
    ) -> None:
        """Patch a single variable in a collection's variables list."""
        from database.database import get_session
        from database.models.collections.collection_repository import \
            update_collection
        from database.models.collections.model.collection_model import \
            CollectionModel

        with get_session() as session:
            coll = session.get(CollectionModel, collection_id)
            if coll is None:
                return
            variables = list(coll.variables or [])

        for entry in variables:
            if entry.get("key") == key:
                entry["value"] = new_value
                break

        update_collection(collection_id, variables=variables)
        logger.info(
            "Updated collection variable %r in collection id=%s",
            key,
            collection_id,
        )

    @staticmethod
    def _update_environment_variable(
        environment_id: int,
        key: str,
        new_value: str,
    ) -> None:
        """Patch a single variable in an environment's values list."""
        env = get_environment_by_id(environment_id)
        if env is None:
            return
        values = list(env.values or [])

        for entry in values:
            if entry.get("key") == key:
                entry["value"] = new_value
                break

        update_environment_values(environment_id, values)
        logger.info(
            "Updated environment variable %r in environment id=%s",
            key,
            environment_id,
        )

    @staticmethod
    def substitute(text: str, variables: dict[str, str]) -> str:
        """Replace ``{{variable}}`` placeholders in *text*.

        Unknown variables are left unchanged.
        """
        if not variables or "{{" not in text:
            return text

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            return variables.get(key, match.group(0))

        return _VAR_PATTERN.sub(_replace, text)

    # ------------------------------------------------------------------
    # Add variable (create new key)
    # ------------------------------------------------------------------

    @staticmethod
    def add_variable(
        source: str,
        source_id: int,
        key: str,
        value: str,
    ) -> None:
        """Add a new variable to a collection or environment.

        Appends a ``{"key": key, "value": value}`` entry to the existing
        variables list.  If a variable with the same *key* already
        exists, its value is updated instead.

        Raises:
            ValueError: If *source* is not ``"collection"`` or
                ``"environment"``.
        """
        if source == "collection":
            EnvironmentService._add_collection_variable(source_id, key, value)
        elif source == "environment":
            EnvironmentService._add_environment_variable(source_id, key, value)
        else:
            raise ValueError(f"Unknown variable source: {source!r}")

    @staticmethod
    def _add_collection_variable(
        collection_id: int,
        key: str,
        value: str,
    ) -> None:
        """Append a new variable to a collection's variables list."""
        from database.database import get_session
        from database.models.collections.collection_repository import \
            update_collection
        from database.models.collections.model.collection_model import \
            CollectionModel

        with get_session() as session:
            coll = session.get(CollectionModel, collection_id)
            if coll is None:
                return
            variables = list(coll.variables or [])

        # Update existing or append new
        for entry in variables:
            if entry.get("key") == key:
                entry["value"] = value
                update_collection(collection_id, variables=variables)
                return

        variables.append({"key": key, "value": value})
        update_collection(collection_id, variables=variables)
        logger.info(
            "Added collection variable %r to collection id=%s",
            key,
            collection_id,
        )

    @staticmethod
    def _add_environment_variable(
        environment_id: int,
        key: str,
        value: str,
    ) -> None:
        """Append a new variable to an environment's values list."""
        env = get_environment_by_id(environment_id)
        if env is None:
            return
        values = list(env.values or [])

        # Update existing or append new
        for entry in values:
            if entry.get("key") == key:
                entry["value"] = value
                update_environment_values(environment_id, values)
                return

        values.append({"key": key, "value": value})
        update_environment_values(environment_id, values)
        logger.info(
            "Added environment variable %r to environment id=%s",
            key,
            environment_id,
        )
