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
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from services.environment_service import LocalOverride, VariableDetail


class _ElidedLabel(QLabel):
    """QLabel that elides text with an ellipsis when space is tight."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text: str) -> None:
        """Store full text and trigger repaint."""
        self._full_text = text
        super().setText(text)

    def paintEvent(self, event: object) -> None:
        """Draw text with right-elision when it overflows."""
        painter = QPainter(self)
        fm = self.fontMetrics()
        elided = fm.elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            self.width(),
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignVCenter), elided)
        painter.end()


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
        row = QHBoxLayout()
        row.setContentsMargins(0, 8, 0, 4)
        row.setSpacing(6)

        dot = QLabel("\u2022")
        dot.setObjectName("sidebarSourceDot")
        dot.setProperty("varSource", source)
        dot.setFixedWidth(12)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(dot)

        label = QLabel(title)
        label.setObjectName("sidebarSectionLabel")
        row.addWidget(label)
        row.addStretch()

        self._content_layout.addLayout(row)

    def _add_variable_row(self, name: str, value: str) -> None:
        """Add a single key-value variable row."""
        row = QHBoxLayout()
        row.setContentsMargins(18, 2, 0, 2)
        row.setSpacing(12)

        key_label = _ElidedLabel(name)
        key_label.setObjectName("variableKeyLabel")
        key_label.setFixedWidth(120)
        key_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row.addWidget(key_label)

        val_label = _ElidedLabel(value)
        val_label.setObjectName("variableValueLabel")
        val_label.setToolTip(value)
        val_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        val_label.setMinimumWidth(0)
        row.addWidget(val_label, 1)

        self._content_layout.addLayout(row)

    def _add_separator(self) -> None:
        """Add a thin horizontal separator line."""
        sep = QLabel()
        sep.setObjectName("sidebarSeparator")
        sep.setFixedHeight(1)
        self._content_layout.addWidget(sep)
        self._content_layout.addWidget(sep)
