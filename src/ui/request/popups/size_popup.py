"""Size breakdown popup — shows request/response header and body sizes.

Two sections: **Response Size** (headers, body, uncompressed) and
**Request Size** (headers, body).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from ui.info_popup import InfoPopup


def _format_size(size_bytes: int) -> str:
    """Format byte count into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


class SizePopup(InfoPopup):
    """Popup showing response/request size breakdown."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise with two grid sections for response and request sizes."""
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(340)

        # -- Header with copy button -----------------------------------
        header_row, self._copy_btn = self._make_header_with_copy("Response Size")
        self._copy_btn.clicked.connect(self._copy_as_markdown)
        self.content_layout.addLayout(header_row)

        self._resp_grid = QGridLayout()
        self._resp_grid.setContentsMargins(0, 2, 0, 8)
        self._resp_grid.setHorizontalSpacing(12)
        self._resp_grid.setVerticalSpacing(2)
        self.content_layout.addLayout(self._resp_grid)

        self._resp_headers_label = QLabel("0 B")
        self._resp_body_label = QLabel("0 B")
        self._resp_uncompressed_label = QLabel()
        self._resp_uncompressed_name = QLabel("Uncompressed")
        self._resp_uncompressed_name.setObjectName("mutedLabel")

        for row, (name, val_label) in enumerate(
            [
                ("Headers", self._resp_headers_label),
                ("Body", self._resp_body_label),
            ]
        ):
            name_lbl = QLabel(name)
            name_lbl.setObjectName("mutedLabel")
            self._resp_grid.addWidget(name_lbl, row, 0)
            val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            self._resp_grid.addWidget(val_label, row, 1)

        # Uncompressed row (hidden by default)
        self._resp_grid.addWidget(self._resp_uncompressed_name, 2, 0)
        self._resp_uncompressed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._resp_grid.addWidget(self._resp_uncompressed_label, 2, 1)
        self._resp_uncompressed_name.hide()
        self._resp_uncompressed_label.hide()

        # -- Request Size section --------------------------------------
        req_title = QLabel("Request Size")
        req_title.setObjectName("infoPopupTitle")
        self.content_layout.addWidget(req_title)

        self._req_grid = QGridLayout()
        self._req_grid.setContentsMargins(0, 2, 0, 0)
        self._req_grid.setHorizontalSpacing(12)
        self._req_grid.setVerticalSpacing(2)
        self.content_layout.addLayout(self._req_grid)

        self._req_headers_label = QLabel("0 B")
        self._req_body_label = QLabel("0 B")

        for row, (name, val_label) in enumerate(
            [
                ("Headers", self._req_headers_label),
                ("Body", self._req_body_label),
            ]
        ):
            name_lbl = QLabel(name)
            name_lbl.setObjectName("mutedLabel")
            self._req_grid.addWidget(name_lbl, row, 0)
            val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            self._req_grid.addWidget(val_label, row, 1)

    def update_sizes(self, data: dict) -> None:
        """Populate the size labels from *data*.

        Expected keys (all optional):
        ``response_headers_size``, ``size_bytes``,
        ``response_uncompressed_size``, ``request_headers_size``,
        ``request_body_size``.
        """
        self._resp_headers_label.setText(_format_size(data.get("response_headers_size", 0)))
        self._resp_body_label.setText(_format_size(data.get("size_bytes", 0)))

        uncompressed = data.get("response_uncompressed_size")
        if uncompressed is not None and uncompressed != data.get("size_bytes", 0):
            self._resp_uncompressed_name.show()
            self._resp_uncompressed_label.show()
            self._resp_uncompressed_label.setText(_format_size(uncompressed))
        else:
            self._resp_uncompressed_name.hide()
            self._resp_uncompressed_label.hide()

        self._req_headers_label.setText(_format_size(data.get("request_headers_size", 0)))
        self._req_body_label.setText(_format_size(data.get("request_body_size", 0)))

    def _copy_as_markdown(self) -> None:
        """Copy the size breakdown to the clipboard as a Markdown table."""
        lines: list[str] = [
            "**Response Size**",
            "",
            "| Component | Size |",
            "| --- | ---: |",
            f"| Headers | {self._resp_headers_label.text()} |",
            f"| Body | {self._resp_body_label.text()} |",
        ]
        if self._resp_uncompressed_label.isVisible():
            lines.append(f"| Uncompressed | {self._resp_uncompressed_label.text()} |")
        lines.extend(
            [
                "",
                "**Request Size**",
                "",
                "| Component | Size |",
                "| --- | ---: |",
                f"| Headers | {self._req_headers_label.text()} |",
                f"| Body | {self._req_body_label.text()} |",
            ]
        )
        self._copy_to_clipboard("\n".join(lines), self._copy_btn)
