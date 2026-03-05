"""Network info popup — shows HTTP version, addresses, and TLS details.

Displays connection-level metadata captured during the request:
HTTP version, remote/local address, TLS protocol, cipher, and
certificate information.  TLS rows are hidden for plain HTTP.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from ui.info_popup import InfoPopup

# Row definitions: (display_label, dict_key, tls_only)
_ROWS: list[tuple[str, str, bool]] = [
    ("HTTP Version", "http_version", False),
    ("Remote Address", "remote_address", False),
    ("Local Address", "local_address", False),
    ("TLS Protocol", "tls_protocol", True),
    ("Cipher", "cipher_name", True),
    ("Certificate CN", "certificate_cn", True),
    ("Issuer CN", "issuer_cn", True),
    ("Valid Until", "valid_until", True),
]


class NetworkPopup(InfoPopup):
    """Popup showing network-level connection metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the key-value grid for network info rows."""
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)

        header_row, self._copy_btn = self._make_header_with_copy("Network Information")
        self._copy_btn.clicked.connect(self._copy_as_markdown)
        self.content_layout.addLayout(header_row)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 4, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(4)
        self.content_layout.addLayout(self._grid)

        self._name_labels: list[QLabel] = []
        self._value_labels: list[QLabel] = []
        self._tls_only_flags: list[bool] = []

        for row, (label, _key, tls_only) in enumerate(_ROWS):
            name_lbl = QLabel(label)
            name_lbl.setObjectName("mutedLabel")
            self._grid.addWidget(name_lbl, row, 0)
            self._name_labels.append(name_lbl)

            val_lbl = QLabel("—")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._grid.addWidget(val_lbl, row, 1)
            self._value_labels.append(val_lbl)

            self._tls_only_flags.append(tls_only)

    def update_network(self, network: dict | None) -> None:
        """Populate the grid from a :class:`NetworkDict`.

        If *network* is ``None``, all rows show dashes.  TLS rows are
        hidden when no TLS data is present.
        """
        has_tls = False
        if network:
            has_tls = network.get("tls_protocol") is not None

        for i, (_label, key, tls_only) in enumerate(_ROWS):
            value = network.get(key) if network else None
            display = str(value) if value else "—"
            self._value_labels[i].setText(display)

            # Hide TLS-only rows when there is no TLS data
            visible = not tls_only or has_tls
            self._name_labels[i].setVisible(visible)
            self._value_labels[i].setVisible(visible)

    def _copy_as_markdown(self) -> None:
        """Copy the network info to the clipboard as a Markdown table."""
        lines: list[str] = [
            "| Property | Value |",
            "| --- | --- |",
        ]
        for name_lbl, val_lbl in zip(self._name_labels, self._value_labels, strict=True):
            if val_lbl.isVisible():
                lines.append(f"| {name_lbl.text()} | {val_lbl.text()} |")
        self._copy_to_clipboard("\n".join(lines), self._copy_btn)
