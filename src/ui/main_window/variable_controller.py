"""Variable and sidebar management mixin for the main window.

Provides ``_VariableControllerMixin`` with environment variable
refresh, update, local override, unresolved-variable callbacks, and
right-sidebar refresh logic.  Mixed into ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

from services.environment_service import EnvironmentService

if TYPE_CHECKING:
    from services.environment_service import LocalOverride
    from ui.environments.environment_selector import EnvironmentSelector
    from ui.request.navigation.request_tab_bar import RequestTabBar
    from ui.request.navigation.tab_manager import TabContext
    from ui.request.request_editor import RequestEditorWidget
    from ui.sidebar import RightSidebar

logger = logging.getLogger(__name__)


class _VariableControllerMixin:
    """Mixin that manages variable maps, popup callbacks, and sidebar.

    Expects the host class to provide ``_tabs``, ``_env_selector``,
    ``_tab_bar``, ``request_widget``, ``_right_sidebar``, and
    ``_current_tab_context()``.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _env_selector: EnvironmentSelector
    _tabs: dict[int, TabContext]
    _right_sidebar: RightSidebar
    _sidebar_debounce: QTimer
    _tab_bar: RequestTabBar

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
        self._refresh_sidebar()

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
            from database.models.collections.collection_query_repository import \
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
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    # Right-sidebar helpers
    # ------------------------------------------------------------------
    def _refresh_sidebar(self, ctx: TabContext | None = None) -> None:
        """Update the right sidebar panels for the active tab."""
        if ctx is None:
            ctx = self._current_tab_context()
        env_id = self._env_selector.current_environment_id()
        has_env = env_id is not None

        if ctx is None:
            self._right_sidebar.clear()
            return

        if ctx.tab_type == "folder":
            variables = EnvironmentService.build_combined_variable_detail_map(env_id, None)
            # Merge folder-level variables from the collection chain
            if ctx.collection_id is not None:
                from database.models.collections.collection_query_repository import \
                    get_collection_variable_chain_detailed

                for key, (value, coll_id) in get_collection_variable_chain_detailed(
                    ctx.collection_id
                ).items():
                    if key not in variables:
                        variables[key] = {
                            "value": value,
                            "source": "collection",
                            "source_id": coll_id,
                        }
            self._right_sidebar.show_folder_panels(variables, has_environment=has_env)
        else:
            variables = EnvironmentService.build_combined_variable_detail_map(
                env_id, ctx.request_id
            )
            # Layer per-request overrides on top
            if ctx.local_overrides:
                for key, override in ctx.local_overrides.items():
                    variables[key] = {
                        "value": override["value"],
                        "source": override["original_source"],
                        "source_id": override["original_source_id"],
                        "is_local": True,
                    }
            editor = ctx.editor
            data = editor.get_request_data()
            # Resolve {{variable}} placeholders for the snippet.
            flat_vars = {k: v["value"] for k, v in variables.items()}
            sub = EnvironmentService.substitute
            # Resolve inherited auth for sidebar / snippet display
            auth = data.get("auth")
            if auth is None and ctx.request_id:
                from services.collection_service import CollectionService

                auth = CollectionService.get_request_inherited_auth(ctx.request_id)
            auth = self._substitute_auth(auth, flat_vars)
            self._right_sidebar.show_request_panels(
                variables,
                local_overrides=ctx.local_overrides,
                has_environment=has_env,
                method=editor._method_combo.currentText(),
                url=sub(editor._url_input.text().strip(), flat_vars),
                headers=sub(editor.get_headers_text() or "", flat_vars) or None,
                body=sub(data.get("body") or "", flat_vars) or None,
                auth=auth,
            )
            request_name = None
            saved_responses = []
            is_persisted_request = ctx.request_id is not None
            if ctx.request_id is not None:
                from services.collection_service import CollectionService

                _, request_name = self._tab_bar.tab_request_info(self._tab_bar.currentIndex())
                saved_responses = CollectionService.get_saved_responses(ctx.request_id)
            self._right_sidebar.set_saved_response_context(
                request_id=ctx.request_id,
                request_name=request_name,
                items=saved_responses,
                can_save_current=ctx.response_viewer.has_live_response(),
                is_persisted_request=is_persisted_request,
            )

    def _schedule_sidebar_snippet_refresh(self) -> None:
        """Debounce snippet refresh (300 ms) on request editor changes."""
        self._sidebar_debounce.start(300)

    def _refresh_sidebar_snippet(self) -> None:
        """Regenerate only the snippet panel for the active request tab."""
        ctx = self._current_tab_context()
        if ctx is None or ctx.tab_type == "folder":
            return
        editor = ctx.editor
        data = editor.get_request_data()
        # Resolve {{variable}} placeholders for the snippet.
        env_id = self._env_selector.current_environment_id()
        variables = EnvironmentService.build_combined_variable_detail_map(env_id, ctx.request_id)
        if ctx.local_overrides:
            for key, override in ctx.local_overrides.items():
                variables[key] = {
                    "value": override["value"],
                    "source": override["original_source"],
                    "source_id": override["original_source_id"],
                    "is_local": True,
                }
        flat_vars = {k: v["value"] for k, v in variables.items()}
        sub = EnvironmentService.substitute
        auth = self._resolve_snippet_auth(data.get("auth"), ctx.request_id)
        auth = self._substitute_auth(auth, flat_vars)
        self._right_sidebar.snippet_panel.update_request(
            method=editor._method_combo.currentText(),
            url=sub(editor._url_input.text().strip(), flat_vars),
            headers=sub(editor.get_headers_text() or "", flat_vars) or None,
            body=sub(data.get("body") or "", flat_vars) or None,
            auth=auth,
        )

    @staticmethod
    def _substitute_auth(auth: dict | None, variables: dict[str, str]) -> dict | None:
        """Substitute ``{{variable}}`` placeholders in auth entry values."""
        if not auth or not variables:
            return auth
        auth_type = auth.get("type", "noauth")
        entries = auth.get(auth_type, [])
        if not entries:
            return auth
        sub = EnvironmentService.substitute
        substituted = dict(auth)
        substituted[auth_type] = [
            {**e, "value": sub(str(e.get("value", "")), variables)} if isinstance(e, dict) else e
            for e in entries
        ]
        return substituted

    def _resolve_snippet_auth(self, auth: dict | None, request_id: int | None) -> dict | None:
        """Return the effective auth for snippet generation.

        If the request uses "Inherit auth from parent" (``auth is None``)
        and has a saved request_id, resolve the inherited auth from the
        collection chain.
        """
        if auth is None and request_id:
            from services.collection_service import CollectionService

            return CollectionService.get_request_inherited_auth(request_id)
        return auth

    def _toggle_right_sidebar(self) -> None:
        """Toggle the right sidebar panel open or closed."""
        if self._right_sidebar.panel_open:
            self._right_sidebar._close_panel()
        else:
            ctx = self._current_tab_context()
            if ctx is None:
                return
            self._refresh_sidebar(ctx)
            self._right_sidebar.open_default_panel()

    def _on_snippet_shortcut(self) -> None:
        """Open the sidebar with the snippet panel visible."""
        self._right_sidebar.open_panel("snippet")
