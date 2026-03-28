"""Unit tests for ScriptVersionService."""

from __future__ import annotations

from services.script_version_service import ScriptVersionService


class TestCapture:
    """Tests for ScriptVersionService.capture."""

    def test_capture_saves_new_version(self) -> None:
        """Capture returns a version dict when content is new."""
        result = ScriptVersionService.capture(
            request_id=1,
            script_type="pre_request",
            content="console.log('hello')",
        )
        assert result is not None
        assert result["content"] == "console.log('hello')"

    def test_capture_dedup_skips_identical(self) -> None:
        """Capture returns None when content matches the latest snapshot."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="same")
        second = ScriptVersionService.capture(request_id=1, script_type="test", content="same")
        assert second is None

    def test_capture_saves_after_change(self) -> None:
        """Capture saves when content differs from the latest snapshot."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="v1")
        result = ScriptVersionService.capture(request_id=1, script_type="test", content="v2")
        assert result is not None
        assert result["content"] == "v2"

    def test_capture_skips_empty(self) -> None:
        """Capture returns None for empty/whitespace-only content."""
        assert ScriptVersionService.capture(request_id=1, script_type="test", content="   ") is None

    def test_capture_preserves_language(self) -> None:
        """Capture stores the language parameter."""
        result = ScriptVersionService.capture(
            request_id=1,
            script_type="test",
            content="print('hi')",
            language="python",
        )
        assert result is not None
        assert result["language"] == "python"


class TestListVersions:
    """Tests for ScriptVersionService.list_versions."""

    def test_list_returns_newest_first(self) -> None:
        """list_versions returns entries ordered newest first."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="a")
        ScriptVersionService.capture(request_id=1, script_type="test", content="b")
        versions = ScriptVersionService.list_versions(request_id=1, script_type="test")
        assert len(versions) == 2
        assert versions[0]["content"] == "b"

    def test_list_empty(self) -> None:
        """list_versions returns [] when no versions exist."""
        assert ScriptVersionService.list_versions(request_id=999, script_type="test") == []


class TestDiff:
    """Tests for ScriptVersionService.diff."""

    def test_diff_produces_unified_diff(self) -> None:
        """Diff returns unified diff output between two versions."""
        v1 = ScriptVersionService.capture(
            request_id=1, script_type="test", content="line1\nline2\n"
        )
        v2 = ScriptVersionService.capture(
            request_id=1, script_type="test", content="line1\nmodified\n"
        )
        assert v1 is not None and v2 is not None

        diff = ScriptVersionService.diff(v1["id"], v2["id"])
        assert diff is not None
        assert "-line2" in diff
        assert "+modified" in diff

    def test_diff_missing_version(self) -> None:
        """Diff returns None when a version ID is invalid."""
        assert ScriptVersionService.diff(999, 998) is None

    def test_diff_identical_versions(self) -> None:
        """Diff returns an empty string for identical content."""
        v = ScriptVersionService.capture(request_id=1, script_type="test", content="same\n")
        assert v is not None
        # Diff against itself.
        diff = ScriptVersionService.diff(v["id"], v["id"])
        assert diff == ""


class TestGetPreviousContent:
    """Tests for ScriptVersionService.get_previous_content."""

    def test_returns_previous_different_version(self) -> None:
        """get_previous_content finds the most recent differing version."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="old")
        ScriptVersionService.capture(request_id=1, script_type="test", content="new")
        result = ScriptVersionService.get_previous_content(
            request_id=1, script_type="test", current_content="new"
        )
        assert result == "old"

    def test_returns_none_when_all_identical(self) -> None:
        """get_previous_content returns None when only identical versions."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="only")
        result = ScriptVersionService.get_previous_content(
            request_id=1, script_type="test", current_content="only"
        )
        assert result is None

    def test_returns_none_when_no_versions(self) -> None:
        """get_previous_content returns None when no history exists."""
        result = ScriptVersionService.get_previous_content(
            request_id=999, script_type="test", current_content="anything"
        )
        assert result is None


class TestDeleteVersions:
    """Tests for ScriptVersionService.delete_versions."""

    def test_delete_clears_history(self) -> None:
        """delete_versions removes all versions for the owner."""
        ScriptVersionService.capture(request_id=1, script_type="test", content="a")
        ScriptVersionService.capture(request_id=1, script_type="pre_request", content="b")
        deleted = ScriptVersionService.delete_versions(request_id=1)
        assert deleted == 2
        assert ScriptVersionService.list_versions(request_id=1, script_type="test") == []
