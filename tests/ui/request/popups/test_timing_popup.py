"""Tests for the TimingPopup widget."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.request.popups.timing_popup import _PHASES, TimingPopup

# Sample timing data matching TimingDict schema.
_SAMPLE_TIMING = {
    "dns_ms": 5.0,
    "tcp_ms": 10.0,
    "tls_ms": 15.0,
    "ttfb_ms": 50.0,
    "download_ms": 20.0,
    "process_ms": 2.0,
}
_SAMPLE_TOTAL = 142.0


class TestTimingPopup:
    """Tests for the TimingPopup widget."""

    def test_construction(self, qapp: QApplication, qtbot) -> None:
        """TimingPopup can be instantiated."""
        popup = TimingPopup()
        qtbot.addWidget(popup)
        assert popup is not None

    def test_has_all_phase_rows(self, qapp: QApplication, qtbot) -> None:
        """TimingPopup has labels for every timing phase."""
        popup = TimingPopup()
        qtbot.addWidget(popup)

        assert len(popup._name_labels) == len(_PHASES)
        assert len(popup._bar_widgets) == len(_PHASES)
        assert len(popup._value_labels) == len(_PHASES)

    def test_update_timing_populates_values(self, qapp: QApplication, qtbot) -> None:
        """update_timing populates millisecond values for each phase."""
        popup = TimingPopup()
        qtbot.addWidget(popup)
        popup.update_timing(_SAMPLE_TIMING, _SAMPLE_TOTAL)

        # Check that DNS row shows 5.0 ms
        dns_idx = next(i for i, (_, k, _) in enumerate(_PHASES) if k == "dns_ms")
        assert "5.0" in popup._value_labels[dns_idx].text()

        # Check total
        assert "142.0" in popup._total_label.text()

    def test_update_timing_bars_have_width(self, qapp: QApplication, qtbot) -> None:
        """Timing bars have non-zero width after update_timing."""
        popup = TimingPopup()
        qtbot.addWidget(popup)
        popup.update_timing(_SAMPLE_TIMING, _SAMPLE_TOTAL)

        ttfb_idx = next(i for i, (_, k, _) in enumerate(_PHASES) if k == "ttfb_ms")
        assert popup._bar_widgets[ttfb_idx].minimumWidth() >= 2

    def test_update_timing_zero_phases(self, qapp: QApplication, qtbot) -> None:
        """All-zero timing data does not crash."""
        popup = TimingPopup()
        qtbot.addWidget(popup)
        zero_timing = {
            "dns_ms": 0.0,
            "tcp_ms": 0.0,
            "tls_ms": 0.0,
            "ttfb_ms": 0.0,
            "download_ms": 0.0,
            "process_ms": 0.0,
        }
        popup.update_timing(zero_timing, 0.0)

        for lbl in popup._value_labels:
            assert "0.0" in lbl.text()

    def test_prepare_phase_computed(self, qapp: QApplication, qtbot) -> None:
        """The Prepare phase is total minus sum of other phases."""
        popup = TimingPopup()
        qtbot.addWidget(popup)

        timing = {
            "dns_ms": 10.0,
            "tcp_ms": 10.0,
            "tls_ms": 10.0,
            "ttfb_ms": 10.0,
            "download_ms": 10.0,
            "process_ms": 10.0,
        }
        # Total 100 - sum(60) = 40 ms prepare
        popup.update_timing(timing, 100.0)

        prepare_idx = next(i for i, (_, k, _) in enumerate(_PHASES) if k is None)
        assert "40.0" in popup._value_labels[prepare_idx].text()
