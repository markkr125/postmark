"""Tests for the NetworkPopup widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.popups.network_popup import _ROWS, NetworkPopup

# Sample HTTPS network data matching NetworkDict schema.
_HTTPS_NETWORK = {
    "http_version": "HTTP/1.1",
    "remote_address": "93.184.216.34:443",
    "local_address": "192.168.1.10:54321",
    "tls_protocol": "TLSv1.3",
    "cipher_name": "TLS_AES_256_GCM_SHA384",
    "certificate_cn": "www.example.com",
    "issuer_cn": "DigiCert SHA2 Extended Validation Server CA",
    "valid_until": "Dec 15 23:59:59 2025 GMT",
}

# Sample HTTP-only network data (no TLS fields).
_HTTP_NETWORK = {
    "http_version": "HTTP/1.1",
    "remote_address": "93.184.216.34:80",
    "local_address": "192.168.1.10:54322",
    "tls_protocol": None,
    "cipher_name": None,
    "certificate_cn": None,
    "issuer_cn": None,
    "valid_until": None,
}


class TestNetworkPopup:
    """Tests for the NetworkPopup widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """NetworkPopup can be instantiated."""
        popup = NetworkPopup()
        qtbot.addWidget(popup)
        assert popup is not None

    def test_has_all_rows(self, qapp: QApplication, qtbot) -> None:
        """NetworkPopup has name and value labels for every row."""
        popup = NetworkPopup()
        qtbot.addWidget(popup)
        assert len(popup._name_labels) == len(_ROWS)
        assert len(popup._value_labels) == len(_ROWS)

    def test_update_network_https(self, qapp: QApplication, qtbot) -> None:
        """HTTPS data shows all rows including TLS fields."""
        popup = NetworkPopup()
        qtbot.addWidget(popup)
        popup.update_network(_HTTPS_NETWORK)

        # All rows should not be explicitly hidden
        for name_lbl in popup._name_labels:
            assert not name_lbl.isHidden()

        # Check specific values
        http_idx = next(i for i, (_, k, _) in enumerate(_ROWS) if k == "http_version")
        assert "HTTP/1.1" in popup._value_labels[http_idx].text()

        tls_idx = next(i for i, (_, k, _) in enumerate(_ROWS) if k == "tls_protocol")
        assert "TLSv1.3" in popup._value_labels[tls_idx].text()

    def test_update_network_http_only(self, qapp: QApplication, qtbot) -> None:
        """HTTP-only data hides TLS rows."""
        popup = NetworkPopup()
        qtbot.addWidget(popup)
        popup.update_network(_HTTP_NETWORK)

        # Non-TLS rows not hidden
        http_idx = next(i for i, (_, k, _) in enumerate(_ROWS) if k == "http_version")
        assert not popup._name_labels[http_idx].isHidden()

        # TLS rows hidden
        tls_idx = next(i for i, (_, k, _) in enumerate(_ROWS) if k == "tls_protocol")
        assert popup._name_labels[tls_idx].isHidden()
        assert popup._value_labels[tls_idx].isHidden()

    def test_update_network_none(self, qapp: QApplication, qtbot) -> None:
        """None network data shows dashes without crashing."""
        popup = NetworkPopup()
        qtbot.addWidget(popup)
        popup.update_network(None)

        for _i, val_lbl in enumerate(popup._value_labels):
            if not val_lbl.isHidden():
                assert val_lbl.text() == "—"

    def test_values_are_selectable(self, qapp: QApplication, qtbot) -> None:
        """Value labels have text-selectable-by-mouse flag."""
        popup = NetworkPopup()
        qtbot.addWidget(popup)
        from PySide6.QtCore import Qt

        for val_lbl in popup._value_labels:
            assert val_lbl.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
