"""Tests for the ThemeManager singleton."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from ui.theme import DARK_PALETTE, LIGHT_PALETTE, current_palette
from ui.theme_manager import (
    _APP,
    _ORG,
    SCHEME_AUTO,
    SCHEME_DARK,
    SCHEME_LIGHT,
    STYLE_FUSION,
    STYLE_NATIVE,
    ThemeManager,
)


@pytest.fixture(autouse=True)
def _clear_theme_settings() -> None:
    """Clear persisted theme QSettings before each test."""
    settings = QSettings(_ORG, _APP)
    settings.remove("theme")
    settings.sync()


class TestThemeManagerConstruction:
    """Tests for ThemeManager initialisation."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """ThemeManager can be instantiated with a QApplication."""
        tm = ThemeManager(qapp)
        assert tm is not None

    def test_default_style_is_fusion(self, qapp: QApplication, qtbot) -> None:
        """Default widget style is Fusion."""
        tm = ThemeManager(qapp)
        assert tm.style == STYLE_FUSION

    def test_default_scheme_is_auto(self, qapp: QApplication, qtbot) -> None:
        """Default colour scheme is Auto-detect."""
        tm = ThemeManager(qapp)
        assert tm.scheme == SCHEME_AUTO


class TestThemeManagerProperties:
    """Tests for style and scheme property get/set."""

    def test_set_style(self, qapp: QApplication, qtbot) -> None:
        """Setting the style property persists the value."""
        tm = ThemeManager(qapp)
        tm.style = STYLE_NATIVE
        assert tm.style == STYLE_NATIVE

    def test_set_scheme_light(self, qapp: QApplication, qtbot) -> None:
        """Setting the scheme to Light persists the value."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_LIGHT
        assert tm.scheme == SCHEME_LIGHT

    def test_set_scheme_dark(self, qapp: QApplication, qtbot) -> None:
        """Setting the scheme to Dark persists the value."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_DARK
        assert tm.scheme == SCHEME_DARK


class TestThemeManagerApply:
    """Tests for the apply() method."""

    def test_apply_sets_palette(self, qapp: QApplication, qtbot) -> None:
        """Calling apply() sets the app palette to a QPalette."""
        tm = ThemeManager(qapp)
        tm.apply()
        pal = qapp.palette()
        assert isinstance(pal, QPalette)

    def test_apply_light_uses_light_palette(self, qapp: QApplication, qtbot) -> None:
        """Forcing Light scheme results in the LIGHT_PALETTE being active."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_LIGHT
        tm.apply()
        assert current_palette() is LIGHT_PALETTE

    def test_apply_dark_uses_dark_palette(self, qapp: QApplication, qtbot) -> None:
        """Forcing Dark scheme results in the DARK_PALETTE being active."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_DARK
        tm.apply()
        assert current_palette() is DARK_PALETTE

    def test_apply_emits_theme_changed(self, qapp: QApplication, qtbot) -> None:
        """apply() emits the theme_changed signal."""
        tm = ThemeManager(qapp)
        with qtbot.waitSignal(tm.theme_changed, timeout=1000):
            tm.apply()

    def test_apply_sets_stylesheet(self, qapp: QApplication, qtbot) -> None:
        """apply() sets a non-empty app stylesheet."""
        tm = ThemeManager(qapp)
        tm.apply()
        assert len(qapp.styleSheet()) > 0


class TestBuildQPalette:
    """Tests for the static _build_qpalette helper."""

    def test_returns_qpalette(self) -> None:
        """_build_qpalette returns a QPalette instance."""
        result = ThemeManager._build_qpalette(LIGHT_PALETTE)
        assert isinstance(result, QPalette)

    def test_window_color_matches_bg(self) -> None:
        """Window colour matches the palette 'bg' slot."""
        result = ThemeManager._build_qpalette(LIGHT_PALETTE)
        window_color = result.color(QPalette.ColorRole.Window).name()
        assert window_color == LIGHT_PALETTE["bg"]

    def test_accent_color_on_highlight(self) -> None:
        """Highlight colour matches the palette 'accent' slot."""
        result = ThemeManager._build_qpalette(DARK_PALETTE)
        highlight_color = result.color(QPalette.ColorRole.Highlight).name()
        assert highlight_color == DARK_PALETTE["accent"]


class TestBuildGlobalQSS:
    """Tests for the static _build_global_qss helper."""

    def test_returns_nonempty_string(self) -> None:
        """_build_global_qss returns a non-empty stylesheet string."""
        result = ThemeManager._build_global_qss(LIGHT_PALETTE)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_primary_button_selector(self) -> None:
        """Global QSS contains the primaryButton object-name selector."""
        result = ThemeManager._build_global_qss(LIGHT_PALETTE)
        assert 'objectName="primaryButton"' in result

    def test_contains_request_tab_bar_close_button(self) -> None:
        """Global QSS contains RequestTabBar close-button styling."""
        result = ThemeManager._build_global_qss(LIGHT_PALETTE)
        assert "RequestTabBar::close-button" in result

    def test_contains_accent_color(self) -> None:
        """Global QSS references the accent colour from the palette."""
        result = ThemeManager._build_global_qss(LIGHT_PALETTE)
        assert LIGHT_PALETTE["accent"] in result

    def test_dark_palette_uses_dark_bg(self) -> None:
        """Global QSS for DARK_PALETTE references dark background colour."""
        result = ThemeManager._build_global_qss(DARK_PALETTE)
        assert DARK_PALETTE["bg"] in result


class TestResolvePalette:
    """Tests for the _resolve_palette method."""

    def test_light_scheme_returns_light(self, qapp: QApplication, qtbot) -> None:
        """Scheme=Light always returns LIGHT_PALETTE."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_LIGHT
        assert tm._resolve_palette() is LIGHT_PALETTE

    def test_dark_scheme_returns_dark(self, qapp: QApplication, qtbot) -> None:
        """Scheme=Dark always returns DARK_PALETTE."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_DARK
        assert tm._resolve_palette() is DARK_PALETTE

    def test_auto_returns_a_valid_palette(self, qapp: QApplication, qtbot) -> None:
        """Scheme=Auto returns either LIGHT_PALETTE or DARK_PALETTE."""
        tm = ThemeManager(qapp)
        tm.scheme = SCHEME_AUTO
        result = tm._resolve_palette()
        assert result is LIGHT_PALETTE or result is DARK_PALETTE
