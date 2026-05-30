"""Tab activation back/forward stacks for :class:`MainWindow`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QAction

    from ui.request.navigation.request_tab_bar import RequestTabBar
    from ui.request.navigation.tab_manager import TabContext

_TAB_NAV_MAX = 50


class _TabNavHistoryMixin:
    """Mixin tracking recently activated tabs (all tab types).

    Expects ``_tabs``, ``_deferred_tabs``, ``_tab_bar``, ``_restoring_session``,
    and ``tab_back_action`` / ``tab_forward_action`` on the host window.
    """

    if TYPE_CHECKING:
        _tabs: dict[int, TabContext]
        _deferred_tabs: dict[int, dict]
        _tab_bar: RequestTabBar
        _restoring_session: bool
        tab_back_action: QAction
        tab_forward_action: QAction

    _tab_nav_back: list[int]
    _tab_nav_forward: list[int]
    _tab_nav_current: int | None
    _tab_nav_from_history: bool

    def _init_tab_activation_history(self) -> None:
        """Reset tab activation stacks (call from ``MainWindow.__init__``)."""
        self._tab_nav_back = []
        self._tab_nav_forward = []
        self._tab_nav_current = None
        self._tab_nav_from_history = False

    @staticmethod
    def _append_tab_nav_stack(stack: list[int], token: int) -> None:
        """Append *token* and trim the stack to ``_TAB_NAV_MAX`` entries."""
        stack.append(token)
        if len(stack) > _TAB_NAV_MAX:
            del stack[: len(stack) - _TAB_NAV_MAX]

    def _tab_nav_token_for_index(self, index: int) -> int | None:
        """Return the navigation token for a tab-bar index, if known."""
        ctx = self._tabs.get(index)
        if ctx is not None:
            return ctx.nav_token
        info = self._deferred_tabs.get(index)
        if info is None:
            return None
        raw = info.get("nav_token")
        return raw if isinstance(raw, int) else None

    def _index_for_nav_token(self, token: int) -> int | None:
        """Resolve a navigation token to the current tab-bar index."""
        for idx, ctx in self._tabs.items():
            if ctx.nav_token == token:
                return idx
        for idx, info in self._deferred_tabs.items():
            if info.get("nav_token") == token:
                return idx
        return None

    def _record_tab_activation(self, index: int) -> None:
        """Push the previous tab onto the back stack when the active tab changes."""
        if getattr(self, "_restoring_session", False) or self._tab_nav_from_history:
            return
        token = self._tab_nav_token_for_index(index)
        if token is None or token == self._tab_nav_current:
            return
        if self._tab_nav_current is not None:
            self._append_tab_nav_stack(self._tab_nav_back, self._tab_nav_current)
        self._tab_nav_forward.clear()
        self._tab_nav_current = token
        self._update_tab_nav_actions()

    def _navigate_tab_back(self) -> None:
        """Activate the previously activated tab."""
        while self._tab_nav_back:
            target = self._tab_nav_back.pop()
            idx = self._index_for_nav_token(target)
            if idx is None:
                continue
            if self._tab_nav_current is not None:
                self._append_tab_nav_stack(self._tab_nav_forward, self._tab_nav_current)
            self._tab_nav_current = target
            self._tab_nav_from_history = True
            try:
                self._tab_bar.setCurrentIndex(idx)
            finally:
                self._tab_nav_from_history = False
            self._update_tab_nav_actions()
            return
        self._update_tab_nav_actions()

    def _navigate_tab_forward(self) -> None:
        """Re-activate a tab left via :meth:`_navigate_tab_back`."""
        while self._tab_nav_forward:
            target = self._tab_nav_forward.pop()
            idx = self._index_for_nav_token(target)
            if idx is None:
                continue
            if self._tab_nav_current is not None:
                self._append_tab_nav_stack(self._tab_nav_back, self._tab_nav_current)
            self._tab_nav_current = target
            self._tab_nav_from_history = True
            try:
                self._tab_bar.setCurrentIndex(idx)
            finally:
                self._tab_nav_from_history = False
            self._update_tab_nav_actions()
            return
        self._update_tab_nav_actions()

    def _purge_tab_nav_token(self, token: int) -> None:
        """Remove *token* from activation stacks when its tab closes."""
        self._tab_nav_back = [t for t in self._tab_nav_back if t != token]
        self._tab_nav_forward = [t for t in self._tab_nav_forward if t != token]
        if self._tab_nav_current == token:
            self._tab_nav_current = None
        self._update_tab_nav_actions()

    def _seed_tab_nav_after_restore(self) -> None:
        """Seed current token after session restore; leave stacks empty."""
        self._tab_nav_back.clear()
        self._tab_nav_forward.clear()
        idx = self._tab_bar.currentIndex()
        if idx >= 0:
            self._tab_nav_current = self._tab_nav_token_for_index(idx)
        else:
            self._tab_nav_current = None
        self._update_tab_nav_actions()

    def _update_tab_nav_actions(self) -> None:
        """Enable tab Back/Forward when the activation stacks allow navigation."""
        self.tab_back_action.setEnabled(len(self._tab_nav_back) > 0)
        self.tab_forward_action.setEnabled(len(self._tab_nav_forward) > 0)
