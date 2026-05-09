"""Mock HTTP response editor for post-response script inline runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.key_value_table import KeyValueTableWidget

if TYPE_CHECKING:
    from services.environment_service import VariableDetail


class ScriptMockResponseTab(QWidget):
    """Live vs manual response source (request scope) and mock status, headers, body."""

    def __init__(self, *, host_kind: str, parent: QWidget | None = None) -> None:
        """Build controls for *host_kind* ``request`` (combo + hints) or ``folder`` (mock only)."""
        super().__init__(parent)
        self.setObjectName("scriptMockResponseSection")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 0)
        root.setSpacing(4)

        self.response_source_combo: QComboBox | None = None
        self.live_response_hint: QLabel | None = None

        if host_kind == "request":
            source_row = QHBoxLayout()
            source_row.setContentsMargins(0, 0, 0, 0)

            source_lbl = QLabel("Response source")
            source_lbl.setObjectName("mutedLabel")
            source_lbl.setStyleSheet("font-weight: bold;")
            source_row.addWidget(source_lbl)

            self.response_source_combo = QComboBox()
            self.response_source_combo.addItem("Use current response", "live")
            self.response_source_combo.addItem("Manual mock response", "manual")
            self.response_source_combo.setCursor(Qt.CursorShape.PointingHandCursor)
            self.response_source_combo.setFixedWidth(190)
            self.response_source_combo.currentIndexChanged.connect(self._on_response_source_changed)
            source_row.addWidget(self.response_source_combo)
            source_row.addStretch()
            root.addLayout(source_row)

            self.live_response_hint = QLabel(
                "Run will send the current request and use that response."
            )
            self.live_response_hint.setObjectName("mutedLabel")
            self.live_response_hint.setWordWrap(True)
            root.addWidget(self.live_response_hint)
        else:
            mock_title = QLabel("Mock response")
            mock_title.setObjectName("mutedLabel")
            mock_title.setStyleSheet("font-weight: bold;")
            root.addWidget(mock_title)
            folder_hint = QLabel(
                "Script runs use this as the HTTP response (pm.response). "
                "There is no \u201ccurrent request\u201d for a collection."
            )
            folder_hint.setObjectName("mutedLabel")
            folder_hint.setWordWrap(True)
            root.addWidget(folder_hint)

        self.manual_response_container = QWidget()
        manual_col = QVBoxLayout(self.manual_response_container)
        manual_col.setContentsMargins(0, 0, 0, 0)
        manual_col.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        status_lbl = QLabel("Status:")
        status_lbl.setObjectName("mutedLabel")
        header.addWidget(status_lbl)

        self.status_spin = QSpinBox()
        self.status_spin.setRange(100, 599)
        self.status_spin.setValue(200)
        self.status_spin.setFixedWidth(70)
        self.status_spin.setToolTip("HTTP status code for the mock response")
        header.addWidget(self.status_spin)
        header.addStretch()
        manual_col.addLayout(header)

        hdr_lbl = QLabel("Headers")
        hdr_lbl.setObjectName("mutedLabel")
        hdr_lbl.setStyleSheet("font-weight: bold;")
        manual_col.addWidget(hdr_lbl)

        self.headers_table = KeyValueTableWidget(
            placeholder_key="Header",
            placeholder_value="Value",
        )
        self.headers_table.setMinimumHeight(72)
        self.headers_table.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        manual_col.addWidget(self.headers_table)

        body_lbl = QLabel("Body")
        body_lbl.setObjectName("mutedLabel")
        body_lbl.setStyleSheet("font-weight: bold;")
        manual_col.addWidget(body_lbl)

        self.response_body_edit = CodeEditorWidget(parent=self.manual_response_container)
        self.response_body_edit.setPlaceholderText(
            "Paste or type response body here\u2026 "
            "Defaults to `{}` if blank - replace with your mock JSON to test pm.response.json()."
        )
        self.response_body_edit.set_language("json")
        self.response_body_edit.set_word_wrap(False)
        self.response_body_edit.setMinimumHeight(80)
        self.response_body_edit.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        manual_col.addWidget(self.response_body_edit, 1)

        root.addWidget(self.manual_response_container, 1)

        if host_kind == "request":
            self._on_response_source_changed()
        else:
            self.manual_response_container.setVisible(True)

    def set_variable_map(self, variables: dict[str, VariableDetail]) -> None:
        """Forward resolved variables for ``{{name}}`` highlighting in headers and body."""
        self.headers_table.set_variable_map(variables)
        self.response_body_edit.set_variable_map(variables)

    def _on_response_source_changed(self) -> None:
        """Show either live-response hint or manual mock editor."""
        if self.response_source_combo is None or self.live_response_hint is None:
            return
        mode = self.response_source_mode()
        self.live_response_hint.setVisible(mode == "live")
        self.manual_response_container.setVisible(mode == "manual")

    def response_source_mode(self) -> str:
        """Return ``live`` or ``manual`` for request scope; folder scope is always manual."""
        if self.response_source_combo is None:
            return "manual"
        data = self.response_source_combo.currentData()
        return "manual" if data == "manual" else "live"

    def set_response_source_mode(self, mode: str) -> None:
        """Select live vs manual in the combo."""
        if self.response_source_combo is None:
            return
        target = "manual" if mode == "manual" else "live"
        idx = self.response_source_combo.findData(target)
        if idx >= 0:
            self.response_source_combo.setCurrentIndex(idx)

    def get_response_data(self) -> dict[str, Any]:
        """Return a dict suitable for ``ScriptInput.response``."""
        body = self.response_body_edit.toPlainText()
        if not body.strip():
            body = "{}"
        code = self.status_spin.value()

        headers_dict: dict[str, str] = {}
        for row in self.headers_table.get_data():
            if not row.get("enabled", True):
                continue
            key = str(row.get("key", "")).strip()
            if not key:
                continue
            headers_dict[key] = str(row.get("value", ""))

        return {
            "code": code,
            "status": f"{code}",
            "headers": headers_dict,
            "body": body,
            "responseTime": 0,
            "responseSize": len(body.encode("utf-8")),
        }
