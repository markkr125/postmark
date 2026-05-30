"""Label widgets used by the wrapped request-tab deck."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ui.styling.icons import phi
from ui.local_scripts.script_filename import script_basename_from_stored, script_display_name
from ui.styling.language_icons import language_icon_pixmap, resolve_script_language
from ui.styling.theme import (
    BADGE_BORDER_RADIUS,
    BADGE_FONT_SIZE,
    BADGE_HEIGHT,
    BADGE_MIN_WIDTH,
    COLOR_DANGER,
    COLOR_SENDING,
    COLOR_WHITE,
    method_color,
    method_short_label,
)

_DEBUG_ICON_SIZE = 14
_DEBUG_ICON_ALIGN = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter

_DIRTY_BULLET = "\u2022 "


@dataclass(frozen=True)
class TabLayoutConfig:
    """Layout constants for request and folder tab labels."""

    tab_height: int
    label_width: int
    badge_width: int
    badge_height: int
    margins: tuple[int, int, int, int]
    spacing: int
    font_delta: int
    spinner_size: int


STANDARD_LAYOUT = TabLayoutConfig(
    tab_height=30,
    label_width=180,
    badge_width=BADGE_MIN_WIDTH,
    badge_height=BADGE_HEIGHT,
    margins=(4, 0, 4, 0),
    spacing=4,
    font_delta=-1,
    spinner_size=10,
)

COMPACT_LAYOUT = TabLayoutConfig(
    tab_height=26,
    label_width=148,
    badge_width=max(18, BADGE_MIN_WIDTH - 4),
    badge_height=max(16, BADGE_HEIGHT - 2),
    margins=(3, 0, 3, 0),
    spacing=3,
    font_delta=-2,
    spinner_size=9,
)


def layout_config(compact: bool) -> TabLayoutConfig:
    """Return the active layout config for tab labels."""
    return COMPACT_LAYOUT if compact else STANDARD_LAYOUT


def _debug_icon_glyph_size(badge_height: int) -> int:
    """Return the bug pixmap edge length for a tab row of *badge_height*."""
    return min(_DEBUG_ICON_SIZE, badge_height)


def _debug_tab_icon_pixmap(badge_height: int) -> QPixmap:
    """Red bug icon pixmap sized for tab label rows."""
    size = _debug_icon_glyph_size(badge_height)
    return phi("bug", color=COLOR_DANGER, size=size).pixmap(size, size)


def _make_debug_tab_icon_label(badge_height: int) -> QLabel:
    """Build a vertically centred red bug icon for an active debug session."""
    size = _debug_icon_glyph_size(badge_height)
    label = QLabel()
    label.setPixmap(_debug_tab_icon_pixmap(badge_height))
    label.setFixedSize(size, badge_height)
    label.setAlignment(_DEBUG_ICON_ALIGN)
    label.setContentsMargins(0, 0, 0, 0)
    label.setToolTip("Debug session active")
    label.hide()
    return label


def _refresh_debug_tab_icon(label: QLabel, badge_height: int) -> None:
    """Update pixmap and cell size after tab layout config changes."""
    size = _debug_icon_glyph_size(badge_height)
    label.setPixmap(_debug_tab_icon_pixmap(badge_height))
    label.setFixedSize(size, badge_height)


def _font_with_delta(label: QLabel, delta: int) -> None:
    """Apply a point-size delta to the given label font.

    Computed from the QApplication font, not the label's current font, so
    repeat calls are idempotent. Reading the current size compounded the
    delta on every settings/theme reapply.
    """
    font = label.font()
    app = QApplication.instance()
    base_size = app.font().pointSize() if isinstance(app, QApplication) else 10
    if base_size <= 0:
        base_size = 10
    font.setPointSize(max(8, base_size + delta))
    label.setFont(font)


class TabLabel(QWidget):
    """Custom request-tab label with a method badge and request name."""

    def __init__(
        self,
        method: str = "GET",
        name: str = "",
        *,
        is_preview: bool = False,
        is_dirty: bool = False,
        compact: bool = False,
        mark_modified: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the tab label with method badge and request name."""
        super().__init__(parent)

        self._layout = QHBoxLayout(self)
        self._config = layout_config(compact)
        self._layout.setContentsMargins(*self._config.margins)
        self._layout.setSpacing(self._config.spacing)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._badge = QLabel(method_short_label(method))
        self._badge.setObjectName("methodBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(self._config.badge_width, self._config.badge_height)
        self._apply_badge_color(method_color(method))
        self._layout.addWidget(self._badge, 0, _DEBUG_ICON_ALIGN)

        self._name_label = QLabel(name)
        self._name_label.setMaximumWidth(self._config.label_width)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        _font_with_delta(self._name_label, self._config.font_delta)
        self._layout.addWidget(self._name_label, 0, _DEBUG_ICON_ALIGN)

        self._method = method
        self._name = name
        self._display_name = name
        self._is_preview = is_preview
        self._is_dirty = is_dirty
        self._is_sending = False
        self._is_debugging = False
        self._mark_modified = mark_modified

        self._spinner = QLabel("\u25cf")
        self._spinner.setStyleSheet(
            f"color: {COLOR_SENDING}; font-size: {self._config.spinner_size}px; padding: 0;"
        )
        self._spinner.hide()
        self._layout.addWidget(self._spinner, 0, _DEBUG_ICON_ALIGN)

        self._debug_icon = _make_debug_tab_icon_label(self._config.badge_height)
        self._layout.addWidget(self._debug_icon, 0, _DEBUG_ICON_ALIGN)

        self._apply_style()

    def _apply_badge_color(self, color: str) -> None:
        """Set the badge background colour."""
        self._badge.setStyleSheet(
            f"background: {color}; color: {COLOR_WHITE};"
            f" font-size: {BADGE_FONT_SIZE}px; font-weight: bold;"
            f" border-radius: {BADGE_BORDER_RADIUS}px;"
            f" font-family: monospace;"
        )

    def set_method(self, method: str) -> None:
        """Update the method badge."""
        self._method = method
        self._badge.setText(method_short_label(method))
        self._apply_badge_color(method_color(method))

    def set_name(self, name: str) -> None:
        """Update the request name."""
        self._name = name
        self._display_name = name
        self._apply_style()

    def set_display_name(self, name: str) -> None:
        """Update the rendered request name without changing the base name."""
        self._display_name = name
        self._apply_style()

    def set_preview(self, preview: bool) -> None:
        """Toggle the preview style."""
        self._is_preview = preview
        self._apply_style()

    def set_dirty(self, dirty: bool) -> None:
        """Toggle the dirty marker."""
        self._is_dirty = dirty
        self._apply_style()

    def set_sending(self, sending: bool) -> None:
        """Toggle the sending indicator."""
        self._is_sending = sending
        self._spinner.setVisible(sending)

    def set_debugging(self, debugging: bool) -> None:
        """Toggle the active-debug-session bug icon."""
        self._is_debugging = debugging
        self._debug_icon.setVisible(debugging)

    def apply_config(self, *, compact: bool, mark_modified: bool) -> None:
        """Apply refreshed display config from the tab settings."""
        self._config = layout_config(compact)
        self._mark_modified = mark_modified
        self._layout.setContentsMargins(*self._config.margins)
        self._layout.setSpacing(self._config.spacing)
        self._badge.setFixedSize(self._config.badge_width, self._config.badge_height)
        self._name_label.setMaximumWidth(self._config.label_width)
        _font_with_delta(self._name_label, self._config.font_delta)
        self._spinner.setStyleSheet(
            f"color: {COLOR_SENDING}; font-size: {self._config.spinner_size}px; padding: 0;"
        )
        _refresh_debug_tab_icon(self._debug_icon, self._config.badge_height)
        self._apply_style()

    def _apply_style(self) -> None:
        """Rebuild the display text and font style."""
        prefix = _DIRTY_BULLET if self._is_dirty and self._mark_modified else ""
        full_text = f"{prefix}{self._display_name}"
        metrics = QFontMetrics(self._name_label.font())
        self._name_label.setText(
            metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, self._config.label_width)
        )
        font = self._name_label.font()
        font.setItalic(self._is_preview)
        self._name_label.setFont(font)


class ScriptTabLabel(QWidget):
    """Local-script tab label with a brand language icon and script name."""

    def __init__(
        self,
        language: str = "javascript",
        name: str = "",
        *,
        is_dirty: bool = False,
        compact: bool = False,
        mark_modified: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the script tab label."""
        super().__init__(parent)

        self._layout = QHBoxLayout(self)
        self._config = layout_config(compact)
        self._layout.setContentsMargins(*self._config.margins)
        self._layout.setSpacing(self._config.spacing)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._icon_label = QLabel()
        self._language = resolve_script_language(language)
        self._apply_language_icon()
        self._icon_label.setFixedSize(self._config.badge_height, self._config.badge_height)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._icon_label, 0, _DEBUG_ICON_ALIGN)

        self._name_label = QLabel(name)
        self._name_label.setMaximumWidth(self._config.label_width)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        _font_with_delta(self._name_label, self._config.font_delta)
        self._layout.addWidget(self._name_label, 0, _DEBUG_ICON_ALIGN)

        self._basename = script_basename_from_stored(name)
        self._name = self._basename
        self._module_format = "esm"
        self._display_name = script_display_name(
            self._basename, self._language, self._module_format
        )
        self._is_dirty = is_dirty
        self._is_debugging = False
        self._mark_modified = mark_modified

        self._debug_icon = _make_debug_tab_icon_label(self._config.badge_height)
        self._layout.addWidget(self._debug_icon, 0, _DEBUG_ICON_ALIGN)

        self._apply_style()

    def _apply_language_icon(self) -> None:
        """Refresh the brand icon pixmap for the current language."""
        size = self._config.badge_height
        self._icon_label.setPixmap(language_icon_pixmap(self._language, size=size))

    def _refresh_display_name(self) -> None:
        """Recompute the tab label from basename, language, and module format."""
        self._display_name = script_display_name(
            self._basename, self._language, self._module_format
        )

    def set_debugging(self, debugging: bool) -> None:
        """Toggle the active-debug-session bug icon."""
        self._is_debugging = debugging
        self._debug_icon.setVisible(debugging)

    def set_language(self, language: str) -> None:
        """Update the language brand icon and tab title extension."""
        self._language = resolve_script_language(language)
        self._apply_language_icon()
        self._refresh_display_name()
        self._apply_style()

    def set_module_format(self, module_format: str) -> None:
        """Update the virtual file extension (``.js`` vs ``.cjs``)."""
        self._module_format = module_format or "esm"
        self._refresh_display_name()
        self._apply_style()

    def set_name(self, name: str) -> None:
        """Update the script basename (tab shows ``name`` + extension)."""
        self._basename = script_basename_from_stored(name)
        self._name = self._basename
        self._refresh_display_name()
        self._apply_style()

    def set_display_name(self, name: str) -> None:
        """Update the rendered script name without changing the base name."""
        self._display_name = name
        self._apply_style()

    def set_dirty(self, dirty: bool) -> None:
        """Toggle the dirty marker."""
        self._is_dirty = dirty
        self._apply_style()

    def apply_config(self, *, compact: bool, mark_modified: bool) -> None:
        """Apply refreshed display config from the tab settings."""
        self._config = layout_config(compact)
        self._mark_modified = mark_modified
        self._layout.setContentsMargins(*self._config.margins)
        self._layout.setSpacing(self._config.spacing)
        self._icon_label.setFixedSize(self._config.badge_height, self._config.badge_height)
        self._name_label.setMaximumWidth(self._config.label_width)
        _font_with_delta(self._name_label, self._config.font_delta)
        self._apply_language_icon()
        _refresh_debug_tab_icon(self._debug_icon, self._config.badge_height)
        self._apply_style()

    def _apply_style(self) -> None:
        """Rebuild the display text from the current state."""
        prefix = _DIRTY_BULLET if self._is_dirty and self._mark_modified else ""
        full_text = f"{prefix}{self._display_name}"
        metrics = QFontMetrics(self._name_label.font())
        self._name_label.setText(
            metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, self._config.label_width)
        )


class FolderTabLabel(QWidget):
    """Custom folder-tab label with icon and folder name."""

    def __init__(
        self,
        name: str = "",
        *,
        is_dirty: bool = False,
        compact: bool = False,
        mark_modified: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the folder-tab label."""
        super().__init__(parent)

        self._layout = QHBoxLayout(self)
        self._config = layout_config(compact)
        self._layout.setContentsMargins(*self._config.margins)
        self._layout.setSpacing(self._config.spacing)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._icon_label = QLabel()
        icon = phi("folder-simple")
        self._icon_label.setPixmap(
            icon.pixmap(self._config.badge_height, self._config.badge_height)
        )
        self._icon_label.setFixedSize(self._config.badge_width, self._config.badge_height)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._icon_label, 0, _DEBUG_ICON_ALIGN)

        self._name_label = QLabel(name)
        self._name_label.setMaximumWidth(self._config.label_width)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        _font_with_delta(self._name_label, self._config.font_delta)
        self._layout.addWidget(self._name_label, 0, _DEBUG_ICON_ALIGN)

        self._name = name
        self._display_name = name
        self._is_dirty = is_dirty
        self._is_debugging = False
        self._mark_modified = mark_modified

        self._debug_icon = _make_debug_tab_icon_label(self._config.badge_height)
        self._layout.addWidget(self._debug_icon, 0, _DEBUG_ICON_ALIGN)

        self._apply_style()

    def set_name(self, name: str) -> None:
        """Update the folder name."""
        self._name = name
        self._display_name = name
        self._apply_style()

    def set_display_name(self, name: str) -> None:
        """Update the rendered folder name without changing the base name."""
        self._display_name = name
        self._apply_style()

    def set_dirty(self, dirty: bool) -> None:
        """Toggle the dirty marker."""
        self._is_dirty = dirty
        self._apply_style()

    def set_debugging(self, debugging: bool) -> None:
        """Toggle the active-debug-session bug icon."""
        self._is_debugging = debugging
        self._debug_icon.setVisible(debugging)

    def apply_config(self, *, compact: bool, mark_modified: bool) -> None:
        """Apply refreshed display config from the tab settings."""
        self._config = layout_config(compact)
        self._mark_modified = mark_modified
        self._layout.setContentsMargins(*self._config.margins)
        self._layout.setSpacing(self._config.spacing)
        icon = phi("folder-simple")
        self._icon_label.setPixmap(
            icon.pixmap(self._config.badge_height, self._config.badge_height)
        )
        self._icon_label.setFixedSize(self._config.badge_width, self._config.badge_height)
        self._name_label.setMaximumWidth(self._config.label_width)
        _font_with_delta(self._name_label, self._config.font_delta)
        _refresh_debug_tab_icon(self._debug_icon, self._config.badge_height)
        self._apply_style()

    def _apply_style(self) -> None:
        """Rebuild the display text from the current state."""
        prefix = _DIRTY_BULLET if self._is_dirty and self._mark_modified else ""
        full_text = f"{prefix}{self._display_name}"
        metrics = QFontMetrics(self._name_label.font())
        self._name_label.setText(
            metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, self._config.label_width)
        )
