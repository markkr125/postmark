"""Unit tests for the script version repository CRUD layer."""

from __future__ import annotations

from database.models.script_versions.script_version_repository import (
    _MAX_VERSIONS_PER_SCRIPT,
    delete_script_versions,
    get_script_version,
    get_script_versions,
    save_script_version,
)


class TestSaveScriptVersion:
    """Tests for save_script_version."""

    def test_save_returns_model(self) -> None:
        """save_script_version returns a persisted model with an ID."""
        v = save_script_version(request_id=1, script_type="pre_request", content="hello")
        assert v.id is not None
        assert v.request_id == 1
        assert v.script_type == "pre_request"
        assert v.content == "hello"
        assert v.language == "javascript"

    def test_save_collection_owner(self) -> None:
        """Versions can be owned by a collection instead of a request."""
        v = save_script_version(
            collection_id=5, script_type="test", content="pm.test()", language="python"
        )
        assert v.collection_id == 5
        assert v.request_id is None
        assert v.language == "python"

    def test_save_sets_created_at(self) -> None:
        """The created_at timestamp is populated automatically."""
        v = save_script_version(request_id=1, script_type="test", content="")
        assert v.created_at is not None


class TestGetScriptVersions:
    """Tests for get_script_versions."""

    def test_returns_newest_first(self) -> None:
        """Versions are returned with the newest entry first."""
        save_script_version(request_id=1, script_type="pre_request", content="v1")
        save_script_version(request_id=1, script_type="pre_request", content="v2")
        save_script_version(request_id=1, script_type="pre_request", content="v3")

        versions = get_script_versions(request_id=1, script_type="pre_request")
        assert len(versions) == 3
        assert versions[0]["content"] == "v3"
        assert versions[2]["content"] == "v1"

    def test_filters_by_script_type(self) -> None:
        """Only versions matching the script_type are returned."""
        save_script_version(request_id=1, script_type="pre_request", content="a")
        save_script_version(request_id=1, script_type="test", content="b")

        pre = get_script_versions(request_id=1, script_type="pre_request")
        assert len(pre) == 1
        assert pre[0]["content"] == "a"

    def test_filters_by_owner(self) -> None:
        """Versions for different owners are isolated."""
        save_script_version(request_id=1, script_type="test", content="r1")
        save_script_version(request_id=2, script_type="test", content="r2")

        r1 = get_script_versions(request_id=1, script_type="test")
        assert len(r1) == 1
        assert r1[0]["content"] == "r1"

    def test_limit_parameter(self) -> None:
        """The limit parameter caps the number of returned versions."""
        for i in range(5):
            save_script_version(request_id=1, script_type="test", content=f"v{i}")

        versions = get_script_versions(request_id=1, script_type="test", limit=3)
        assert len(versions) == 3

    def test_empty_result(self) -> None:
        """Returns an empty list when no matching versions exist."""
        versions = get_script_versions(request_id=999, script_type="test")
        assert versions == []


class TestGetScriptVersion:
    """Tests for get_script_version (single)."""

    def test_returns_dict(self) -> None:
        """get_script_version returns all fields as a dict."""
        v = save_script_version(request_id=1, script_type="pre_request", content="x")
        result = get_script_version(v.id)
        assert result is not None
        assert result["id"] == v.id
        assert result["content"] == "x"
        assert result["script_type"] == "pre_request"

    def test_not_found(self) -> None:
        """Missing version ID returns None."""
        assert get_script_version(999) is None


class TestDeleteScriptVersions:
    """Tests for delete_script_versions."""

    def test_deletes_by_request(self) -> None:
        """All versions for a request are deleted."""
        save_script_version(request_id=1, script_type="test", content="a")
        save_script_version(request_id=1, script_type="pre_request", content="b")
        save_script_version(request_id=2, script_type="test", content="c")

        deleted = delete_script_versions(request_id=1)
        assert deleted == 2
        assert get_script_versions(request_id=1, script_type="test") == []
        assert len(get_script_versions(request_id=2, script_type="test")) == 1

    def test_deletes_by_collection(self) -> None:
        """All versions for a collection are deleted."""
        save_script_version(collection_id=10, script_type="test", content="a")
        deleted = delete_script_versions(collection_id=10)
        assert deleted == 1


class TestPruning:
    """Tests for automatic version pruning."""

    def test_prune_keeps_max_versions(self) -> None:
        """Saving beyond the limit prunes the oldest versions."""
        for i in range(_MAX_VERSIONS_PER_SCRIPT + 5):
            save_script_version(request_id=1, script_type="test", content=f"v{i}")

        versions = get_script_versions(
            request_id=1, script_type="test", limit=_MAX_VERSIONS_PER_SCRIPT + 10
        )
        assert len(versions) == _MAX_VERSIONS_PER_SCRIPT
        # The newest version should be the last one saved.
        assert versions[0]["content"] == f"v{_MAX_VERSIONS_PER_SCRIPT + 4}"
