"""Tests for the SizePopup widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.popups.size_popup import SizePopup


class TestSizePopup:
    """Tests for the SizePopup widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """SizePopup can be instantiated."""
        popup = SizePopup()
        qtbot.addWidget(popup)
        assert popup is not None

    def test_update_sizes_full_data(self, qapp: QApplication, qtbot) -> None:
        """update_sizes with all fields populates response and request sizes."""
        popup = SizePopup()
        qtbot.addWidget(popup)
        popup.update_sizes(
            {
                "response_headers_size": 256,
                "size_bytes": 1024,
                "response_uncompressed_size": 4096,
                "request_headers_size": 128,
                "request_body_size": 512,
            }
        )

        assert "256 B" in popup._resp_headers_label.text()
        assert "KB" in popup._resp_body_label.text()  # 1024 = 1.0 KB
        assert "KB" in popup._resp_uncompressed_label.text()  # 4096 = 4.0 KB
        assert not popup._resp_uncompressed_name.isHidden()
        assert "128 B" in popup._req_headers_label.text()
        assert "512 B" in popup._req_body_label.text()

    def test_update_sizes_no_uncompressed(self, qapp: QApplication, qtbot) -> None:
        """Uncompressed row is hidden when no uncompressed size is present."""
        popup = SizePopup()
        qtbot.addWidget(popup)
        popup.update_sizes(
            {
                "response_headers_size": 100,
                "size_bytes": 200,
                "request_headers_size": 50,
                "request_body_size": 0,
            }
        )

        assert popup._resp_uncompressed_name.isHidden()
        assert popup._resp_uncompressed_label.isHidden()

    def test_update_sizes_uncompressed_equals_body(self, qapp: QApplication, qtbot) -> None:
        """Uncompressed row is hidden when it equals the body size."""
        popup = SizePopup()
        qtbot.addWidget(popup)
        popup.update_sizes(
            {
                "response_headers_size": 100,
                "size_bytes": 200,
                "response_uncompressed_size": 200,  # same as body
                "request_headers_size": 50,
                "request_body_size": 0,
            }
        )

        assert popup._resp_uncompressed_name.isHidden()

    def test_update_sizes_zero_request_body(self, qapp: QApplication, qtbot) -> None:
        """Zero request body size shows '0 B'."""
        popup = SizePopup()
        qtbot.addWidget(popup)
        popup.update_sizes(
            {
                "response_headers_size": 100,
                "size_bytes": 100,
                "request_headers_size": 50,
                "request_body_size": 0,
            }
        )

        assert "0 B" in popup._req_body_label.text()

    def test_update_sizes_empty_dict(self, qapp: QApplication, qtbot) -> None:
        """An empty dict defaults all fields to zero without crashing."""
        popup = SizePopup()
        qtbot.addWidget(popup)
        popup.update_sizes({})

        assert "0 B" in popup._resp_headers_label.text()
        assert "0 B" in popup._req_headers_label.text()
