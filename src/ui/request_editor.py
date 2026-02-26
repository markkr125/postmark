"""Read-only request editor pane showing method, URL, and tabbed details."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from ui.theme import (COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED,
                      COLOR_WHITE)

# HTTP methods shown in the dropdown
_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


class RequestEditorWidget(QWidget):
    """Display-only request editor with method, URL bar, and tabbed sections.

    Call :meth:`load_request` to populate the pane from a request dict.
    Emits ``send_requested`` when the Send button is clicked (future use).
    """

    send_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the request editor layout."""
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # -- Title label (shows request name) --
        self._title_label = QLabel()
        self._title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLOR_TEXT};")
        root.addWidget(self._title_label)

        # -- Top bar: method dropdown + URL + Send --
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self._method_combo = QComboBox()
        self._method_combo.addItems(list(_HTTP_METHODS))
        self._method_combo.setFixedWidth(90)
        self._method_combo.setStyleSheet(
            f"""
            QComboBox {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                padding: 4px 8px;
                font-weight: bold;
                color: {COLOR_TEXT};
            }}
            """
        )
        top_bar.addWidget(self._method_combo)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Enter request URL")
        self._url_input.setStyleSheet(
            f"""
            background: {COLOR_WHITE};
            border: 1px solid {COLOR_BORDER};
            padding: 4px 8px;
            color: {COLOR_TEXT};
            """
        )
        self._url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_bar.addWidget(self._url_input)

        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {COLOR_ACCENT};
                color: {COLOR_WHITE};
                border: none;
                padding: 6px 16px;
                font-weight: bold;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            """
        )
        self._send_btn.clicked.connect(self.send_requested.emit)
        top_bar.addWidget(self._send_btn)

        root.addLayout(top_bar)

        # -- Tabbed area: Params, Headers, Body, Scripts --
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"""
            QTabBar::tab {{
                padding: 6px 14px;
                color: {COLOR_TEXT_MUTED};
            }}
            QTabBar::tab:selected {{
                color: {COLOR_TEXT};
                border-bottom: 2px solid {COLOR_ACCENT};
            }}
            """
        )

        self._params_edit = QTextEdit()
        self._params_edit.setPlaceholderText("Query parameters")
        self._params_edit.setReadOnly(True)
        self._tabs.addTab(self._params_edit, "Params")

        self._headers_edit = QTextEdit()
        self._headers_edit.setPlaceholderText("Request headers")
        self._headers_edit.setReadOnly(True)
        self._tabs.addTab(self._headers_edit, "Headers")

        self._body_edit = QTextEdit()
        self._body_edit.setPlaceholderText("Request body")
        self._body_edit.setReadOnly(True)
        self._tabs.addTab(self._body_edit, "Body")

        self._scripts_edit = QTextEdit()
        self._scripts_edit.setPlaceholderText("Scripts")
        self._scripts_edit.setReadOnly(True)
        self._tabs.addTab(self._scripts_edit, "Scripts")

        root.addWidget(self._tabs, 1)

        # -- Empty state --
        self._empty_label = QLabel("Select a request to view its details.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-style: italic; font-size: 13px;"
        )
        root.addWidget(self._empty_label)

        # Start in empty state
        self._set_content_visible(False)

    def _set_content_visible(self, visible: bool) -> None:
        """Toggle between the editor content and the empty-state label."""
        self._title_label.setVisible(visible)
        self._method_combo.setVisible(visible)
        self._url_input.setVisible(visible)
        self._send_btn.setVisible(visible)
        self._tabs.setVisible(visible)
        self._empty_label.setVisible(not visible)

    def load_request(self, data: dict) -> None:
        """Populate the editor from a request data dict.

        Expected keys: ``name``, ``method``, ``url``, and optionally
        ``body``, ``request_parameters``, ``headers``, ``scripts``.
        """
        self._set_content_visible(True)

        self._title_label.setText(data.get("name", ""))

        method = data.get("method", "GET").upper()
        idx = self._method_combo.findText(method)
        if idx >= 0:
            self._method_combo.setCurrentIndex(idx)

        self._url_input.setText(data.get("url", ""))

        self._params_edit.setPlainText(data.get("request_parameters") or "")
        self._headers_edit.setPlainText(data.get("headers") or "")
        self._body_edit.setPlainText(data.get("body") or "")

        scripts = data.get("scripts")
        if isinstance(scripts, dict):
            import json

            self._scripts_edit.setPlainText(json.dumps(scripts, indent=2))
        elif scripts:
            self._scripts_edit.setPlainText(str(scripts))
        else:
            self._scripts_edit.setPlainText("")

    def clear_request(self) -> None:
        """Reset the editor to the empty state."""
        self._set_content_visible(False)
        self._title_label.setText("")
        self._method_combo.setCurrentIndex(0)
        self._url_input.clear()
        self._params_edit.clear()
        self._headers_edit.clear()
        self._body_edit.clear()
        self._scripts_edit.clear()
