"""Tests for the EnvironmentEditorDialog widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from services.environment_service import EnvironmentService
from ui.environment_editor import EnvironmentEditorDialog


class TestEnvironmentEditorDialog:
    """Tests for the environment editor dialog."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """EnvironmentEditorDialog can be constructed without errors."""
        dialog = EnvironmentEditorDialog()
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Manage Environments"

    def test_shows_existing_environments(self, qapp: QApplication, qtbot) -> None:
        """Dialog lists environments from the service layer."""
        EnvironmentService.create_environment("Dev", [])
        EnvironmentService.create_environment("Prod", [])

        dialog = EnvironmentEditorDialog()
        qtbot.addWidget(dialog)
        assert dialog._env_list.count() == 2

    def test_add_environment(self, qapp: QApplication, qtbot) -> None:
        """Clicking add creates a new environment."""
        dialog = EnvironmentEditorDialog()
        qtbot.addWidget(dialog)
        initial_count = dialog._env_list.count()
        dialog._on_add()
        assert dialog._env_list.count() == initial_count + 1

    def test_delete_environment(self, qapp: QApplication, qtbot) -> None:
        """Deleting an environment removes it from the list."""
        env = EnvironmentService.create_environment("ToDelete", [])
        dialog = EnvironmentEditorDialog()
        qtbot.addWidget(dialog)
        # Select the item
        dialog._env_list.setCurrentRow(0)
        assert dialog._current_env_id == env.id
        # Simulate deletion (bypass the QMessageBox)
        EnvironmentService.delete_environment(env.id)
        dialog._current_env_id = None
        dialog._refresh_list()
        assert dialog._env_list.count() == 0

    def test_environments_changed_signal(self, qapp: QApplication, qtbot) -> None:
        """Adding an environment emits environments_changed."""
        dialog = EnvironmentEditorDialog()
        qtbot.addWidget(dialog)
        with qtbot.waitSignal(dialog.environments_changed, timeout=1000):
            dialog._on_add()
