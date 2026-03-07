"""Variable management mixin for the main window.

Provides ``_VariableControllerMixin`` with environment variable
refresh, update, local override, and unresolved-variable callbacks.
Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from services.environment_service import EnvironmentService

if TYPE_CHECKING:
    from services.environment_service import LocalOverride
    from ui.environments.environment_selector import EnvironmentSelector
    from ui.request.navigation.tab_manager import TabContext
    from ui.request.request_editor import RequestEditorWidget

logger = logging.getLogger(__name__)


class _VariableControllerMixin:
    """Mixin that manages variable maps and popup callbacks.

    Expects the host class to provide ``_tabs``, ``_env_selector``,
    ``_tab_bar``, ``request_widget``, and ``_current_tab_context()``.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _env_selector: EnvironmentSelector
    _tabs: dict[int, TabContext]

    def _current_tab_context(self) -> TabContext | None: ...

    def _refresh_variable_map(
        self,
        editor: RequestEditorWidget,
        request_id: int | None,
        local_overrides: dict[str, LocalOverride] | None = None,
    ) -> None:
        """Build the combined variable map and push it to *editor*.

        When *local_overrides* is provided (per-request overrides set
        via the variable popup), those entries are layered on top with
        ``is_local=True`` so the popup shows a **Local** badge while
        preserving the original source for the **Update** action.
        """
        env_id = self._env_selector.current_environment_id()
        variables = EnvironmentService.build_combined_variable_detail_map(env_id, request_id)

        # Layer per-request overrides on top
        if local_overrides:
            for key, override in local_overrides.items():
                variables[key] = {
                    "value": override["value"],
                    "source": override["original_source"],
                    "source_id": override["original_source_id"],
                    "is_local": True,
                }

        editor.set_variable_map(variables)

    def _on_environment_changed(self, _env_id: object) -> None:
        """Refresh variable maps in all open request editors."""
        from ui.widgets.variable_popup import VariablePopup

        VariablePopup.set_has_environment(self._env_selector.current_environment_id() is not None)
        for ctx in self._tabs.values():
            if ctx.tab_type != "folder":
                self._refresh_variable_map(ctx.editor, ctx.request_id, ctx.local_overrides)

    def _on_variable_updated(
        self,
        var_name: str,
        new_value: str,
        source: str,
        source_id: int,
    ) -> None:
        """Persist a variable edit from the popup and refresh all editors."""
        try:
            EnvironmentService.update_variable_value(source, source_id, var_name, new_value)
        except Exception:
            logger.exception("Failed to update variable %r", var_name)
            return

        # When a variable is globally updated, clear any local override
        # for the same key in the current tab.
        ctx = self._current_tab_context()
        if ctx is not None:
            ctx.local_overrides.pop(var_name, None)

        # Refresh variable maps in all open request editors
        for ctx in self._tabs.values():
            if ctx.tab_type != "folder":
                self._refresh_variable_map(ctx.editor, ctx.request_id, ctx.local_overrides)

    def _on_local_variable_override(
        self,
        var_name: str,
        new_value: str,
        source: str,
        source_id: int,
    ) -> None:
        """Store a per-request variable override from the popup.

        When the user edits a variable value in the popup and closes
        it without clicking **Update**, the new value is stored as a
        local override that applies only to the current request tab.
        """
        ctx = self._current_tab_context()
        if ctx is None or ctx.tab_type == "folder":
            return

        ctx.local_overrides[var_name] = {
            "value": new_value,
            "original_source": source,
            "original_source_id": source_id,
        }
        self._refresh_variable_map(ctx.editor, ctx.request_id, ctx.local_overrides)

    def _on_reset_local_override(self, var_name: str) -> None:
        """Remove a per-request variable override and refresh.

        Called when the user clicks **Reset** on a locally-overridden
        variable in the popup.
        """
        ctx = self._current_tab_context()
        if ctx is None or ctx.tab_type == "folder":
            return

        ctx.local_overrides.pop(var_name, None)
        self._refresh_variable_map(ctx.editor, ctx.request_id, ctx.local_overrides)

    def _on_add_unresolved_variable(
        self,
        var_name: str,
        value: str,
        target: str,
    ) -> None:
        """Create a new variable from an unresolved reference.

        *target* is ``"collection"`` or ``"environment"``.  For
        ``"collection"`` the variable is added to the current
        request's parent collection.  For ``"environment"`` it is
        added to the currently selected environment.
        """
        ctx = self._current_tab_context()

        if target == "collection":
            request_id = ctx.request_id if ctx else None
            if request_id is None:
                return
            from database.models.collections.collection_repository import \
                get_request_by_id

            req = get_request_by_id(request_id)
            if req is None:
                return
            EnvironmentService.add_variable("collection", req.collection_id, var_name, value)
        elif target == "environment":
            env_id = self._env_selector.current_environment_id()
            if env_id is None:
                return
            EnvironmentService.add_variable("environment", env_id, var_name, value)
        else:
            return

        # Refresh variable maps in all open request editors
        for tab_ctx in self._tabs.values():
            if tab_ctx.tab_type != "folder":
                self._refresh_variable_map(
                    tab_ctx.editor,
                    tab_ctx.request_id,
                    tab_ctx.local_overrides,
                )
