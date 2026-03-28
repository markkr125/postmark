"""Pre-request tab mixin for the response viewer.

Provides ``_PreRequestMixin`` which adds a "Pre-request" tab showing
console output, variable changes, and errors from pre-request script
execution.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget

from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS, COLOR_WARNING


class _PreRequestMixin:
    """Add a Pre-request tab to the response viewer.

    The host class must initialise ``_tabs`` (``QTabWidget``) and call
    :meth:`_build_pre_request_tab` during ``__init__``.
    """

    _tabs: QTabWidget
    _pre_request_tab: QWidget
    _pre_tab_index: int
    _pre_request_output: QTextEdit
    _pre_request_vars_label: QLabel
    _pre_request_header: QLabel
    _pre_request_has_error: bool

    def _build_pre_request_tab(self) -> None:
        """Create the Pre-request tab and add it to ``_tabs``."""
        self._pre_request_tab = QWidget()
        tab_layout = QVBoxLayout(self._pre_request_tab)
        tab_layout.setContentsMargins(8, 8, 8, 8)
        tab_layout.setSpacing(6)

        # Header label (status summary).
        self._pre_request_header = QLabel()
        self._pre_request_header.setWordWrap(True)
        tab_layout.addWidget(self._pre_request_header)

        # Scrollable content area.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(8)

        # Variable changes section.
        self._pre_request_vars_label = QLabel()
        self._pre_request_vars_label.setWordWrap(True)
        self._pre_request_vars_label.setTextFormat(Qt.TextFormat.RichText)
        self._pre_request_vars_label.hide()
        inner.addWidget(self._pre_request_vars_label)

        # Console output (monospaced read-only area).
        self._pre_request_output = QTextEdit()
        self._pre_request_output.setReadOnly(True)
        self._pre_request_output.setObjectName("monoEdit")
        self._pre_request_output.setPlaceholderText("No console output")
        inner.addWidget(self._pre_request_output, 1)

        scroll.setWidget(container)
        tab_layout.addWidget(scroll, 1)

        self._pre_tab_index = self._tabs.addTab(self._pre_request_tab, "Pre-request")
        self._tabs.setTabVisible(self._pre_tab_index, False)
        self._pre_request_has_error = False

    def load_pre_request_data(
        self,
        *,
        console_logs: list[dict[str, Any]],
        variable_changes: dict[str, str],
        errors: list[dict[str, Any]],
    ) -> None:
        """Populate the Pre-request tab with script execution data.

        Parameters:
            console_logs: Console output entries from pre-request scripts.
            variable_changes: Variables set/modified by the scripts.
            errors: Runtime errors from pre-request scripts.
        """
        self._pre_request_has_error = bool(errors)

        # 1. Build the header summary.
        if errors:
            lines: list[str] = []
            for err in errors:
                source = err.get("source_name", "pre-request")
                msg = err.get("error", "unknown error")
                lines.append(f"<b>{source}:</b> {msg}")
            header = (
                f"<span style='color:{COLOR_DANGER}; font-weight:bold;'>"
                "Pre-request script error</span><br>" + "<br>".join(lines)
            )
        else:
            header = (
                f"<span style='color:{COLOR_SUCCESS}; font-weight:bold;'>"
                "Pre-request script executed</span>"
            )
        self._pre_request_header.setText(header)

        # 2. Variable changes section.
        if variable_changes:
            rows = "".join(
                f"<tr><td style='padding:2px 8px 2px 0;'><b>{k}</b></td>"
                f"<td style='padding:2px 0;'>{v}</td></tr>"
                for k, v in variable_changes.items()
            )
            self._pre_request_vars_label.setText(
                f"<b>Variable changes:</b><table style='margin-top:4px;'>{rows}</table>"
            )
            self._pre_request_vars_label.show()
        else:
            self._pre_request_vars_label.hide()

        # 3. Console output.
        if console_logs:
            html_parts: list[str] = []
            for entry in console_logs:
                level = entry.get("level", "log")
                message = entry.get("message", "")
                if level == "error":
                    html_parts.append(f"<span style='color:{COLOR_DANGER};'>{message}</span>")
                elif level == "warn":
                    html_parts.append(f"<span style='color:{COLOR_WARNING};'>{message}</span>")
                else:
                    html_parts.append(message)
            self._pre_request_output.setHtml("<br>".join(html_parts))
        else:
            self._pre_request_output.clear()

        # 4. Apply tab colour and make visible.
        self._apply_pre_request_tab_color()
        self._tabs.setTabVisible(self._pre_tab_index, True)

    def _apply_pre_request_tab_color(self) -> None:
        """Set the Pre-request tab text colour based on error state."""
        bar = self._tabs.tabBar()
        color = COLOR_DANGER if self._pre_request_has_error else ""
        bar.setTabTextColor(self._pre_tab_index, bar.palette().text().color())
        if color:
            from PySide6.QtGui import QColor

            bar.setTabTextColor(self._pre_tab_index, QColor(color))

    def _clear_pre_request_tab(self) -> None:
        """Reset the Pre-request tab to its initial hidden state."""
        self._pre_request_output.clear()
        self._pre_request_header.setText("")
        self._pre_request_vars_label.hide()
        self._pre_request_has_error = False
        self._tabs.setTabVisible(self._pre_tab_index, False)
        # Reset tab text colour.
        bar = self._tabs.tabBar()
        bar.setTabTextColor(self._pre_tab_index, bar.palette().text().color())
        bar.setTabTextColor(self._pre_tab_index, bar.palette().text().color())
