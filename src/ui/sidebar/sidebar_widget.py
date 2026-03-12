"""Postman-style right sidebar with icon rail and flyout panel.

The sidebar consists of two widgets placed as **separate children** in
the parent ``QSplitter``:

- :class:`_FlyoutPanel` — collapsible content area (variables /
  code-snippet).  The QSplitter enforces its ``minimumSizeHint`` so
  content is never crushed: dragging past the minimum snaps it to 0.
- :class:`RightSidebar` — the always-visible icon rail.

``RightSidebar`` owns the flyout and exposes the same public API as
before.  Call :pymethod:`install_in_splitter` after construction to
place both widgets into the target splitter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QLabel, QPushButton, QSizePolicy, QSplitter,
                               QToolButton, QVBoxLayout, QWidget)

from services.collection_service import SavedResponseDict
from ui.sidebar.saved_responses.panel import SavedResponsesPanel
from ui.sidebar.snippet_panel import SnippetPanel
from ui.sidebar.variables_panel import VariablesPanel
from ui.styling.icons import phi

if TYPE_CHECKING:
    from services.environment_service import LocalOverride, VariableDetail


# ------------------------------------------------------------------
# Flyout panel — separate splitter child
# ------------------------------------------------------------------
class _FlyoutPanel(QWidget):
    """Collapsible content panel placed as its own splitter child."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build title bar and all flyout content panels."""
        super().__init__(parent)
        self.setObjectName("sidebarPanelArea")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        em = self.fontMetrics().height()
        self._min_width: int = round(12.0 * em)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        from PySide6.QtWidgets import QHBoxLayout

        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(12, 8, 8, 4)
        title_bar.setSpacing(4)

        self.title_label = QLabel()
        self.title_label.setObjectName("sidebarTitleLabel")
        title_bar.addWidget(self.title_label)
        title_bar.addStretch()

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("iconButton")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setIcon(phi("x", size=16))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close panel")
        title_bar.addWidget(self.close_btn)

        layout.addLayout(title_bar)

        # Content panels
        self.variables_panel = VariablesPanel()
        self.snippet_panel = SnippetPanel()
        self.saved_responses_panel = SavedResponsesPanel()
        self.snippet_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.variables_panel, 1)
        layout.addWidget(self.snippet_panel, 1)
        layout.addWidget(self.saved_responses_panel, 1)
        self.variables_panel.hide()
        self.snippet_panel.hide()
        self.saved_responses_panel.hide()

    def minimumSizeHint(self) -> QSize:
        """Enforce a readable minimum width for the flyout."""
        return QSize(self._min_width, 0)


# ------------------------------------------------------------------
# Icon rail + controller
# ------------------------------------------------------------------
class RightSidebar(QWidget):
    """Always-visible icon rail that controls a flyout panel.

    After construction, call :pymethod:`install_in_splitter` to place
    both the flyout and the rail into the parent splitter.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the icon rail and create the flyout panel."""
        super().__init__(parent)
        self.setObjectName("sidebarRail")

        # Derive sizes from the application font.
        em = self.fontMetrics().height()
        self._rail_width: int = round(2.0 * em)
        self._icon_size: int = em
        self._btn_size: int = self._rail_width - round(0.35 * em)
        self._panel_hint_width: int = round(15.0 * em)

        self.setFixedWidth(self._rail_width)

        # --- Flyout (separate widget, placed in splitter later) -------
        self._flyout = _FlyoutPanel()
        self._close_btn = self._flyout.close_btn
        self._title_label = self._flyout.title_label
        self._variables_panel = self._flyout.variables_panel
        self._snippet_panel = self._flyout.snippet_panel
        self._saved_responses_panel = self._flyout.saved_responses_panel
        self._close_btn.clicked.connect(self._close_panel)

        # --- Rail layout ----------------------------------------------
        rail_layout = QVBoxLayout(self)
        rail_layout.setContentsMargins(0, 6, 0, 6)
        rail_layout.setSpacing(2)

        self._var_btn = self._make_rail_button(
            "brackets-curly",
            "Variables",
        )
        self._snippet_btn = self._make_rail_button("code", "Code snippet")
        self._saved_btn = self._make_rail_button("floppy-disk-back", "Saved responses")
        self._snippet_btn.hide()
        self._saved_btn.hide()
        rail_layout.addWidget(self._var_btn)
        rail_layout.addWidget(self._snippet_btn)
        rail_layout.addWidget(self._saved_btn)
        rail_layout.addStretch()

        # State
        self._active_panel: str | None = None
        self._last_panel: str | None = None
        self._available_panels: set[str] = set()
        self._default_panel: str | None = None
        self._splitter: QSplitter | None = None
        self._flyout_idx: int = -1

        # Wire rail buttons
        self._var_btn.clicked.connect(lambda: self._toggle_panel("variables"))
        self._snippet_btn.clicked.connect(
            lambda: self._toggle_panel("snippet"),
        )
        self._saved_btn.clicked.connect(
            lambda: self._toggle_panel("saved_responses"),
        )

    # Keep a reference for the ``_rail`` attribute used by tests.
    @property
    def _rail(self) -> QWidget:
        """Return self — the rail *is* this widget."""
        return self

    # ------------------------------------------------------------------
    # Splitter integration
    # ------------------------------------------------------------------
    def install_in_splitter(self, splitter: QSplitter) -> None:
        """Add the flyout and rail as children of *splitter*.

        Must be called **after** the content area has been added to
        the splitter so the flyout sits between content and rail.
        """
        self._splitter = splitter
        splitter.addWidget(self._flyout)
        self._flyout_idx = splitter.indexOf(self._flyout)
        splitter.addWidget(self)
        rail_idx = splitter.indexOf(self)

        # Flyout: collapsible (snap-to-close), no stretch.
        splitter.setCollapsible(self._flyout_idx, True)
        splitter.setStretchFactor(self._flyout_idx, 0)

        # Rail: fixed, non-collapsible, no stretch.
        splitter.setCollapsible(rail_idx, False)
        splitter.setStretchFactor(rail_idx, 0)

        # Hide the handle between flyout and rail — it's not useful
        # since the rail is fixed-width.
        rail_handle = splitter.handle(rail_idx)
        if rail_handle:
            rail_handle.setFixedWidth(0)
            rail_handle.setEnabled(False)

        # Start collapsed — flyout at 0 width.
        sizes = splitter.sizes()
        sizes[self._flyout_idx] = 0
        splitter.setSizes(sizes)

        # React when user drags the splitter handle.
        splitter.splitterMoved.connect(self._on_splitter_moved)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def variables_panel(self) -> VariablesPanel:
        """Return the variables panel widget."""
        return self._variables_panel

    @property
    def snippet_panel(self) -> SnippetPanel:
        """Return the snippet panel widget."""
        return self._snippet_panel

    @property
    def saved_responses_panel(self) -> SavedResponsesPanel:
        """Return the saved responses panel widget."""
        return self._saved_responses_panel

    @property
    def active_panel(self) -> str | None:
        """Return the key of the currently open panel, or *None*."""
        return self._active_panel

    @property
    def panel_open(self) -> bool:
        """Return whether any panel is currently visible."""
        return self._active_panel is not None

    def show_request_panels(
        self,
        variables: dict[str, VariableDetail],
        local_overrides: dict[str, LocalOverride] | None = None,
        has_environment: bool = True,
        *,
        method: str = "",
        url: str = "",
        headers: str | None = None,
        body: str | None = None,
        auth: dict | None = None,
    ) -> None:
        """Configure the sidebar for a request tab."""
        self._available_panels = {"variables", "snippet", "saved_responses"}
        self._default_panel = "snippet"
        self._var_btn.setEnabled(True)
        self._snippet_btn.show()
        self._snippet_btn.setEnabled(True)
        self._saved_btn.show()
        self._saved_btn.setEnabled(True)

        self._variables_panel.load_variables(
            variables,
            local_overrides=local_overrides,
            has_environment=has_environment,
        )
        self._snippet_panel.update_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            auth=auth,
        )

        if self._active_panel and self._active_panel not in self._available_panels:
            self._close_panel()

    def show_folder_panels(
        self,
        variables: dict[str, VariableDetail],
        has_environment: bool = True,
    ) -> None:
        """Configure the sidebar for a folder tab."""
        self._available_panels = {"variables"}
        self._default_panel = "variables"
        self._var_btn.setEnabled(True)
        self._snippet_btn.hide()
        self._saved_btn.hide()

        self._variables_panel.load_variables(
            variables,
            has_environment=has_environment,
        )

        if self._active_panel in {"snippet", "saved_responses"}:
            self._close_panel()

    def set_saved_response_context(
        self,
        *,
        request_id: int | None,
        request_name: str | None,
        items: list[SavedResponseDict],
        can_save_current: bool,
        is_persisted_request: bool,
    ) -> None:
        """Populate the saved responses panel for the active request context."""
        self._saved_btn.setVisible(True)
        self._saved_btn.setEnabled(is_persisted_request)
        self._saved_responses_panel.set_request_context(request_id, request_name)
        self._saved_responses_panel.set_live_response_available(can_save_current)
        if not is_persisted_request:
            if self._active_panel == "saved_responses":
                self._close_panel()
            self._saved_responses_panel.show_request_required_state(
                "Save the request first to store and browse saved responses."
            )
            return
        self._saved_responses_panel.set_saved_responses(items)

    def clear(self) -> None:
        """Reset the sidebar to an empty state (no tab open)."""
        self._available_panels = set()
        self._var_btn.setEnabled(False)
        self._snippet_btn.hide()
        self._saved_btn.hide()
        self._close_panel()
        self._variables_panel.clear()
        self._snippet_panel.clear()
        self._saved_responses_panel.clear()

    def open_panel(self, panel: str) -> None:
        """Programmatically open a specific panel by key."""
        if panel in self._available_panels:
            self._show_panel(panel)

    def open_default_panel(self) -> None:
        """Open the most relevant available panel for the current context."""
        panel = self._last_panel if self._last_panel in self._available_panels else None
        if panel is None:
            panel = self._default_panel
        if panel is not None:
            self._show_panel(panel)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _make_rail_button(self, icon_name: str, tooltip: str) -> QToolButton:
        """Create a single rail icon button."""
        btn = QToolButton()
        btn.setObjectName("sidebarRailButton")
        btn.setIcon(phi(icon_name, size=self._icon_size))
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(self._btn_size, self._btn_size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setEnabled(False)
        return btn

    def _toggle_panel(self, panel: str) -> None:
        """Toggle the given panel open or closed."""
        if self._active_panel == panel:
            self._close_panel()
        else:
            self._show_panel(panel)

    def _show_panel(self, panel: str) -> None:
        """Open *panel*, configuring the flyout content."""
        self._active_panel = panel
        self._last_panel = panel
        self._variables_panel.setVisible(panel == "variables")
        self._snippet_panel.setVisible(panel == "snippet")
        self._saved_responses_panel.setVisible(panel == "saved_responses")
        self._var_btn.setChecked(panel == "variables")
        self._snippet_btn.setChecked(panel == "snippet")
        self._saved_btn.setChecked(panel == "saved_responses")
        self._title_label.setText(
            "Variables"
            if panel == "variables"
            else "Code snippet"
            if panel == "snippet"
            else "Saved Responses",
        )
        self._flyout.show()
        self._expand_flyout()

    def _close_panel(self) -> None:
        """Collapse the flyout, keeping the icon rail visible."""
        self._active_panel = None
        self._variables_panel.hide()
        self._snippet_panel.hide()
        self._saved_responses_panel.hide()
        self._var_btn.setChecked(False)
        self._snippet_btn.setChecked(False)
        self._saved_btn.setChecked(False)
        self._collapse_flyout()

    def _expand_flyout(self) -> None:
        """Expand the flyout in the parent splitter via setSizes."""
        if not self._splitter or self._flyout_idx < 0:
            return
        sizes = self._splitter.sizes()
        if sizes[self._flyout_idx] >= self._panel_hint_width:
            return
        # Steal space from the content area (index 0).
        need = self._panel_hint_width - sizes[self._flyout_idx]
        give = min(need, sizes[0])
        sizes[0] -= give
        sizes[self._flyout_idx] += give
        self._splitter.setSizes(sizes)

    def _collapse_flyout(self) -> None:
        """Collapse the flyout in the parent splitter to 0."""
        if not self._splitter or self._flyout_idx < 0:
            return
        sizes = self._splitter.sizes()
        freed = sizes[self._flyout_idx]
        if freed <= 0:
            return
        sizes[0] += freed
        sizes[self._flyout_idx] = 0
        self._splitter.setSizes(sizes)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """React to the user dragging the splitter handle."""
        if not self._splitter or self._flyout_idx < 0:
            return
        flyout_width = self._splitter.sizes()[self._flyout_idx]

        if flyout_width == 0 and self._active_panel:
            # User collapsed the flyout by dragging.
            self._active_panel = None
            self._variables_panel.hide()
            self._snippet_panel.hide()
            self._saved_responses_panel.hide()
            self._var_btn.setChecked(False)
            self._snippet_btn.setChecked(False)
            self._saved_btn.setChecked(False)

        if flyout_width > 0 and not self._active_panel:
            # User expanded the flyout by dragging — open a panel.
            panel = self._last_panel
            if not panel or panel not in self._available_panels:
                panel = self._default_panel
            if panel:
                # Only configure content — don't call _expand_flyout
                # again since the user is already controlling the width.
                self._active_panel = panel
                self._last_panel = panel
                self._variables_panel.setVisible(panel == "variables")
                self._snippet_panel.setVisible(panel == "snippet")
                self._saved_responses_panel.setVisible(panel == "saved_responses")
                self._var_btn.setChecked(panel == "variables")
                self._snippet_btn.setChecked(panel == "snippet")
                self._saved_btn.setChecked(panel == "saved_responses")
                self._title_label.setText(
                    "Variables"
                    if panel == "variables"
                    else "Code snippet"
                    if panel == "snippet"
                    else "Saved Responses",
                )
                self._flyout.show()
