"""Theme manager — reads/writes QSettings, builds QPalette + global QSS.

Instantiate once in ``main.py`` right after ``QApplication`` is created.
Connects to ``QStyleHints.colorSchemeChanged`` so the palette updates
live when the OS toggles light/dark mode.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from ui.styling.theme import DARK_PALETTE, LIGHT_PALETTE, ThemePalette, set_active_palette

logger = logging.getLogger(__name__)

# QSettings keys
_ORG = "Postmark"
_APP = "Postmark"
_KEY_STYLE = "theme/style"
_KEY_SCHEME = "theme/color_scheme"

# Supported style choices
STYLE_FUSION = "Fusion"
STYLE_NATIVE = "Native"
STYLES = (STYLE_FUSION, STYLE_NATIVE)

# Colour-scheme choices
SCHEME_AUTO = "Auto"
SCHEME_LIGHT = "Light"
SCHEME_DARK = "Dark"
SCHEMES = (SCHEME_AUTO, SCHEME_LIGHT, SCHEME_DARK)


def _detect_os_dark() -> bool:
    """Return ``True`` if the OS prefers a dark colour scheme."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return False
    try:
        hints = app.styleHints()
        scheme = hints.colorScheme()
        return bool(scheme == Qt.ColorScheme.Dark)
    except AttributeError:
        # PySide6 < 6.5 — fall back to palette heuristic
        bg = app.palette().color(QPalette.ColorRole.Window)
        return bool(bg.lightnessF() < 0.5)


class ThemeManager(QObject):
    """Singleton-style manager that applies style, palette, and global QSS.

    Signals:
        theme_changed(): Emitted after a theme switch so widgets can
            refresh dynamic styles (e.g. method badges).
    """

    theme_changed = Signal()

    def __init__(self, app: QApplication) -> None:
        """Initialise and immediately apply the persisted (or default) theme."""
        super().__init__(app)
        self._app = app

        # Import QSettings here to avoid early import issues
        from PySide6.QtCore import QSettings

        self._settings = QSettings(_ORG, _APP)

        # Read persisted values
        self._style: str = str(self._settings.value(_KEY_STYLE, STYLE_FUSION))
        self._scheme: str = str(self._settings.value(_KEY_SCHEME, SCHEME_AUTO))

        # Apply immediately
        self.apply()

        # Live OS theme tracking
        try:
            hints = app.styleHints()
            hints.colorSchemeChanged.connect(self._on_os_scheme_changed)
        except AttributeError:
            pass  # PySide6 < 6.5

    # -- Public API ----------------------------------------------------

    @property
    def style(self) -> str:
        """Return the current style name (``Fusion`` or ``Native``)."""
        return self._style

    @style.setter
    def style(self, value: str) -> None:
        """Set and persist the style name."""
        self._style = value
        self._settings.setValue(_KEY_STYLE, value)

    @property
    def scheme(self) -> str:
        """Return the current colour-scheme setting."""
        return self._scheme

    @scheme.setter
    def scheme(self, value: str) -> None:
        """Set and persist the colour-scheme preference."""
        self._scheme = value
        self._settings.setValue(_KEY_SCHEME, value)

    def apply(self) -> None:
        """Apply the current style, palette, and global QSS to the app."""
        # 1. Widget style
        if self._style == STYLE_NATIVE:
            native = QStyleFactory.keys()
            # Pick the first non-Fusion style, or fall back to Fusion
            preferred = [s for s in native if s.lower() != "fusion"]
            style_name = preferred[0] if preferred else STYLE_FUSION
            self._app.setStyle(style_name)
        else:
            self._app.setStyle(STYLE_FUSION)

        # 2. Resolve palette
        palette = self._resolve_palette()
        set_active_palette(palette)

        # 3. Build and apply QPalette
        qpal = self._build_qpalette(palette)
        self._app.setPalette(qpal)

        # 4. Build and apply global QSS
        from ui.styling.global_qss import build_global_qss

        qss = build_global_qss(palette)
        self._app.setStyleSheet(qss)

        # 5. Flush icon cache so colours are re-rendered
        from ui.styling.icons import clear_cache

        clear_cache()

        self.theme_changed.emit()

    # -- Internals -----------------------------------------------------

    def _resolve_palette(self) -> ThemePalette:
        """Choose the light or dark palette based on current scheme."""
        if self._scheme == SCHEME_DARK:
            return DARK_PALETTE
        if self._scheme == SCHEME_LIGHT:
            return LIGHT_PALETTE
        # Auto — detect from OS
        return DARK_PALETTE if _detect_os_dark() else LIGHT_PALETTE

    def _on_os_scheme_changed(self) -> None:
        """Re-apply theme when the OS colour scheme changes."""
        if self._scheme == SCHEME_AUTO:
            self.apply()

    @staticmethod
    def _build_qpalette(p: ThemePalette) -> QPalette:
        """Construct a QPalette from the given theme palette."""
        qpal = QPalette()
        qpal.setColor(QPalette.ColorRole.Window, QColor(p["bg"]))
        qpal.setColor(QPalette.ColorRole.WindowText, QColor(p["text"]))
        qpal.setColor(QPalette.ColorRole.Base, QColor(p["input_bg"]))
        qpal.setColor(QPalette.ColorRole.AlternateBase, QColor(p["bg_alt"]))
        qpal.setColor(QPalette.ColorRole.Text, QColor(p["text"]))
        qpal.setColor(QPalette.ColorRole.Button, QColor(p["bg"]))
        qpal.setColor(QPalette.ColorRole.ButtonText, QColor(p["text"]))
        qpal.setColor(QPalette.ColorRole.Highlight, QColor(p["accent"]))
        qpal.setColor(QPalette.ColorRole.HighlightedText, QColor(p["bg"]))
        qpal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["bg_alt"]))
        qpal.setColor(QPalette.ColorRole.ToolTipText, QColor(p["text"]))
        qpal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["text_muted"]))
        qpal.setColor(QPalette.ColorRole.Mid, QColor(p["border"]))
        qpal.setColor(QPalette.ColorRole.Dark, QColor(p["border"]))
        qpal.setColor(QPalette.ColorRole.Light, QColor(p["bg_alt"]))

        # Disabled group — muted colour
        qpal.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(p["text_muted"])
        )
        qpal.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p["text_muted"])
        )
        qpal.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(p["text_muted"])
        )
        return qpal
