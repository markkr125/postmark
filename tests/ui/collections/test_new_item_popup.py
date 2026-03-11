"""Tests for the NewItemPopup dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from ui.collections.new_item_popup import NewItemPopup, _Tile


class TestTile:
    """Tests for the internal _Tile button widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """_Tile can be instantiated with an icon name and label."""
        tile = _Tile("globe", "HTTP Request")
        qtbot.addWidget(tile)
        assert tile.objectName() == "newItemTile"

    def test_fixed_size(self, qapp: QApplication, qtbot) -> None:
        """_Tile has fixed 140x110 size."""
        tile = _Tile("globe", "HTTP Request")
        qtbot.addWidget(tile)
        assert tile.width() == 140
        assert tile.height() == 110

    def test_cursor_is_hand(self, qapp: QApplication, qtbot) -> None:
        """_Tile shows a pointing hand cursor."""
        tile = _Tile("globe", "HTTP Request")
        qtbot.addWidget(tile)
        assert tile.cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestNewItemPopup:
    """Tests for the NewItemPopup dialog window."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """NewItemPopup can be instantiated without errors."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)
        assert popup.objectName() == "newItemPopup"

    def test_is_qdialog(self, qapp: QApplication, qtbot) -> None:
        """NewItemPopup is a QDialog."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)
        assert isinstance(popup, QDialog)

    def test_window_title(self, qapp: QApplication, qtbot) -> None:
        """Dialog has the 'Create New' title."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)
        assert popup.windowTitle() == "Create New"

    def test_has_description_label(self, qapp: QApplication, qtbot) -> None:
        """Dialog contains a description label with default text."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)
        assert popup._description is not None
        assert "HTTP request" in popup._description.text()

    def test_new_request_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the HTTP tile emits ``new_request_clicked``."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)

        http_tile = popup.findChildren(QPushButton)[0]
        with qtbot.waitSignal(popup.new_request_clicked, timeout=1000):
            http_tile.click()

    def test_new_collection_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the Collection tile emits ``new_collection_clicked``."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)

        tiles = popup.findChildren(QPushButton)
        collection_tile = tiles[1]
        with qtbot.waitSignal(popup.new_collection_clicked, timeout=1000):
            collection_tile.click()

    def test_accept_on_http_click(self, qapp: QApplication, qtbot) -> None:
        """Dialog accepts after clicking the HTTP tile."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)

        # _on_http_clicked should emit + accept
        results: list[int] = []
        popup.finished.connect(lambda r: results.append(r))
        popup._on_http_clicked()
        assert results == [int(QDialog.DialogCode.Accepted)]

    def test_accept_on_collection_click(self, qapp: QApplication, qtbot) -> None:
        """Dialog accepts after clicking the Collection tile."""
        popup = NewItemPopup()
        qtbot.addWidget(popup)

        results: list[int] = []
        popup.finished.connect(lambda r: results.append(r))
        popup._on_collection_clicked()
        assert results == [int(QDialog.DialogCode.Accepted)]
