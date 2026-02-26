"""Environment editor dialog for managing environment variables.

Provides a modal dialog to create, rename, delete environments and
edit their key-value variable lists.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from services.environment_service import EnvironmentService
from ui.key_value_table import KeyValueTableWidget
from ui.theme import COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_TEXT, COLOR_WHITE


class EnvironmentEditorDialog(QDialog):
    """Modal dialog for managing environments and their variables.

    Signals:
        environments_changed(): Emitted when environments are created,
            renamed, deleted, or variables are modified.
    """

    environments_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the environment editor dialog."""
        super().__init__(parent)
        self.setWindowTitle("Manage Environments")
        self.setMinimumSize(700, 450)
        self.setModal(True)

        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # Left panel: environment list + add/delete buttons
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._env_list = QListWidget()
        self._env_list.setStyleSheet(
            f"QListWidget {{ border: 1px solid {COLOR_BORDER}; background: {COLOR_WHITE}; }}"
        )
        self._env_list.currentRowChanged.connect(self._on_env_selected)
        left_layout.addWidget(self._env_list, 1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setStyleSheet(
            f"background: {COLOR_ACCENT}; color: {COLOR_WHITE}; border: none;"
            f" padding: 4px 12px; border-radius: 3px;"
        )
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_btn)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setStyleSheet(
            f"background: {COLOR_DANGER}; color: {COLOR_WHITE}; border: none;"
            f" padding: 4px 12px; border-radius: 3px;"
        )
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # Right panel: name + key-value table
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        name_row = QHBoxLayout()
        name_label = QLabel("Name:")
        name_label.setStyleSheet(f"color: {COLOR_TEXT}; font-weight: bold;")
        name_row.addWidget(name_label)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Environment name")
        self._name_input.setStyleSheet(
            f"background: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER};"
            f" padding: 4px 8px; color: {COLOR_TEXT};"
        )
        self._name_input.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._name_input, 1)
        right_layout.addLayout(name_row)

        self._var_table = KeyValueTableWidget(placeholder_key="Variable", placeholder_value="Value")
        self._var_table.data_changed.connect(self._on_vars_changed)
        right_layout.addWidget(self._var_table, 1)

        # Save button
        self._save_btn = QPushButton("Save Variables")
        self._save_btn.setStyleSheet(
            f"background: {COLOR_ACCENT}; color: {COLOR_WHITE}; border: none;"
            f" padding: 6px 16px; font-weight: bold; border-radius: 3px;"
        )
        self._save_btn.clicked.connect(self._on_save_vars)
        right_layout.addWidget(self._save_btn)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._current_env_id: int | None = None
        self._refresh_list()

    # -- Internal -------------------------------------------------------

    def _refresh_list(self) -> None:
        """Reload environments from the service layer."""
        self._env_list.blockSignals(True)
        try:
            self._env_list.clear()
            envs = EnvironmentService.fetch_all()
            for env in envs:
                item = QListWidgetItem(env["name"])
                item.setData(Qt.ItemDataRole.UserRole, env["id"])
                self._env_list.addItem(item)
        finally:
            self._env_list.blockSignals(False)

        if self._env_list.count() > 0:
            self._env_list.setCurrentRow(0)
        else:
            self._current_env_id = None
            self._name_input.clear()
            self._var_table.set_data([])

    def _on_env_selected(self, row: int) -> None:
        """Load the selected environment's variables."""
        item = self._env_list.item(row)
        if item is None:
            self._current_env_id = None
            self._name_input.clear()
            self._var_table.set_data([])
            return
        env_id = item.data(Qt.ItemDataRole.UserRole)
        self._current_env_id = env_id
        env = EnvironmentService.get_environment(env_id)
        if env is None:
            return
        self._name_input.setText(env.name)
        values = env.values or []
        rows: list[dict[str, Any]] = [
            {
                "key": v.get("key", ""),
                "value": v.get("value", ""),
                "description": v.get("description", ""),
                "enabled": v.get("enabled", True),
            }
            for v in values
        ]
        self._var_table.set_data(rows)

    def _on_add(self) -> None:
        """Create a new environment."""
        name = "New Environment"
        try:
            env = EnvironmentService.create_environment(name)
        except ValueError:
            return
        self._refresh_list()
        # Select the new environment
        for i in range(self._env_list.count()):
            item = self._env_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == env.id:
                self._env_list.setCurrentRow(i)
                break
        self.environments_changed.emit()

    def _on_delete(self) -> None:
        """Delete the selected environment."""
        if self._current_env_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete Environment",
            "Delete this environment? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        EnvironmentService.delete_environment(self._current_env_id)
        self._current_env_id = None
        self._refresh_list()
        self.environments_changed.emit()

    def _on_name_changed(self) -> None:
        """Rename the selected environment."""
        if self._current_env_id is None:
            return
        new_name = self._name_input.text().strip()
        if not new_name:
            return
        try:
            EnvironmentService.rename_environment(self._current_env_id, new_name)
        except ValueError:
            return
        # Update list item text
        current_item = self._env_list.currentItem()
        if current_item:
            current_item.setText(new_name)
        self.environments_changed.emit()

    def _on_vars_changed(self) -> None:
        """Mark variables as modified (auto-save on explicit save click)."""

    def _on_save_vars(self) -> None:
        """Persist the current variable table to the database."""
        if self._current_env_id is None:
            return
        env = EnvironmentService.get_environment(self._current_env_id)
        if env is None:
            return
        rows = self._var_table.get_data()
        values: list[dict[str, Any]] = [
            {
                "key": r.get("key", ""),
                "value": r.get("value", ""),
                "description": r.get("description", ""),
                "enabled": r.get("enabled", True),
            }
            for r in rows
        ]
        EnvironmentService.update_environment_values(self._current_env_id, values)
        self.environments_changed.emit()
