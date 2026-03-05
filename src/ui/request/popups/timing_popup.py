"""Timing breakdown popup — shows per-phase request duration bars.

Displays a vertical list of timing phases (Prepare, DNS Lookup,
TCP Handshake, TLS Handshake, Waiting/TTFB, Download, Process)
with coloured proportional bars and millisecond values.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QSizePolicy, QWidget

from ui.info_popup import InfoPopup
from ui.theme import (COLOR_TIMING_DNS, COLOR_TIMING_DOWNLOAD,
                      COLOR_TIMING_PREPARE, COLOR_TIMING_PROCESS,
                      COLOR_TIMING_TCP, COLOR_TIMING_TLS, COLOR_TIMING_TTFB)

# Phase definitions: (label, timing_dict_key | None, color)
# ``None`` key means the value is computed externally (prepare).
_PHASES: list[tuple[str, str | None, str]] = [
    ("Prepare", None, COLOR_TIMING_PREPARE),
    ("DNS Lookup", "dns_ms", COLOR_TIMING_DNS),
    ("TCP Handshake", "tcp_ms", COLOR_TIMING_TCP),
    ("TLS Handshake", "tls_ms", COLOR_TIMING_TLS),
    ("Waiting (TTFB)", "ttfb_ms", COLOR_TIMING_TTFB),
    ("Download", "download_ms", COLOR_TIMING_DOWNLOAD),
    ("Process", "process_ms", COLOR_TIMING_PROCESS),
]

# Minimum bar width so zero-duration phases are still visible.
_MIN_BAR_WIDTH = 2
# Maximum bar width for the largest phase.
_MAX_BAR_WIDTH = 160


class TimingPopup(InfoPopup):
    """Popup showing per-phase timing breakdown with proportional bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the grid layout for phase rows."""
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)

        header_row, self._copy_btn = self._make_header_with_copy("Request Timing")
        self._copy_btn.clicked.connect(self._copy_as_markdown)
        self.content_layout.addLayout(header_row)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 4, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(4)
        self.content_layout.addLayout(self._grid)

        self._bar_widgets: list[QWidget] = []
        self._value_labels: list[QLabel] = []
        self._name_labels: list[QLabel] = []

        for row, (label, _key, _color) in enumerate(_PHASES):
            name_lbl = QLabel(label)
            name_lbl.setObjectName("mutedLabel")
            name_lbl.setFixedWidth(110)
            self._grid.addWidget(name_lbl, row, 0)
            self._name_labels.append(name_lbl)

            bar = QWidget()
            bar.setFixedHeight(10)
            bar.setMinimumWidth(_MIN_BAR_WIDTH)
            bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._grid.addWidget(bar, row, 1)
            self._bar_widgets.append(bar)

            value_lbl = QLabel("0 ms")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            value_lbl.setFixedWidth(60)
            self._grid.addWidget(value_lbl, row, 2)
            self._value_labels.append(value_lbl)

        # Total row
        self._total_label = QLabel()
        self._total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._total_label.setStyleSheet("font-weight: bold;")
        total_row = len(_PHASES)
        sep = QLabel("")
        sep.setFixedHeight(1)
        sep.setObjectName("infoPopupSeparator")
        self._grid.addWidget(sep, total_row, 0, 1, 3)
        self._grid.addWidget(QLabel("Total"), total_row + 1, 0)
        self._grid.addWidget(self._total_label, total_row + 1, 2)

    def update_timing(self, timing: dict, total_ms: float) -> None:
        """Populate bars and values from a :class:`TimingDict`.

        *timing* must contain keys ``dns_ms``, ``tcp_ms``, ``tls_ms``,
        ``ttfb_ms``, ``download_ms``, ``process_ms``.
        *total_ms* is the overall elapsed time.
        """
        # 1. Compute prepare = total - sum of individual phases
        phase_sum = sum(timing.get(key, 0.0) for _label, key, _color in _PHASES if key)
        prepare_ms = max(0.0, total_ms - phase_sum)

        # 2. Build value list
        values: list[float] = []
        for _label, key, _color in _PHASES:
            if key is None:
                values.append(prepare_ms)
            else:
                values.append(timing.get(key, 0.0))

        max_val = max(values) if values else 1.0
        if max_val == 0:
            max_val = 1.0

        # 3. Update each row
        for i, ((_label, _key, color), val) in enumerate(zip(_PHASES, values, strict=True)):
            self._value_labels[i].setText(f"{val:.1f} ms")
            bar_w = max(
                _MIN_BAR_WIDTH,
                int((val / max_val) * _MAX_BAR_WIDTH),
            )
            self._bar_widgets[i].setFixedWidth(bar_w)
            self._bar_widgets[i].setStyleSheet(f"background: {color}; border-radius: 2px;")

        self._total_label.setText(f"{total_ms:.1f} ms")

    def _copy_as_markdown(self) -> None:
        """Copy the timing breakdown to the clipboard as a Markdown table."""
        lines: list[str] = [
            "| Phase | Duration |",
            "| --- | ---: |",
        ]
        for name_lbl, val_lbl in zip(self._name_labels, self._value_labels, strict=True):
            lines.append(f"| {name_lbl.text()} | {val_lbl.text()} |")
        lines.append(f"| **Total** | **{self._total_label.text()}** |")
        self._copy_to_clipboard("\n".join(lines), self._copy_btn)
