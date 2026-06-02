"""Inline date-range filter popup for send history lists."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.info_popup import InfoPopup


class HistoryDateRangeFilterPopup(InfoPopup):
    """Floating picker with presets, from/to dates, Apply, and Clear."""

    filter_applied = Signal(object, object)  # date | None, date | None

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build preset chips, date editors, and action row."""
        super().__init__(parent)
        layout = self.content_layout

        title = QLabel("Filter by date")
        title.setObjectName("infoPopupTitle")
        layout.addWidget(title)

        presets = QHBoxLayout()
        presets.setSpacing(4)
        for label, handler in (
            ("Today", self._preset_today),
            ("7 days", self._preset_last_days(7)),
            ("30 days", self._preset_last_days(30)),
            ("All", self._preset_all),
        ):
            btn = QPushButton(label)
            btn.setObjectName("flatMutedButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(handler)
            presets.addWidget(btn)
        layout.addLayout(presets)

        range_row = QHBoxLayout()
        range_row.setSpacing(8)
        self._from_edit = self._make_date_edit()
        self._to_edit = self._make_date_edit()
        range_row.addWidget(self._labeled("From", self._from_edit), 1)
        range_row.addWidget(self._labeled("To", self._to_edit), 1)
        layout.addLayout(range_row)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("flatMutedButton")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._on_clear)
        actions.addWidget(self._clear_btn)
        actions.addStretch(1)
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setObjectName("primaryButton")
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setDefault(True)
        self._apply_btn.clicked.connect(self._on_apply)
        actions.addWidget(self._apply_btn)
        layout.addLayout(actions)

        self.setMinimumWidth(280)

    def set_range(self, executed_from: date | None, executed_to: date | None) -> None:
        """Populate editors from the panel's active filter (or today when unset)."""
        today = date.today()
        from_d = executed_from or today
        to_d = executed_to or today
        if executed_from is None and executed_to is None:
            self._from_edit.setDate(QDate.currentDate())
            self._to_edit.setDate(QDate.currentDate())
            return
        self._from_edit.setDate(QDate(from_d.year, from_d.month, from_d.day))
        self._to_edit.setDate(QDate(to_d.year, to_d.month, to_d.day))

    def _make_date_edit(self) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd MMM yyyy")
        edit.setDate(QDate.currentDate())
        edit.setObjectName("historyDateFilterEdit")
        return edit

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QWidget:
        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        label = QLabel(text)
        label.setObjectName("mutedLabel")
        col.addWidget(label)
        col.addWidget(widget)
        return host

    def _qdate_to_date(self, qd: QDate) -> date:
        return date(qd.year(), qd.month(), qd.day())

    def _read_range(self) -> tuple[date, date]:
        from_d = self._qdate_to_date(self._from_edit.date())
        to_d = self._qdate_to_date(self._to_edit.date())
        if from_d > to_d:
            from_d, to_d = to_d, from_d
        return from_d, to_d

    def _emit_range(self, executed_from: date | None, executed_to: date | None) -> None:
        self.filter_applied.emit(executed_from, executed_to)
        self.hide()

    def _on_apply(self) -> None:
        from_d, to_d = self._read_range()
        self._emit_range(from_d, to_d)

    def _on_clear(self) -> None:
        self._emit_range(None, None)

    def _preset_today(self) -> None:
        today = QDate.currentDate()
        self._from_edit.setDate(today)
        self._to_edit.setDate(today)
        self._on_apply()

    def _preset_last_days(self, days: int) -> Callable[[], None]:
        def _apply() -> None:
            today = date.today()
            start = today - timedelta(days=max(0, days - 1))
            self._from_edit.setDate(QDate(start.year, start.month, start.day))
            self._to_edit.setDate(QDate(today.year, today.month, today.day))
            self._on_apply()

        return _apply

    def _preset_all(self) -> None:
        self._on_clear()
