"""Popup handler mixin for the response viewer.

Provides ``_PopupMixin`` with click handlers that create and position
the status, timing, size, and network info popups below their
corresponding header labels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ui.request.popups.network_popup import NetworkPopup
from ui.request.popups.size_popup import SizePopup
from ui.request.popups.status_popup import StatusPopup
from ui.request.popups.timing_popup import TimingPopup

if TYPE_CHECKING:
    from ui.widgets.info_popup import ClickableLabel, InfoPopup


class _PopupMixin:
    """Click handlers for the four response-header info popups.

    The host class must initialise the following attributes in its
    ``__init__``:

    - ``_status_popup``, ``_timing_popup``, ``_size_popup``,
      ``_network_popup`` (each ``Popup | None``)
    - ``_status_label``, ``_time_label``, ``_size_label``,
      ``_network_icon`` (each ``ClickableLabel``)
    - ``_last_status_code``, ``_last_status_text``, ``_last_status_color``
    - ``_timing_data``, ``_last_elapsed_ms``, ``_size_data``,
      ``_network_data``
    """

    # Attribute declarations so mypy knows the shapes coming from the host.
    _status_popup: StatusPopup | None
    _timing_popup: TimingPopup | None
    _size_popup: SizePopup | None
    _network_popup: NetworkPopup | None
    _status_label: ClickableLabel
    _time_label: ClickableLabel
    _size_label: ClickableLabel
    _network_icon: ClickableLabel
    _last_status_code: int
    _last_status_text: str
    _last_status_color: str
    _timing_data: dict[str, Any] | None
    _last_elapsed_ms: float
    _size_data: dict[str, Any]
    _network_data: dict[str, Any] | None

    def _close_other_popups(self, keep: InfoPopup | None) -> None:
        """Close every open popup except *keep*."""
        for popup in (
            self._status_popup,
            self._timing_popup,
            self._size_popup,
            self._network_popup,
        ):
            if popup is not None and popup is not keep and popup.isVisible():
                popup.close()

    def _on_status_clicked(self) -> None:
        """Open or refresh the status description popup."""
        if self._status_popup is None:
            self._status_popup = StatusPopup(self)  # type: ignore[arg-type]
        self._close_other_popups(self._status_popup)
        self._status_popup.update_status(
            self._last_status_code,
            self._last_status_text,
            self._last_status_color,
        )
        self._status_popup.show_below(self._status_label)

    def _on_time_clicked(self) -> None:
        """Open or refresh the timing breakdown popup."""
        if self._timing_popup is None:
            self._timing_popup = TimingPopup(self)  # type: ignore[arg-type]
        self._close_other_popups(self._timing_popup)
        if self._timing_data is not None:
            self._timing_popup.update_timing(self._timing_data, self._last_elapsed_ms)
        self._timing_popup.show_below(self._time_label)

    def _on_size_clicked(self) -> None:
        """Open or refresh the size breakdown popup."""
        if self._size_popup is None:
            self._size_popup = SizePopup(self)  # type: ignore[arg-type]
        self._close_other_popups(self._size_popup)
        self._size_popup.update_sizes(self._size_data)
        self._size_popup.show_below(self._size_label)

    def _on_network_clicked(self) -> None:
        """Open or refresh the network info popup."""
        if self._network_popup is None:
            self._network_popup = NetworkPopup(self)  # type: ignore[arg-type]
        self._close_other_popups(self._network_popup)
        self._network_popup.update_network(self._network_data)
        self._network_popup.show_below(self._network_icon)
        self._network_popup.show_below(self._network_icon)  # type: ignore[attr-defined]
