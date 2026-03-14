"""Tab settings manager — reads/writes QSettings for request-tab behaviour.

Instantiate once in ``main.py`` right after ``QApplication`` is created.
Widgets that render or manage request tabs subscribe to
``settings_changed`` and refresh themselves live when preferences change.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ui.styling.theme_manager import _APP, _ORG

_KEY_SMALL_LABELS = "tabs/small_labels"
_KEY_SHOW_PATH_FOR_DUPLICATES = "tabs/show_path_for_duplicates"
_KEY_MARK_MODIFIED = "tabs/mark_modified"
_KEY_SHOW_FULL_PATH_ON_HOVER = "tabs/show_full_path_on_hover"
_KEY_OPEN_NEW_AT_END = "tabs/open_new_at_end"
_KEY_ENABLE_PREVIEW = "tabs/enable_preview"
_KEY_TAB_LIMIT = "tabs/tab_limit"
_KEY_TAB_LIMIT_POLICY = "tabs/tab_limit_policy"
_KEY_ACTIVATE_ON_CLOSE = "tabs/activate_on_close"
_KEY_WRAP_MODE = "tabs/wrap_mode"

LIMIT_CLOSE_UNCHANGED = "close_unchanged"
LIMIT_CLOSE_UNUSED = "close_unused"
LIMIT_POLICIES = (LIMIT_CLOSE_UNCHANGED, LIMIT_CLOSE_UNUSED)

ACTIVATE_LEFT = "left"
ACTIVATE_RIGHT = "right"
ACTIVATE_MRU = "mru"
ACTIVATE_POLICIES = (ACTIVATE_LEFT, ACTIVATE_RIGHT, ACTIVATE_MRU)

WRAP_MULTIPLE_ROWS = "multiple_rows"
WRAP_SINGLE_ROW = "single_row"
WRAP_MODES = (WRAP_MULTIPLE_ROWS, WRAP_SINGLE_ROW)

MIN_TAB_LIMIT = 1
MAX_TAB_LIMIT = 100
DEFAULT_TAB_LIMIT = 30


def _as_bool(value: object, default: bool) -> bool:
    """Return a stable bool from ``QSettings`` values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _clamp_tab_limit(value: object) -> int:
    """Clamp a configured tab limit into the supported range."""
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = DEFAULT_TAB_LIMIT
    return max(MIN_TAB_LIMIT, min(MAX_TAB_LIMIT, parsed))


class TabSettingsManager(QObject):
    """Singleton-style manager for persisted request-tab preferences."""

    settings_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise and immediately read the persisted tab settings."""
        super().__init__(parent)

        from PySide6.QtCore import QSettings

        self._settings = QSettings(_ORG, _APP)
        self._small_labels = _as_bool(self._settings.value(_KEY_SMALL_LABELS, True), True)
        self._show_path_for_duplicates = _as_bool(
            self._settings.value(_KEY_SHOW_PATH_FOR_DUPLICATES, True),
            True,
        )
        self._mark_modified = _as_bool(self._settings.value(_KEY_MARK_MODIFIED, True), True)
        self._show_full_path_on_hover = _as_bool(
            self._settings.value(_KEY_SHOW_FULL_PATH_ON_HOVER, True),
            True,
        )
        self._open_new_tabs_at_end = _as_bool(
            self._settings.value(_KEY_OPEN_NEW_AT_END, True), True
        )
        self._enable_preview_tab = _as_bool(self._settings.value(_KEY_ENABLE_PREVIEW, True), True)
        self._tab_limit = _clamp_tab_limit(self._settings.value(_KEY_TAB_LIMIT, DEFAULT_TAB_LIMIT))
        self._tab_limit_policy = self._read_choice(
            _KEY_TAB_LIMIT_POLICY,
            LIMIT_CLOSE_UNUSED,
            LIMIT_POLICIES,
        )
        self._activate_on_close = self._read_choice(
            _KEY_ACTIVATE_ON_CLOSE,
            ACTIVATE_MRU,
            ACTIVATE_POLICIES,
        )
        self._wrap_mode = self._read_choice(
            _KEY_WRAP_MODE,
            WRAP_MULTIPLE_ROWS,
            WRAP_MODES,
        )

    def _read_choice(self, key: str, default: str, choices: tuple[str, ...]) -> str:
        """Read a string choice and fall back when an invalid value is stored."""
        value = str(self._settings.value(key, default))
        return value if value in choices else default

    def _set_and_emit(self, key: str, attr_name: str, value: object) -> None:
        """Persist a changed setting and notify listeners."""
        if getattr(self, attr_name) == value:
            return
        setattr(self, attr_name, value)
        self._settings.setValue(key, value)
        self.settings_changed.emit()

    @property
    def small_labels(self) -> bool:
        """Return whether tabs use the compact label treatment."""
        return self._small_labels

    @small_labels.setter
    def small_labels(self, value: bool) -> None:
        """Persist the compact-label preference."""
        self._set_and_emit(_KEY_SMALL_LABELS, "_small_labels", bool(value))

    @property
    def show_path_for_duplicates(self) -> bool:
        """Return whether duplicate tab names show a path suffix."""
        return self._show_path_for_duplicates

    @show_path_for_duplicates.setter
    def show_path_for_duplicates(self, value: bool) -> None:
        """Persist duplicate-name path disambiguation."""
        self._set_and_emit(
            _KEY_SHOW_PATH_FOR_DUPLICATES,
            "_show_path_for_duplicates",
            bool(value),
        )

    @property
    def mark_modified(self) -> bool:
        """Return whether modified requests show a dirty marker."""
        return self._mark_modified

    @mark_modified.setter
    def mark_modified(self, value: bool) -> None:
        """Persist dirty-indicator visibility."""
        self._set_and_emit(_KEY_MARK_MODIFIED, "_mark_modified", bool(value))

    @property
    def show_full_path_on_hover(self) -> bool:
        """Return whether the tab tooltip shows the full request path."""
        return self._show_full_path_on_hover

    @show_full_path_on_hover.setter
    def show_full_path_on_hover(self, value: bool) -> None:
        """Persist the full-path tooltip preference."""
        self._set_and_emit(
            _KEY_SHOW_FULL_PATH_ON_HOVER,
            "_show_full_path_on_hover",
            bool(value),
        )

    @property
    def open_new_tabs_at_end(self) -> bool:
        """Return whether new request tabs open at the end of the strip."""
        return self._open_new_tabs_at_end

    @open_new_tabs_at_end.setter
    def open_new_tabs_at_end(self, value: bool) -> None:
        """Persist the new-tab positioning preference."""
        self._set_and_emit(_KEY_OPEN_NEW_AT_END, "_open_new_tabs_at_end", bool(value))

    @property
    def enable_preview_tab(self) -> bool:
        """Return whether preview tabs are enabled."""
        return self._enable_preview_tab

    @enable_preview_tab.setter
    def enable_preview_tab(self, value: bool) -> None:
        """Persist the preview-tab preference."""
        self._set_and_emit(_KEY_ENABLE_PREVIEW, "_enable_preview_tab", bool(value))

    @property
    def tab_limit(self) -> int:
        """Return the maximum number of simultaneously open request tabs."""
        return self._tab_limit

    @tab_limit.setter
    def tab_limit(self, value: int) -> None:
        """Persist the configured request-tab limit."""
        self._set_and_emit(_KEY_TAB_LIMIT, "_tab_limit", _clamp_tab_limit(value))

    @property
    def tab_limit_policy(self) -> str:
        """Return the overflow policy used when the tab limit is exceeded."""
        return self._tab_limit_policy

    @tab_limit_policy.setter
    def tab_limit_policy(self, value: str) -> None:
        """Persist the limit-overflow policy."""
        choice = value if value in LIMIT_POLICIES else LIMIT_CLOSE_UNUSED
        self._set_and_emit(_KEY_TAB_LIMIT_POLICY, "_tab_limit_policy", choice)

    @property
    def activate_on_close(self) -> str:
        """Return the preferred tab-selection policy after closing the active tab."""
        return self._activate_on_close

    @activate_on_close.setter
    def activate_on_close(self, value: str) -> None:
        """Persist the close-activation policy."""
        choice = value if value in ACTIVATE_POLICIES else ACTIVATE_MRU
        self._set_and_emit(_KEY_ACTIVATE_ON_CLOSE, "_activate_on_close", choice)

    @property
    def wrap_mode(self) -> str:
        """Return the visual layout mode used by the request-tab deck."""
        return self._wrap_mode

    @wrap_mode.setter
    def wrap_mode(self, value: str) -> None:
        """Persist the request-tab wrap-mode preference."""
        choice = value if value in WRAP_MODES else WRAP_MULTIPLE_ROWS
        self._set_and_emit(_KEY_WRAP_MODE, "_wrap_mode", choice)
