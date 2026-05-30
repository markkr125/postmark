"""Tests for local-script path-safe name validation."""

from __future__ import annotations

import pytest

from database.models.local_scripts.path_policy import (
    is_path_safe_folder_name,
    is_path_safe_script_basename,
    validate_folder_name,
    validate_script_basename,
)


def test_folder_name_allows_dots() -> None:
    """Folder segments may contain dots (JS segment rules)."""
    assert is_path_safe_folder_name("auth.utils")
    assert validate_folder_name("auth.utils") == "auth.utils"


def test_folder_name_rejects_spaces() -> None:
    """Spaces are not path-safe."""
    assert not is_path_safe_folder_name("New Folder")
    with pytest.raises(ValueError, match="path-safe"):
        validate_folder_name("New Folder")


def test_script_basename_multi_dot_js() -> None:
    """``helper.test`` is valid for JavaScript (extension added separately)."""
    assert is_path_safe_script_basename("helper.test", "javascript")
    assert validate_script_basename("helper.test", "javascript") == "helper.test"


def test_script_basename_python_rejects_dots() -> None:
    """Python segments do not allow dots inside the basename."""
    assert not is_path_safe_script_basename("helper.test", "python")
