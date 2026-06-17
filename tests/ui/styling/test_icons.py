"""Tests for the Phosphor icon provider (ui.icons)."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from ui.styling.icons import (
    chat_stop_icon,
    clear_cache,
    load_font,
    phi,
    phi_qss_image_url,
    square_filled_icon,
)


class TestLoadFont:
    """Tests for the font-loading bootstrap."""

    def test_load_font_succeeds(self, qapp) -> None:
        """load_font() should populate the font family and charmap."""
        load_font()
        # Second call is a no-op — should not raise
        load_font()

    def test_load_font_idempotent(self, qapp) -> None:
        """Calling load_font() multiple times does not raise."""
        load_font()
        load_font()
        load_font()


class TestPhi:
    """Tests for the phi() icon factory."""

    def test_returns_qicon(self, qapp) -> None:
        """phi() should return a QIcon instance."""
        icon = phi("arrow-left")
        assert isinstance(icon, QIcon)

    def test_unknown_name_returns_null_icon(self, qapp) -> None:
        """phi() returns a null QIcon for an unknown glyph name."""
        icon = phi("this-icon-does-not-exist")
        assert icon.isNull()

    def test_known_icon_not_null(self, qapp) -> None:
        """phi() returns a non-null QIcon for a valid glyph name."""
        icon = phi("trash")
        assert not icon.isNull()

    def test_custom_color_and_size(self, qapp) -> None:
        """phi() accepts color and size overrides."""
        icon = phi("plus", color="#ff0000", size=24)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_cache_returns_same_object(self, qapp) -> None:
        """Identical phi() calls should return the same cached QIcon."""
        a = phi("trash", color="#cccccc", size=16)
        b = phi("trash", color="#cccccc", size=16)
        assert a is b

    def test_different_params_return_different_icons(self, qapp) -> None:
        """Different size/color combos should produce distinct QIcon objects."""
        a = phi("trash", color="#cccccc", size=16)
        b = phi("trash", color="#ff0000", size=16)
        assert a is not b


class TestSquareFilledIcon:
    """Tests for the solid-square stop icon helper."""

    def test_returns_non_null_icon(self, qapp) -> None:
        """square_filled_icon() should return a painted QIcon."""
        icon = square_filled_icon(color="#ff0000", size=18)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_chat_stop_icon_matches_composer(self, qapp) -> None:
        """chat_stop_icon() should return the shared white stop square."""
        icon = chat_stop_icon()
        assert isinstance(icon, QIcon)
        assert not icon.isNull()


class TestPhiQssImageUrl:
    """Tests for stylesheet arrow PNG URLs."""

    def test_returns_postmark_qss_url(self, qapp) -> None:
        """phi_qss_image_url() should reference a cached PNG on disk."""
        load_font()
        url = phi_qss_image_url("caret-up", color="#112233", size=8)
        assert url.startswith("url(postmark-qss:")
        assert url.endswith(".png)")


class TestClearCache:
    """Tests for cache invalidation."""

    def test_clear_cache_forces_new_icon(self, qapp) -> None:
        """After clear_cache(), phi() should create a fresh QIcon."""
        a = phi("pencil-simple")
        clear_cache()
        b = phi("pencil-simple")
        # They are equal icons but distinct objects after cache flush
        assert a is not b
