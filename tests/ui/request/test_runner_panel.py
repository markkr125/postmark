"""Tests for folder inline collection runner (`_RunnerPanel`)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ui.request.folder_editor.runner_panel import _RunnerPanel


def _synthetic_tree() -> dict[str, Any]:
    """Root 1 -> child folder 2 (mapper) -> two requests; unrelated root 99."""
    return {
        "1": {
            "id": 1,
            "name": "Root",
            "type": "folder",
            "children": {
                "2": {
                    "id": 2,
                    "name": "mapper",
                    "type": "folder",
                    "children": {
                        "10": {"type": "request", "id": 10, "name": "A", "method": "GET"},
                        "11": {"type": "request", "id": 11, "name": "B", "method": "POST"},
                    },
                },
            },
        },
        "99": {
            "id": 99,
            "name": "OtherRoot",
            "type": "folder",
            "children": {
                "200": {"type": "request", "id": 200, "name": "X", "method": "GET"},
            },
        },
    }


class TestRunnerPanelCollectRequests:
    """Regression: nested folder IDs must resolve (not only root keys)."""

    def test_collect_requests_nested_folder(self, qapp: QApplication) -> None:
        """Child folder id finds subtree; returns depth-first request dicts."""
        with patch(
            "ui.request.folder_editor.runner_panel.CollectionService.fetch_all",
            return_value=_synthetic_tree(),
        ):
            out = _RunnerPanel._collect_requests(2)
        assert len(out) == 2
        assert [r.get("name") for r in out] == ["A", "B"]

    def test_collect_requests_root_folder(self, qapp: QApplication) -> None:
        """Root collection id still walks entire subtree under that root."""
        with patch(
            "ui.request.folder_editor.runner_panel.CollectionService.fetch_all",
            return_value=_synthetic_tree(),
        ):
            out = _RunnerPanel._collect_requests(1)
        assert len(out) == 2
        names = {r.get("name") for r in out}
        assert names == {"A", "B"}

    def test_collect_requests_other_root(self, qapp: QApplication) -> None:
        """Second root tree is searched when first root does not match."""
        with patch(
            "ui.request.folder_editor.runner_panel.CollectionService.fetch_all",
            return_value=_synthetic_tree(),
        ):
            out = _RunnerPanel._collect_requests(99)
        assert len(out) == 1
        assert out[0].get("name") == "X"

    def test_collect_requests_unknown_id(self, qapp: QApplication) -> None:
        """Missing collection id yields empty list without error."""
        with patch(
            "ui.request.folder_editor.runner_panel.CollectionService.fetch_all",
            return_value=_synthetic_tree(),
        ):
            out = _RunnerPanel._collect_requests(9999)
        assert out == []
