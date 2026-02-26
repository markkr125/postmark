"""Tests for the EnvironmentSelector widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.environments.environment_selector import EnvironmentSelector


class TestEnvironmentSelector:
    """Tests for the environment selector dropdown."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """Selector starts with 'No Environment' option."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        assert selector.count() == 1
        assert selector.currentText() == "No Environment"

    def test_current_id_none_by_default(self, qapp: QApplication, qtbot) -> None:
        """Default selection returns None as environment_id."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        assert selector.current_environment_id() is None

    def test_load_environments(self, qapp: QApplication, qtbot) -> None:
        """Loading environments populates the dropdown."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        selector.load_environments(
            [
                {"id": 1, "name": "Dev", "values": []},
                {"id": 2, "name": "Prod", "values": []},
            ]
        )
        assert selector.count() == 5  # No Environment + Dev + Prod + sep + Manage

    def test_select_environment(self, qapp: QApplication, qtbot) -> None:
        """Selecting an environment returns its ID."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        selector.load_environments(
            [
                {"id": 10, "name": "Dev", "values": []},
            ]
        )
        selector.setCurrentIndex(1)  # Select "Dev"
        assert selector.current_environment_id() == 10

    def test_environment_changed_signal(self, qapp: QApplication, qtbot) -> None:
        """Changing selection emits environment_changed."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        selector.load_environments(
            [
                {"id": 5, "name": "Test", "values": []},
            ]
        )
        with qtbot.waitSignal(selector.environment_changed, timeout=1000):
            selector.setCurrentIndex(1)

    def test_load_preserves_selection(self, qapp: QApplication, qtbot) -> None:
        """Reloading environments preserves the current selection."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        selector.load_environments(
            [
                {"id": 1, "name": "Dev", "values": []},
                {"id": 2, "name": "Prod", "values": []},
            ]
        )
        selector.setCurrentIndex(2)  # Select "Prod"
        assert selector.current_environment_id() == 2

        # Reload with same data
        selector.load_environments(
            [
                {"id": 1, "name": "Dev", "values": []},
                {"id": 2, "name": "Prod", "values": []},
            ]
        )
        assert selector.current_environment_id() == 2

    def test_refresh_loads_from_service(self, qapp: QApplication, qtbot) -> None:
        """refresh() loads environments from the service layer."""
        from services.environment_service import EnvironmentService

        EnvironmentService.create_environment("FromDB")

        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        selector.refresh()
        assert selector.count() >= 2  # At least No Environment + FromDB

    def test_manage_entry_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """Selecting 'Manage Environments...' emits manage_requested."""
        selector = EnvironmentSelector()
        qtbot.addWidget(selector)
        selector.load_environments([{"id": 1, "name": "Dev", "values": []}])

        # Find the "Manage Environments..." index
        manage_idx = -1
        for i in range(selector.count()):
            if selector.itemText(i) == "Manage Environments\u2026":
                manage_idx = i
                break
        assert manage_idx >= 0

        with qtbot.waitSignal(selector.manage_requested, timeout=1000):
            selector.setCurrentIndex(manage_idx)

        # Selection should revert to previous
        assert selector.currentText() != "Manage Environments\u2026"
