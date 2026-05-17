"""Environment editor — full widget for tabs plus optional modal dialog wrapper."""

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
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.environment_service import EnvironmentService
from ui.styling.icons import phi
from ui.styling.theme import COLOR_SOLID_BUTTON_FG
from ui.widgets.key_value_table import KeyValueTableWidget

# Internal margins around the editor surface (tab body + dialog content).
_ENV_EDITOR_MARGIN_PX = 12
# Cap the environment list column so the variable editor keeps more horizontal space.
_ENV_LIST_PANE_MAX_WIDTH_PX = 200

_INTRO_WHEN_ENVS = (
    "Each environment is a named group of key/value variables. When you send a request, "
    "{{variable}} placeholders in the URL, headers, body, and auth fields are replaced "
    "using the active environment (chosen in the left sidebar) plus any collection variables. "
    "Use this tab to create environments, rename them, and edit their variables; click "
    "Save variables after changing the table so changes are written to the database."
)
_INTRO_WHEN_EMPTY = (
    "You do not have any environments yet. Create one from the Environments section at the "
    "bottom of the left column (under Collections): use Manage to open this tab after the "
    "first environment exists, or Add there to create one. The name and variable editor on "
    "the right appears once at least one environment is available."
)


class EnvironmentEditorWidget(QWidget):
    """Full editor surface for environments and their variables (non-modal).

    Used as a main-window tab body: title, contextual intro, a narrow environment
    list with Add/Delete, and (once environments exist) the name + variable table
    editor on the right. With no environments, the editor is replaced by a
    placeholder that points users to the sidebar.

    Signals:
        environments_changed(): Emitted when environments are created,
            renamed, deleted, or variables are modified.
    """

    environments_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the splitter UI (list + detail)."""
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            _ENV_EDITOR_MARGIN_PX,
            _ENV_EDITOR_MARGIN_PX,
            _ENV_EDITOR_MARGIN_PX,
            _ENV_EDITOR_MARGIN_PX,
        )
        root.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 10)
        header_layout.setSpacing(6)
        title = QLabel("Environments")
        title.setObjectName("titleLabel")
        header_layout.addWidget(title)
        self._intro = QLabel(_INTRO_WHEN_EMPTY)
        self._intro.setObjectName("mutedLabel")
        self._intro.setWordWrap(True)
        header_layout.addWidget(self._intro)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left.setMaximumWidth(_ENV_LIST_PANE_MAX_WIDTH_PX)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self._env_list = QListWidget()
        self._env_list.currentRowChanged.connect(self._on_env_selected)
        left_layout.addWidget(self._env_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._add_btn = QPushButton("Add")
        self._add_btn.setIcon(phi("plus", color=COLOR_SOLID_BUTTON_FG))
        self._add_btn.setObjectName("primaryButton")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self._add_btn)

        self._del_btn = QPushButton("Delete")
        self._del_btn.setIcon(phi("trash", color=COLOR_SOLID_BUTTON_FG))
        self._del_btn.setObjectName("dangerButton")
        self._del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        self._right_stack = QStackedWidget()

        placeholder = QWidget()
        ph_layout = QVBoxLayout(placeholder)
        ph_layout.setContentsMargins(16, 24, 16, 16)
        ph_layout.addStretch(1)
        ph_title = QLabel("Nothing to edit yet")
        ph_title.setObjectName("emptyStateLabel")
        ph_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_title.setWordWrap(True)
        ph_layout.addWidget(ph_title)
        ph_body = QLabel(
            "Add an environment from the Environments section at the bottom of the left "
            "sidebar (under Collections). Use Manage or Add there first; when at least one "
            "environment exists, select it in the list on the left and the editor will appear "
            "here."
        )
        ph_body.setObjectName("mutedLabel")
        ph_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_body.setWordWrap(True)
        ph_layout.addWidget(ph_body)
        ph_layout.addStretch(2)
        self._right_stack.addWidget(placeholder)

        editor_page = QWidget()
        right_layout = QVBoxLayout(editor_page)
        right_layout.setContentsMargins(12, 0, 0, 0)
        right_layout.setSpacing(10)

        name_row = QHBoxLayout()
        name_label = QLabel("Name:")
        name_label.setObjectName("sectionLabel")
        name_label.setStyleSheet("font-weight: bold;")
        name_row.addWidget(name_label)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Environment name")
        self._name_input.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._name_input, 1)
        right_layout.addLayout(name_row)

        self._var_table = KeyValueTableWidget(
            placeholder_key="Variable",
            placeholder_value="Value",
            settings_profile="environment_vars",
        )
        self._var_table.data_changed.connect(self._on_vars_changed)
        right_layout.addWidget(self._var_table, 1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self._save_btn = QPushButton("Save Variables")
        self._save_btn.setIcon(phi("floppy-disk", color=COLOR_SOLID_BUTTON_FG, size=22))
        self._save_btn.setObjectName("environmentEditorSaveVarsButton")
        self._save_btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_vars)
        save_row.addWidget(self._save_btn)
        right_layout.addLayout(save_row)

        self._right_stack.addWidget(editor_page)
        splitter.addWidget(self._right_stack)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._current_env_id: int | None = None
        self._saved_var_rows: list[dict[str, Any]] = []
        self._refresh_list()

    def _sync_right_pane_and_intro(self) -> None:
        """Show the variable editor only when at least one environment exists."""
        has_envs = self._env_list.count() > 0
        self._right_stack.setCurrentIndex(1 if has_envs else 0)
        self._intro.setText(_INTRO_WHEN_ENVS if has_envs else _INTRO_WHEN_EMPTY)
        self._del_btn.setEnabled(has_envs and self._current_env_id is not None)

    def _normalized_var_rows(self) -> list[dict[str, Any]]:
        """Return variable rows in the same shape used for persist/compare."""
        rows = self._var_table.get_data()
        return [
            {
                "key": r.get("key", ""),
                "value": r.get("value", ""),
                "description": r.get("description", ""),
                "enabled": r.get("enabled", True),
            }
            for r in rows
        ]

    def _capture_var_snapshot(self) -> None:
        """Record the current table as the last-saved baseline for dirty checks."""
        self._saved_var_rows = self._normalized_var_rows()

    def _update_vars_save_enabled(self) -> None:
        """Enable **Save Variables** only when the table differs from the baseline."""
        if self._current_env_id is None:
            self._save_btn.setEnabled(False)
            return
        self._save_btn.setEnabled(self._normalized_var_rows() != self._saved_var_rows)

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
            self._capture_var_snapshot()
            self._update_vars_save_enabled()

        self._sync_right_pane_and_intro()

    def _on_env_selected(self, row: int) -> None:
        """Load the selected environment's variables."""
        item = self._env_list.item(row)
        if item is None:
            self._current_env_id = None
            self._name_input.clear()
            self._var_table.set_data([])
            self._capture_var_snapshot()
            self._update_vars_save_enabled()
            self._sync_right_pane_and_intro()
            return
        env_id = item.data(Qt.ItemDataRole.UserRole)
        self._current_env_id = env_id
        env = EnvironmentService.get_environment(env_id)
        if env is None:
            self._sync_right_pane_and_intro()
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
        self._capture_var_snapshot()
        self._update_vars_save_enabled()
        self._sync_right_pane_and_intro()

    def _on_add(self) -> None:
        """Create a new environment."""
        name = "New Environment"
        try:
            env = EnvironmentService.create_environment(name)
        except ValueError:
            return
        self._refresh_list()
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
        current_item = self._env_list.currentItem()
        if current_item:
            current_item.setText(new_name)
        self.environments_changed.emit()

    def _on_vars_changed(self) -> None:
        """Track unsaved variable edits."""
        self._update_vars_save_enabled()

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
        self._capture_var_snapshot()
        self._update_vars_save_enabled()
        self.environments_changed.emit()


class EnvironmentEditorDialog(QDialog):
    """Modal wrapper around :class:`EnvironmentEditorWidget` (tests, legacy)."""

    environments_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Wrap the shared editor widget in a modal dialog."""
        super().__init__(parent)
        self.setWindowTitle("Manage Environments")
        self.setMinimumSize(700, 450)
        self.setModal(True)
        self._body = EnvironmentEditorWidget(self)
        self._body.environments_changed.connect(self.environments_changed.emit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(
            _ENV_EDITOR_MARGIN_PX,
            _ENV_EDITOR_MARGIN_PX,
            _ENV_EDITOR_MARGIN_PX,
            _ENV_EDITOR_MARGIN_PX,
        )
        lay.addWidget(self._body, 1)

    @property
    def _env_list(self) -> QListWidget:
        """Alias for tests that reach into the list widget."""
        return self._body._env_list

    @property
    def _current_env_id(self) -> int | None:
        return self._body._current_env_id

    @_current_env_id.setter
    def _current_env_id(self, value: int | None) -> None:
        self._body._current_env_id = value

    def _refresh_list(self) -> None:
        self._body._refresh_list()

    def _on_add(self) -> None:
        self._body._on_add()
