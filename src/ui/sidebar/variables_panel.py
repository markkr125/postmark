"""Variables panel for the right sidebar.

Displays resolved variables grouped by source (Environment, Collection,
Local Overrides) in a read-only list.  The panel accepts a
:class:`VariableDetail` map and optional :class:`LocalOverride` map,
groups entries by their ``source`` field, and renders them as
key-value rows under collapsible source headings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.sidebar._kv_list import DEFAULT_KV_KEY_WIDTH, add_kv_row, add_section_header, add_separator

if TYPE_CHECKING:
    from services.environment_service import LocalOverride, VariableDetail


class VariablesPanel(QWidget):
    """Read-only panel showing variables grouped by source.

    Sections are rendered for **Environment**, **Collection**, and
    **Local Overrides** (only when entries exist for each).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the variables panel with an empty state."""
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable content area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(self._scroll)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 8, 12, 8)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)

        self._show_empty_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_variables(
        self,
        variables: dict[str, VariableDetail],
        local_overrides: dict[str, LocalOverride] | None = None,
        has_environment: bool = True,
    ) -> None:
        """Populate the panel with variable data grouped by source.

        *variables* maps variable names to their resolved metadata.
        *local_overrides* are per-request overrides (shown separately).
        *has_environment* controls whether the environment header is
        shown or a 'No environment selected' hint appears.
        """
        self._clear_content()

        # Group variables by source
        env_vars: list[tuple[str, str]] = []
        coll_vars: list[tuple[str, str]] = []
        for name, detail in sorted(variables.items()):
            if detail.get("is_local"):
                continue  # handled via local_overrides
            if detail["source"] == "environment":
                env_vars.append((name, detail["value"]))
            elif detail["source"] == "collection":
                coll_vars.append((name, detail["value"]))

        local_vars: list[tuple[str, str]] = []
        if local_overrides:
            for name, override in sorted(local_overrides.items()):
                local_vars.append((name, override["value"]))

        has_any = bool(env_vars or coll_vars or local_vars)

        # 1. Environment section
        if not has_environment:
            hint = QLabel("No environment selected. Select environment")
            hint.setObjectName("emptyStateLabel")
            hint.setWordWrap(True)
            self._content_layout.addWidget(hint)
            self._add_separator()
        elif env_vars:
            self._add_section("Environment", "environment", env_vars)
        else:
            self._add_section_header("Environment", "environment")
            empty = QLabel("No variables")
            empty.setObjectName("mutedLabel")
            self._content_layout.addWidget(empty)
            self._add_separator()

        # 2. Collection section
        if coll_vars:
            self._add_section("Requests collection", "collection", coll_vars)
        elif has_any or not has_environment:
            self._add_section_header("Requests collection", "collection")
            empty = QLabel("No variables")
            empty.setObjectName("mutedLabel")
            self._content_layout.addWidget(empty)
            self._add_separator()

        # 3. Local overrides section (only when entries exist)
        if local_vars:
            self._add_section("Local overrides", "local", local_vars)

        if not has_any and has_environment:
            self._show_empty_state()
            return

        self._content_layout.addStretch()

    def clear(self) -> None:
        """Reset the panel to its empty state."""
        self._clear_content()
        self._show_empty_state()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _clear_content(self) -> None:
        """Remove all widgets and sub-layouts from the content layout."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                continue
            sub = item.layout()
            if sub is not None:
                self._clear_layout(sub)

    @staticmethod
    def _clear_layout(layout: object) -> None:
        """Recursively delete all items in a sub-layout."""
        from PySide6.QtWidgets import QLayout

        if not isinstance(layout, QLayout):
            return
        while layout.count():
            child = layout.takeAt(0)
            if child is None:
                continue
            w = child.widget()
            if w is not None:
                w.setParent(None)
            else:
                VariablesPanel._clear_layout(child.layout())

    def _show_empty_state(self) -> None:
        """Display an empty-state label when no variables are available."""
        label = QLabel("No variables available")
        label.setObjectName("emptyStateLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.addWidget(label)
        self._content_layout.addStretch()

    def _add_section(
        self,
        title: str,
        source: str,
        variables: list[tuple[str, str]],
    ) -> None:
        """Add a source section with header and variable rows."""
        self._add_section_header(title, source)
        for name, value in variables:
            self._add_variable_row(name, value)
        self._add_separator()

    def _add_section_header(self, title: str, source: str) -> None:
        """Add a section header with a colored source dot and title."""
        add_section_header(self._content_layout, title, source)

    def _add_variable_row(self, name: str, value: str) -> None:
        """Add a single key-value variable row."""
        add_kv_row(self._content_layout, name, value, tooltip=value, key_width=DEFAULT_KV_KEY_WIDTH)

    def _add_separator(self) -> None:
        """Add a thin horizontal separator line."""
        add_separator(self._content_layout)
