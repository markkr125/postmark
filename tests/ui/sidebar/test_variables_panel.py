"""Tests for the VariablesPanel widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication, QLabel

from ui.sidebar.variables_panel import VariablesPanel


class TestVariablesPanel:
    """Tests for the read-only variables display panel."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """VariablesPanel can be instantiated with empty state."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        assert panel is not None

    def test_empty_state_label(self, qapp: QApplication, qtbot) -> None:
        """Panel shows 'No variables available' when empty."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "No variables available" in texts

    def test_load_environment_variables(self, qapp: QApplication, qtbot) -> None:
        """Panel renders environment variables under the Environment section."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        variables: dict[str, Any] = {
            "api_key": {"value": "abc123", "source": "environment", "source_id": 1},
        }
        panel.load_variables(variables, has_environment=True)
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "api_key" in texts
        assert "abc123" in texts
        # Section header should be present
        assert "Environment" in texts

    def test_load_collection_variables(self, qapp: QApplication, qtbot) -> None:
        """Panel renders collection variables under the Collection section."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        variables: dict[str, Any] = {
            "base_url": {
                "value": "https://api.example.com",
                "source": "collection",
                "source_id": 5,
            },
        }
        panel.load_variables(variables, has_environment=True)
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "base_url" in texts
        assert "Requests collection" in texts

    def test_no_environment_message(self, qapp: QApplication, qtbot) -> None:
        """Panel shows 'No environment selected' when has_environment=False."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        panel.load_variables({}, has_environment=False)
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("No environment selected" in t for t in texts)

    def test_local_overrides_section(self, qapp: QApplication, qtbot) -> None:
        """Panel shows local overrides in a separate section."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        variables: dict[str, Any] = {
            "token": {"value": "original", "source": "environment", "source_id": 1},
        }
        overrides: dict[str, Any] = {
            "token": {
                "value": "local_val",
                "original_source": "environment",
                "original_source_id": 1,
            },
        }
        panel.load_variables(variables, local_overrides=overrides, has_environment=True)
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "Local overrides" in texts
        assert "local_val" in texts

    def test_clear_resets_to_empty(self, qapp: QApplication, qtbot) -> None:
        """clear() returns to the empty state."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        variables: dict[str, Any] = {
            "x": {"value": "y", "source": "environment", "source_id": 1},
        }
        panel.load_variables(variables, has_environment=True)
        panel.clear()
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "No variables available" in texts

    def test_grouping_multiple_sources(self, qapp: QApplication, qtbot) -> None:
        """Panel groups variables by source correctly."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        variables: dict[str, Any] = {
            "env_var": {"value": "e_val", "source": "environment", "source_id": 1},
            "coll_var": {"value": "c_val", "source": "collection", "source_id": 5},
        }
        panel.load_variables(variables, has_environment=True)
        labels = panel._content.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert "Environment" in texts
        assert "Requests collection" in texts
        assert "env_var" in texts
        assert "coll_var" in texts

    def test_long_value_has_tooltip(self, qapp: QApplication, qtbot) -> None:
        """Long values keep the full text available as a tooltip."""
        panel = VariablesPanel()
        qtbot.addWidget(panel)
        long_val = "a" * 60
        variables: dict[str, Any] = {
            "long_key": {"value": long_val, "source": "environment", "source_id": 1},
        }
        panel.load_variables(variables, has_environment=True)
        labels = panel._content.findChildren(QLabel)
        value_labels = [lbl for lbl in labels if lbl.objectName() == "variableValueLabel"]
        assert len(value_labels) == 1
        assert value_labels[0].text() == long_val
        assert value_labels[0].toolTip() == long_val
