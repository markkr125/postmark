"""Date-range filter state and controls for :class:`HistoryPanel`."""

# Mixin methods use attributes defined on :class:`HistoryPanel`.
# mypy: disable-error-code=attr-defined

from __future__ import annotations

from datetime import date
from typing import cast

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from ui.sidebar.history.date_filter import HistoryDateRangeFilterPopup


class _HistoryDateFilterMixin:
    """Shared date filter button, popup, and refresh kwargs."""

    _date_filter_from: date | None
    _date_filter_to: date | None
    _date_filter_btn: QPushButton
    _date_filter_popup: HistoryDateRangeFilterPopup | None
    _search_row: QWidget

    def _init_date_filter_state(self) -> None:
        """Create the filter button and search row container."""
        self._date_filter_from = None
        self._date_filter_to = None
        self._date_filter_popup = None

        self._date_filter_btn = self._make_icon_btn(
            "funnel",
            "Filter by date",
            "iconButton",
            None,
        )
        self._date_filter_btn.setCheckable(True)
        self._date_filter_btn.clicked.connect(self._on_date_filter_btn_clicked)

        self._search_row = QWidget()
        search_layout = QHBoxLayout(self._search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)
        search_layout.addWidget(self._history_search_input, 1)
        search_layout.addWidget(self._date_filter_btn)

    def _on_date_filter_btn_clicked(self) -> None:
        # QPushButton toggles ``checked`` before the click handler; restore active-only state.
        self._sync_date_filter_chrome()
        self._toggle_date_range_filter(self._date_filter_btn)

    def _toggle_date_range_filter(self, anchor: QWidget) -> None:
        """Show or hide the date-range popup below *anchor*."""
        if self._date_filter_popup is not None and self._date_filter_popup.isVisible():
            self._date_filter_popup.hide()
            return
        if self._date_filter_popup is None:
            host = cast(QWidget, self)
            self._date_filter_popup = HistoryDateRangeFilterPopup(host)
            self._date_filter_popup.filter_applied.connect(self._on_date_range_applied)
        self._date_filter_popup.set_range(self._date_filter_from, self._date_filter_to)
        self._date_filter_popup.show_below(anchor)

    def _on_date_range_applied(
        self,
        executed_from: date | None,
        executed_to: date | None,
    ) -> None:
        """Store the range and reload the list."""
        self._date_filter_from = executed_from
        self._date_filter_to = executed_to
        self._sync_date_filter_chrome()
        self.refresh()

    def _date_filter_active(self) -> bool:
        return self._date_filter_from is not None or self._date_filter_to is not None

    def _date_filter_kwargs(self) -> dict[str, date | None]:
        if not self._date_filter_active():
            return {}
        return {
            "executed_from": self._date_filter_from,
            "executed_to": self._date_filter_to,
        }

    def _sync_date_filter_chrome(self) -> None:
        active = self._date_filter_active()
        self._date_filter_btn.setChecked(active)
        if active:
            summary = self._date_filter_summary()
            tip = f"Date filter: {summary} (click to change)"
        else:
            tip = "Filter by date"
        self._date_filter_btn.setToolTip(tip)

    def _date_filter_summary(self) -> str:
        if self._date_filter_from is None and self._date_filter_to is None:
            return ""
        if self._date_filter_from is None:
            return f"through {self._date_filter_to:%d %b %Y}"
        if self._date_filter_to is None:
            return f"from {self._date_filter_from:%d %b %Y}"
        if self._date_filter_from == self._date_filter_to:
            return self._date_filter_from.strftime("%d %b %Y")
        return f"{self._date_filter_from:%d %b %Y} - {self._date_filter_to:%d %b %Y}"

    def _place_date_filter_btn_for_mode(self) -> None:
        """Global mode: header before refresh; request mode: search row."""
        parent = self._date_filter_btn.parentWidget()
        if parent is not None:
            lay = parent.layout()
            if lay is not None:
                lay.removeWidget(self._date_filter_btn)

        if self._is_global_mode() and self._global_header is not None:
            header_lay = self._global_header.layout()
            if isinstance(header_lay, QHBoxLayout):
                header_lay.insertWidget(header_lay.count() - 1, self._date_filter_btn)
            return

        search_lay = self._search_row.layout()
        if isinstance(search_lay, QHBoxLayout):
            search_lay.addWidget(self._date_filter_btn)

    def _reset_date_filter(self) -> None:
        """Clear the active date range (e.g. on panel clear)."""
        self._date_filter_from = None
        self._date_filter_to = None
        if self._date_filter_popup is not None:
            self._date_filter_popup.hide()
        self._sync_date_filter_chrome()
