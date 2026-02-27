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

from ui.theme import (BADGE_BORDER_RADIUS, BADGE_FONT_SIZE, BADGE_HEIGHT,
                      BADGE_MIN_WIDTH, DARK_PALETTE, LIGHT_PALETTE,
                      TREE_ROW_HEIGHT, ThemePalette, set_active_palette)

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
        qss = self._build_global_qss(palette)
        self._app.setStyleSheet(qss)

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

    @staticmethod
    def _build_global_qss(p: ThemePalette) -> str:
        """Return the global stylesheet string for the entire application."""
        return f"""
        /* ---- Global resets ------------------------------------------ */
        QMainWindow, QDialog {{
            background: {p["bg"]};
            color: {p["text"]};
        }}

        /* ---- Splitters ---------------------------------------------- */
        QSplitter::handle {{
            background: {p["bg"]};
        }}
        QSplitter::handle:horizontal {{
            width: 5px;
            border-left: none;
            border-right: 1px solid {p["border"]};
        }}
        QSplitter::handle:vertical {{
            height: 1px;
            background: {p["border"]};
        }}

        /* ---- Labels ------------------------------------------------- */
        QLabel {{
            color: {p["text"]};
        }}
        QLabel[objectName="mutedLabel"] {{
            color: {p["text_muted"]};
            font-size: 11px;
        }}
        QLabel[objectName="emptyStateLabel"] {{
            color: {p["text_muted"]};
            font-style: italic;
            font-size: 13px;
        }}
        QLabel[objectName="titleLabel"] {{
            font-size: 14px;
            font-weight: bold;
            color: {p["text"]};
        }}
        QLabel[objectName="sectionLabel"] {{
            color: {p["text"]};
            font-size: 12px;
        }}
        QLabel[objectName="panelTitle"] {{
            font-weight: bold;
            font-size: 12px;
            color: {p["text"]};
            padding: 8px;
        }}

        /* ---- Inputs ------------------------------------------------- */
        QLineEdit, QComboBox {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            padding: 6px 10px;
            color: {p["text"]};
            border-radius: 4px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border-color: {p["accent"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 4px solid {p["text_muted"]};
            margin-right: 8px;
        }}

        /* ---- Text editors ------------------------------------------- */
        QTextEdit {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            color: {p["text"]};
            font-size: 12px;
        }}
        QTextEdit[objectName="monoEdit"] {{
            font-family: monospace;
        }}
        QTextEdit[objectName="consoleOutput"] {{
            background: {p["console_bg"]};
            color: {p["console_text"]};
            font-family: monospace;
            font-size: 11px;
            border: none;
        }}

        /* ---- Buttons ------------------------------------------------ */
        QPushButton[objectName="primaryButton"] {{
            background: {p["accent"]};
            color: {p["bg"]};
            border: none;
            padding: 6px 20px;
            font-weight: bold;
            border-radius: 4px;
        }}
        QPushButton[objectName="primaryButton"]:hover {{
            opacity: 0.85;
        }}
        QPushButton[objectName="dangerButton"] {{
            background: {p["danger"]};
            color: {p["bg"]};
            border: none;
            padding: 6px 20px;
            font-weight: bold;
            border-radius: 4px;
        }}
        QPushButton[objectName="dangerButton"]:hover {{
            opacity: 0.85;
        }}
        QPushButton[objectName="smallPrimaryButton"] {{
            background: {p["accent"]};
            color: {p["bg"]};
            border: none;
            padding: 4px 12px;
            font-size: 11px;
            border-radius: 4px;
        }}
        QPushButton[objectName="outlineButton"] {{
            border: 1px solid {p["border"]};
            padding: 4px 12px;
            font-size: 11px;
            border-radius: 4px;
            background: transparent;
            color: {p["text"]};
        }}
        QPushButton[objectName="linkButton"] {{
            color: {p["accent"]};
            border: none;
            font-size: 11px;
            padding: 8px;
            background: transparent;
        }}
        QPushButton[objectName="flatAccentButton"] {{
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 500;
            color: {p["accent"]};
            border: none;
            background: transparent;
            border-radius: 4px;
        }}
        QPushButton[objectName="flatAccentButton"]:hover {{
            background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.04)"};
        }}
        QPushButton[objectName="flatMutedButton"] {{
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 500;
            color: {p["text_muted"]};
            border: none;
            background: transparent;
            border-radius: 4px;
        }}
        QPushButton[objectName="flatMutedButton"]:hover {{
            background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.04)"};
            color: {p["text"]};
        }}
        QPushButton[objectName="importLinkButton"] {{
            color: {p["accent"]};
            text-decoration: underline;
            border: none;
            font-weight: bold;
            background: transparent;
        }}
        QPushButton[objectName="dismissButton"] {{
            padding: 6px 20px;
            border: 1px solid {p["border"]};
            border-radius: 4px;
            background: {p["bg_alt"]};
            font-weight: bold;
            color: {p["text"]};
        }}
        QPushButton[objectName="dismissButton"]:hover {{
            background: {p["border"]};
        }}

        /* ---- Tab bars (underline style) ----------------------------- */
        QTabWidget::pane {{
            border: 1px solid {p["border"]};
            border-top: none;
            background: {p["bg"]};
            border-radius: 0px;
        }}
        QTabWidget > QTabBar::tab {{
            padding: 8px 16px;
            color: {p["text_muted"]};
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            font-weight: 500;
        }}
        QTabWidget > QTabBar::tab:hover {{
            color: {p["text"]};
            background: {p["bg_alt"]};
        }}
        QTabWidget > QTabBar::tab:selected {{
            color: {p["accent"]};
            border-bottom: 2px solid {p["accent"]};
        }}

        /* ---- Progress bars ------------------------------------------ */
        QProgressBar {{
            border: none;
            background: transparent;
        }}
        QProgressBar::chunk {{
            background: {p["accent"]};
        }}

        /* ---- Table widgets ------------------------------------------ */
        QTableWidget {{
            background: {p["input_bg"]};
            border: 1px solid {p["border"]};
            gridline-color: {"rgba(0,0,0,0.05)" if p is LIGHT_PALETTE else "rgba(255,255,255,0.05)"};
            color: {p["text"]};
            border-radius: 4px;
        }}
        QHeaderView::section {{
            background: {p["bg_alt"]};
            border: none;
            border-bottom: 1px solid {p["border"]};
            border-right: 1px solid {"rgba(0,0,0,0.05)" if p is LIGHT_PALETTE else "rgba(255,255,255,0.05)"};
            padding: 6px 8px;
            font-size: 12px;
            font-weight: 500;
            color: {p["text_muted"]};
        }}

        /* ---- List widgets ------------------------------------------- */
        QListWidget {{
            border: 1px solid {p["border"]};
            background: {p["input_bg"]};
        }}

        /* ---- Scroll areas ------------------------------------------- */
        QScrollArea {{
            border: none;
        }}

        /* ---- Tree widgets ------------------------------------------- */
        QTreeWidget::item {{
            height: {TREE_ROW_HEIGHT}px;
            padding: 0px 0px;
        }}
        QTreeWidget::item:hover {{
            background-color: {p["hover_tree_bg"]};
        }}
        QTreeWidget::item:selected {{
            background-color: {p["selected_bg"]};
        }}

        /* ---- Request tab bar ---------------------------------------- */
        RequestTabBar {{
            border-bottom: 1px solid {p["border"]};
            background: {p["bg_alt"]};
        }}
        RequestTabBar::tab {{
            height: 34px;
            padding: 0 16px;
            border: none;
            border-right: 1px solid {p["border"]};
            background: {p["bg_alt"]};
            color: {p["text_muted"]};
        }}
        RequestTabBar::tab:selected {{
            background: {p["bg"]};
            color: {p["text"]};
            border-top: 2px solid {p["accent"]};
            border-bottom: none;
        }}
        RequestTabBar::tab:hover:!selected {{
            background: {"rgba(255,255,255,0.06)" if p is DARK_PALETTE else "rgba(0,0,0,0.04)"};
        }}
        RequestTabBar::close-button {{
            image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'><path d='M5 5l6 6m0-6l-6 6' stroke='{p["text_muted"].replace("#", "%23")}' stroke-width='1.5' stroke-linecap='round'/></svg>");
            subcontrol-position: right;
            margin: 4px;
            padding: 2px;
        }}
        RequestTabBar::close-button:hover {{
            background: {"rgba(255,255,255,0.15)" if p is DARK_PALETTE else "rgba(0,0,0,0.1)"};
            border-radius: 4px;
            image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'><path d='M5 5l6 6m0-6l-6 6' stroke='{p["text"].replace("#", "%23")}' stroke-width='1.5' stroke-linecap='round'/></svg>");
        }}

        /* ---- Menus -------------------------------------------------- */
        QMenu {{
            background: {p["bg"]};
            border: 1px solid {p["border"]};
            color: {p["text"]};
        }}
        QMenu::item {{
            padding: 4px 12px;
        }}
        QMenu::item:selected:enabled {{
            background-color: {p["accent"]};
            color: {p["bg"]};
        }}

        /* ---- Toolbar buttons ---------------------------------------- */
        QToolButton {{
            background: {p["bg"]};
        }}

        /* ---- Sidebar flat buttons ----------------------------------- */
        QToolButton[objectName="sidebarToolButton"] {{
            background: transparent;
            border: none;
            color: {p["accent"]};
            font-size: 12px;
            font-weight: 500;
            padding: 2px 8px;
            border-radius: 4px;
        }}
        QToolButton[objectName="sidebarToolButton"]:hover {{
            background: {"rgba(255,255,255,0.08)" if p is DARK_PALETTE else "rgba(0,0,0,0.06)"};
        }}

        /* ---- Sidebar section label ---------------------------------- */
        QLabel[objectName="sidebarSectionLabel"] {{
            font-weight: bold;
            font-size: 13px;
            color: {p["text"]};
        }}

        /* ---- Badge (method badge in tree + tabs) -------------------- */
        QLabel[objectName="methodBadge"] {{
            font-size: {BADGE_FONT_SIZE}px;
            font-weight: bold;
            font-family: monospace;
            border-radius: {BADGE_BORDER_RADIUS}px;
            min-width: {BADGE_MIN_WIDTH}px;
            max-width: {BADGE_MIN_WIDTH}px;
            min-height: {BADGE_HEIGHT}px;
            max-height: {BADGE_HEIGHT}px;
        }}

        /* ---- Import dialog drop zone ------------------------------- */
        _DropZone {{
            background: {p["drop_zone_bg"]};
            border: 2px dashed {p["drop_zone_border"]};
            border-radius: 8px;
        }}

        /* ---- Import dialog tab widget (box-style tabs) -------------- */
        QTabWidget[objectName="importTabs"]::pane {{
            border: 1px solid {p["border"]};
            border-top: none;
        }}
        QTabWidget[objectName="importTabs"] > QTabBar::tab {{
            padding: 6px 16px;
            border: 1px solid {p["border"]};
            border-bottom: none;
            background: {p["bg_alt"]};
        }}
        QTabWidget[objectName="importTabs"] > QTabBar::tab:selected {{
            background: {p["bg"]};
            font-weight: bold;
            border-bottom: none;
        }}
        """
