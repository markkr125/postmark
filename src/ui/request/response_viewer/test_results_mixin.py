"""Test results mixin for the response viewer.

Provides ``_TestResultsMixin`` which adds a "Test Results" tab showing
pass/fail assertions from script execution.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from ui.styling.icons import phi
from ui.styling.theme import COLOR_DANGER, COLOR_SUCCESS


class _TestResultsMixin:
    """Add a Test Results tab to the response viewer.

    The host class must initialise ``_tabs`` (``QTabWidget``) and call
    :meth:`_build_test_results_tab` during ``__init__``.
    """

    _tabs: QTabWidget
    _test_results_list: QVBoxLayout
    _test_results_summary: QLabel
    _test_results_scroll: QScrollArea
    _test_results_tab: QWidget
    _test_tab_index: int
    _test_results: list[dict[str, Any]]

    def _build_test_results_tab(self) -> None:
        """Create the Test Results tab and add it to ``_tabs``."""
        self._test_results_tab = QWidget()
        tab_layout = QVBoxLayout(self._test_results_tab)
        tab_layout.setContentsMargins(8, 8, 8, 8)
        tab_layout.setSpacing(6)

        self._test_results_summary = QLabel()
        self._test_results_summary.setObjectName("testResultsSummary")
        tab_layout.addWidget(self._test_results_summary)

        # Scrollable list of result rows.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._test_results_scroll = scroll

        container = QWidget()
        self._test_results_list = QVBoxLayout(container)
        self._test_results_list.setContentsMargins(0, 0, 0, 0)
        self._test_results_list.setSpacing(2)
        self._test_results_list.addStretch()
        scroll.setWidget(container)
        tab_layout.addWidget(scroll, 1)

        self._test_tab_index = self._tabs.addTab(self._test_results_tab, "Test Results")
        self._test_results: list[dict[str, Any]] = []
        self._tabs.setTabVisible(self._test_tab_index, False)

    def load_test_results(self, results: list[dict[str, Any]]) -> None:
        """Populate the Test Results tab with *results*.

        Each result dict should contain ``name`` (str), ``passed``
        (bool), and optionally ``error`` (str | None) and
        ``duration_ms`` (float).
        """
        self._test_results = list(results)
        self._clear_test_results_rows()

        if not results:
            self._tabs.setTabVisible(self._test_tab_index, False)
            return

        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        color = COLOR_SUCCESS if passed == total else COLOR_DANGER
        self._test_results_summary.setText(
            f"<span style='color:{color};font-weight:bold;'>{passed}/{total} tests passed</span>"
        )

        for result in results:
            row = self._build_result_row(result)
            # Insert before the stretch at the end.
            self._test_results_list.insertWidget(self._test_results_list.count() - 1, row)

        self._tabs.setTabVisible(self._test_tab_index, True)

    def _clear_test_results_rows(self) -> None:
        """Remove all result row widgets from the list layout."""
        layout = self._test_results_list
        while layout.count() > 1:  # keep the stretch
            item = layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        self._test_results_summary.setText("")

    @staticmethod
    def _build_result_row(result: dict[str, Any]) -> QWidget:
        """Create a single pass/fail row widget."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(8)

        passed = result.get("passed", False)
        icon_name = "check-circle" if passed else "x-circle"
        color = COLOR_SUCCESS if passed else COLOR_DANGER
        icon_label = QLabel()
        icon_label.setPixmap(phi(icon_name, color=color).pixmap(16, 16))
        icon_label.setFixedSize(18, 18)
        row_layout.addWidget(icon_label)

        name_label = QLabel(result.get("name", "unnamed"))
        name_label.setStyleSheet("font-size: 12px;")
        row_layout.addWidget(name_label, 1)

        duration = result.get("duration_ms", 0.0)
        if duration > 0:
            dur_label = QLabel(f"{duration:.0f} ms")
            dur_label.setObjectName("mutedLabel")
            dur_label.setStyleSheet("font-size: 11px;")
            row_layout.addWidget(dur_label)

        error = result.get("error")
        if error and not passed:
            name_label.setToolTip(str(error))
            err_label = QLabel(str(error))
            err_label.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 11px;")
            err_label.setWordWrap(True)
            err_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            # Wrap row + error in a vertical container.
            outer = QWidget()
            outer_layout = QVBoxLayout(outer)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            outer_layout.addWidget(row_widget)
            outer_layout.addWidget(err_label)
            return outer

        return row_widget
