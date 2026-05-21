"""Declarative assertions table for the request editor."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.assertion_service import AssertionDict
from services.scripting.assertions_compiler import VALID_OPERATORS
from ui.styling.icons import phi

_OPERATOR_LABELS: dict[str, str] = {
    "eq": "equals",
    "ne": "not equals",
    "gt": "greater than",
    "lt": "less than",
    "contains": "contains",
    "matches": "matches regex",
    "exists": "exists",
    "is_type": "is type",
}


class AssertionsTab(QWidget):
    """Editable table of declarative assertion rows."""

    rows_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the scrollable assertion editor."""
        super().__init__(parent)
        self.setObjectName("assertionsTab")
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        for label, stretch in (
            ("", 0),
            ("Subject", 3),
            ("Operator", 2),
            ("Expected", 3),
            ("", 0),
        ):
            if not label:
                spacer = QLabel()
                spacer.setFixedWidth(24)
                header.addWidget(spacer)
            else:
                lbl = QLabel(label)
                lbl.setObjectName("sectionLabel")
                header.addWidget(lbl, stretch)
            if label == "Expected":
                header.addSpacing(28)
        root.addLayout(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("assertionsScroll")
        self._rows_host = QWidget(scroll)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_host)
        root.addWidget(scroll, 1)

        add_btn = QPushButton("Add assertion")
        add_btn.setObjectName("outlineButton")
        add_btn.setIcon(phi("plus"))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_clicked)
        root.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self._empty_hint = QLabel("Add declarative checks that compile to pm.test blocks on send.")
        self._empty_hint.setObjectName("mutedLabel")
        self._empty_hint.setWordWrap(True)
        root.addWidget(self._empty_hint)

    def set_rows(self, rows: list[AssertionDict]) -> None:
        """Replace all rows from persisted assertion dicts."""
        self._loading = True
        try:
            self._clear_rows()
            if rows:
                for row in rows:
                    self._append_row_widget(row)
            else:
                self._append_row_widget(self._blank_row())
            self._sync_empty_hint()
        finally:
            self._loading = False

    def get_rows(self) -> list[AssertionDict]:
        """Return current assertion rows in display order."""
        rows: list[AssertionDict] = []
        for index in range(self._rows_layout.count() - 1):
            item = self._rows_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            row = self._row_from_widget(widget)
            if row is not None:
                row["order_index"] = index
                rows.append(row)
        return rows

    def has_content(self) -> bool:
        """Return ``True`` when at least one row has a non-empty subject."""
        return any(row.get("subject", "").strip() for row in self.get_rows())

    def _blank_row(self) -> AssertionDict:
        return {
            "subject": "",
            "operator": "eq",
            "expected": "",
            "enabled": True,
            "order_index": 0,
        }

    def _clear_rows(self) -> None:
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _append_row_widget(self, data: AssertionDict) -> None:
        row = QWidget(self._rows_host)
        row.setObjectName("assertionRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        enabled = QCheckBox(row)
        enabled.setChecked(bool(data.get("enabled", True)))
        enabled.setToolTip("Enable this assertion")
        enabled.stateChanged.connect(self._emit_rows_changed)
        layout.addWidget(enabled)

        subject = QLineEdit(str(data.get("subject", "")), row)
        subject.setPlaceholderText("res.status")
        subject.setObjectName("assertionSubjectEdit")
        subject.editingFinished.connect(self._emit_rows_changed)
        layout.addWidget(subject, 3)

        operator = QComboBox(row)
        operator.setObjectName("assertionOperatorCombo")
        for key in sorted(VALID_OPERATORS):
            operator.addItem(_OPERATOR_LABELS.get(key, key), key)
        op_value = str(data.get("operator", "eq"))
        op_index = operator.findData(op_value)
        operator.setCurrentIndex(op_index if op_index >= 0 else 0)
        operator.currentIndexChanged.connect(self._on_operator_changed)
        layout.addWidget(operator, 2)

        expected = QLineEdit(str(data.get("expected", "")), row)
        expected.setPlaceholderText("200")
        expected.setObjectName("assertionExpectedEdit")
        expected.editingFinished.connect(self._emit_rows_changed)
        layout.addWidget(expected, 3)

        delete_btn = QPushButton(row)
        delete_btn.setObjectName("iconDangerButton")
        delete_btn.setIcon(phi("trash", color="#e74c3c"))
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setFixedSize(28, 28)
        delete_btn.setToolTip("Remove assertion")
        delete_btn.clicked.connect(lambda _checked=False, w=row: self._remove_row(w))
        layout.addWidget(delete_btn)

        row._enabled = enabled  # type: ignore[attr-defined]
        row._subject = subject  # type: ignore[attr-defined]
        row._operator = operator  # type: ignore[attr-defined]
        row._expected = expected  # type: ignore[attr-defined]

        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
        self._update_expected_enabled(row)

    def _row_from_widget(self, row: QWidget) -> AssertionDict | None:
        subject = getattr(row, "_subject", None)
        operator = getattr(row, "_operator", None)
        expected = getattr(row, "_expected", None)
        enabled = getattr(row, "_enabled", None)
        if subject is None or operator is None or expected is None or enabled is None:
            return None
        return {
            "subject": subject.text().strip(),
            "operator": str(operator.currentData() or "eq"),
            "expected": expected.text(),
            "enabled": enabled.isChecked(),
            "order_index": 0,
        }

    def _remove_row(self, row: QWidget) -> None:
        if self._rows_layout.count() <= 2:
            self._clear_rows()
            self._append_row_widget(self._blank_row())
        else:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._sync_empty_hint()
        self._emit_rows_changed()

    def _on_add_clicked(self) -> None:
        self._append_row_widget(self._blank_row())
        self._sync_empty_hint()
        self._emit_rows_changed()

    def _on_operator_changed(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QComboBox):
            return
        parent = sender.parentWidget()
        if parent is not None:
            self._update_expected_enabled(parent)
        self._emit_rows_changed()

    def _update_expected_enabled(self, row: QWidget) -> None:
        operator = getattr(row, "_operator", None)
        expected = getattr(row, "_expected", None)
        if operator is None or expected is None:
            return
        op = str(operator.currentData() or "eq")
        hide_expected = op in {"exists"}
        expected.setEnabled(not hide_expected)
        if hide_expected:
            expected.setPlaceholderText("—")
        else:
            expected.setPlaceholderText("200")

    def _sync_empty_hint(self) -> None:
        has_rows = self._rows_layout.count() > 1
        self._empty_hint.setVisible(not has_rows)

    def _emit_rows_changed(self) -> None:
        if self._loading:
            return
        self.rows_changed.emit()
