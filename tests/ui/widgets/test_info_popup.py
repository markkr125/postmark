"""Tests for InfoPopup and ClickableLabel widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from ui.widgets.info_popup import ClickableLabel, InfoPopup


class TestInfoPopup:
    """Tests for the floating InfoPopup widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """InfoPopup can be instantiated without errors."""
        popup = InfoPopup()
        qtbot.addWidget(popup)
        assert popup is not None

    def test_object_name(self, qapp: QApplication, qtbot) -> None:
        """InfoPopup sets its objectName to 'infoPopup'."""
        popup = InfoPopup()
        qtbot.addWidget(popup)
        assert popup.objectName() == "infoPopup"

    def test_window_flags_include_popup(self, qapp: QApplication, qtbot) -> None:
        """InfoPopup has the Tool window flag for controlled dismiss."""
        popup = InfoPopup()
        qtbot.addWidget(popup)
        assert popup.windowFlags() & Qt.WindowType.Tool

    def test_content_layout_is_vbox(self, qapp: QApplication, qtbot) -> None:
        """InfoPopup exposes a QVBoxLayout for content."""
        popup = InfoPopup()
        qtbot.addWidget(popup)
        lbl = QLabel("Test content")
        popup.content_layout.addWidget(lbl)
        assert popup.content_layout.count() == 1

    def test_show_below_positions_popup(self, qapp: QApplication, qtbot) -> None:
        """show_below() moves the popup below the anchor widget."""
        parent = QWidget()
        parent.setGeometry(100, 100, 200, 30)
        parent.show()
        qtbot.addWidget(parent)

        anchor = QLabel("Anchor", parent)
        anchor.setGeometry(10, 5, 50, 20)

        popup = InfoPopup()
        qtbot.addWidget(popup)
        popup.show_below(anchor)

        # Popup should be visible and positioned below anchor
        assert popup.isVisible()
        popup.close()


class TestClickableLabel:
    """Tests for the ClickableLabel widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """ClickableLabel can be instantiated with text."""
        lbl = ClickableLabel("Click me")
        qtbot.addWidget(lbl)
        assert lbl.text() == "Click me"

    def test_cursor_is_pointing_hand(self, qapp: QApplication, qtbot) -> None:
        """ClickableLabel shows a pointing-hand cursor."""
        lbl = ClickableLabel()
        qtbot.addWidget(lbl)
        assert lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_click_emits_signal(self, qapp: QApplication, qtbot) -> None:
        """Clicking the label emits the clicked signal."""
        lbl = ClickableLabel("Click me")
        qtbot.addWidget(lbl)
        lbl.show()

        with qtbot.waitSignal(lbl.clicked, timeout=1000):
            qtbot.mouseClick(lbl, Qt.MouseButton.LeftButton)

    def test_right_click_does_not_emit(self, qapp: QApplication, qtbot) -> None:
        """Right-clicking does not emit the clicked signal."""
        lbl = ClickableLabel("Click me")
        qtbot.addWidget(lbl)
        lbl.show()

        emitted = []
        lbl.clicked.connect(lambda: emitted.append(True))
        qtbot.mouseClick(lbl, Qt.MouseButton.RightButton)
        assert emitted == []
