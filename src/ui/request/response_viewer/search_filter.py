"""Search and filter mixin for the response viewer.

Provides ``_SearchFilterMixin`` with:
- ``_build_filter_bar`` / ``_build_search_bar`` — UI construction helpers
  called from the host ``__init__``.
- Body search: toggle, highlight, next/prev navigation.
- Response filter: JSONPath / XPath evaluation and display.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_WARNING
from ui.widgets.code_editor import CodeEditorWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QVBoxLayout


class _SearchFilterMixin:
    """Mixin that adds search/filter bars and related methods.

    Expects the host class to provide ``_body_edit``, ``_format_combo``,
    ``_search_btn``, ``_filter_btn``, ``_raw_body``,
    ``_apply_body_format()``, and ``_try_pretty_json()``.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _body_edit: CodeEditorWidget
    _format_combo: QComboBox
    _search_btn: QPushButton
    _filter_btn: QPushButton
    _raw_body: str
    _is_filtered: bool
    _filter_expression: str
    _filtered_body: str
    _apply_body_format: Callable[[], None]
    _try_pretty_json: Callable[[str], str]

    # -- Builder helpers (called from host __init__) --------------------

    def _build_filter_bar(self, body_layout: QVBoxLayout) -> None:
        """Construct the filter bar and add it to *body_layout*."""
        self._filter_bar = QWidget()
        filter_layout = QHBoxLayout(self._filter_bar)
        filter_layout.setContentsMargins(0, 4, 0, 0)
        filter_layout.setSpacing(4)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter using JSONPath: $.store.books")
        self._filter_input.returnPressed.connect(self._apply_filter)
        filter_layout.addWidget(self._filter_input, 1)

        self._filter_error_label = QLabel()
        self._filter_error_label.setObjectName("mutedLabel")
        self._filter_error_label.hide()
        filter_layout.addWidget(self._filter_error_label)

        self._filter_apply_btn = QPushButton()
        self._filter_apply_btn.setIcon(phi("play"))
        self._filter_apply_btn.setFixedSize(28, 28)
        self._filter_apply_btn.setToolTip("Apply filter")
        self._filter_apply_btn.setObjectName("iconButton")
        self._filter_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_apply_btn.clicked.connect(self._apply_filter)
        filter_layout.addWidget(self._filter_apply_btn)

        self._filter_clear_btn = QPushButton()
        self._filter_clear_btn.setIcon(phi("x"))
        self._filter_clear_btn.setFixedSize(28, 28)
        self._filter_clear_btn.setToolTip("Clear filter")
        self._filter_clear_btn.setObjectName("iconButton")
        self._filter_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_clear_btn.clicked.connect(self._clear_filter)
        self._filter_clear_btn.hide()
        filter_layout.addWidget(self._filter_clear_btn)

        self._filter_bar.hide()
        body_layout.addWidget(self._filter_bar)

        self._is_filtered = False
        self._filter_expression = ""

    def _build_search_bar(self, body_layout: QVBoxLayout) -> None:
        """Construct the search bar and add it to *body_layout*."""
        self._search_bar = QWidget()
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(0, 4, 0, 0)
        search_layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Find in response\u2026")
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self._search_input, 1)

        self._search_count_label = QLabel("")
        self._search_count_label.setObjectName("mutedLabel")
        search_layout.addWidget(self._search_count_label)

        prev_btn = QPushButton()
        prev_btn.setIcon(phi("caret-up"))
        prev_btn.setFixedSize(24, 24)
        prev_btn.setToolTip("Previous match")
        prev_btn.setObjectName("iconButton")
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.clicked.connect(self._search_prev)
        search_layout.addWidget(prev_btn)

        next_btn = QPushButton()
        next_btn.setIcon(phi("caret-down"))
        next_btn.setFixedSize(24, 24)
        next_btn.setToolTip("Next match")
        next_btn.setObjectName("iconButton")
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(self._search_next)
        search_layout.addWidget(next_btn)

        close_btn = QPushButton()
        close_btn.setIcon(phi("x"))
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("Close search")
        close_btn.setObjectName("iconButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._close_search)
        search_layout.addWidget(close_btn)

        self._search_bar.hide()
        body_layout.addWidget(self._search_bar)

        # Platform-native Find shortcut (Cmd+F on macOS, Ctrl+F elsewhere).
        # Scoped to this widget tree so the editor's own shortcut is not
        # swallowed when the request body editor has focus.
        self._find_shortcut = QShortcut(QKeySequence.StandardKey.Find, cast(QObject, self))
        self._find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._find_shortcut.activated.connect(self._toggle_search)

        self._search_matches: list[int] = []
        self._search_index: int = -1

    # -- Body search ---------------------------------------------------

    def _toggle_search(self) -> None:
        """Show or hide the body search bar."""
        if not self._search_bar.isHidden():
            self._close_search()
        else:
            self._search_bar.show()
            self._search_btn.setChecked(True)
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _close_search(self) -> None:
        """Hide the search bar and clear highlights."""
        self._search_bar.hide()
        self._search_btn.setChecked(False)
        self._search_input.clear()
        self._clear_highlights()

    def _on_search_text_changed(self, text: str) -> None:
        """Highlight all occurrences of *text* in the body."""
        self._clear_highlights()
        self._search_matches = []
        self._search_index = -1

        if not text:
            self._search_count_label.setText("")
            return

        # Find all matches
        body_text = self._body_edit.toPlainText()
        start = 0
        while True:
            idx = body_text.find(text, start)
            if idx == -1:
                break
            self._search_matches.append(idx)
            start = idx + 1

        if not self._search_matches:
            self._search_count_label.setText("No results")
            return

        # Highlight all matches via extra selections
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_WARNING))
        selections: list[QTextEdit.ExtraSelection] = []
        for pos in self._search_matches:
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(self._body_edit.document())
            cur.setPosition(pos)
            cur.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        self._body_edit.set_search_selections(selections)

        # Move to first match
        self._search_index = 0
        self._goto_match()

    def _search_next(self) -> None:
        """Move to the next search match."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        self._goto_match()

    def _search_prev(self) -> None:
        """Move to the previous search match."""
        if not self._search_matches:
            return
        self._search_index = (self._search_index - 1) % len(self._search_matches)
        self._goto_match()

    def _goto_match(self) -> None:
        """Scroll to the current search match and update the counter."""
        if self._search_index < 0 or self._search_index >= len(self._search_matches):
            return
        pos = self._search_matches[self._search_index]
        text = self._search_input.text()
        cursor = self._body_edit.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
        self._body_edit.setTextCursor(cursor)
        self._body_edit.ensureCursorVisible()
        total = len(self._search_matches)
        self._search_count_label.setText(f"{self._search_index + 1} of {total}")

    def _clear_highlights(self) -> None:
        """Remove all search highlight formatting from the body."""
        self._body_edit.set_search_selections([])

    # -- Filter handlers -----------------------------------------------

    def _toggle_filter(self) -> None:
        """Show or hide the filter bar.

        Hiding the bar does **not** clear an active filter — the user
        must click the explicit *Clear* button to restore the original
        body.  This avoids an expensive re-format of large responses
        when simply closing the bar.
        """
        if not self._filter_bar.isHidden():
            self._filter_bar.hide()
            self._filter_btn.setChecked(False)
        else:
            self._filter_bar.show()
            self._filter_btn.setChecked(True)
            self._update_filter_placeholder()
            self._filter_input.setFocus()

    def _update_filter_placeholder(self) -> None:
        """Set the filter input placeholder based on the current body language."""
        lang = self._body_edit.language if hasattr(self._body_edit, "language") else ""
        fmt = self._format_combo.currentText()
        if fmt in ("XML", "HTML") or lang == "xml":
            self._filter_input.setPlaceholderText("Filter using XPath: //item")
        else:
            self._filter_input.setPlaceholderText("Filter using JSONPath: $.store.books")

    def _apply_filter(self) -> None:
        """Evaluate the filter expression and display matching results."""
        expr = self._filter_input.text().strip()
        if not expr:
            return

        self._filter_error_label.hide()
        fmt = self._format_combo.currentText()
        body = self._raw_body

        # Pretty-print first if applicable so the filtered view is readable
        if fmt in ("Pretty", "JSON"):
            body = self._try_pretty_json(body)

        self._run_filter(expr, body)

    def _run_filter(self, expr: str, body: str) -> None:
        """Run *expr* against *body* and display results in the editor.

        Detects whether to use JSONPath or XPath based on the current
        format selection.  On success the filter state is activated;
        on error the error label is shown.
        """
        fmt = self._format_combo.currentText()
        is_xml = fmt in ("XML", "HTML")

        try:
            result = self._eval_xpath(expr, body) if is_xml else self._eval_jsonpath(expr, body)
        except Exception as exc:
            self._filter_error_label.setText(str(exc)[:120])
            self._filter_error_label.show()
            return

        if result is None:
            self._filter_error_label.setText("No matches")
            self._filter_error_label.show()
            return

        self._is_filtered = True
        self._filter_expression = expr
        self._filtered_body = result
        self._filter_error_label.hide()
        self._filter_apply_btn.hide()
        self._filter_clear_btn.show()
        self._body_edit.set_text(result)

    @staticmethod
    def _eval_jsonpath(expr: str, body: str) -> str | None:
        """Evaluate a JSONPath expression against a JSON *body* string.

        Returns the formatted result string or ``None`` when no matches
        are found.  Raises on parse or evaluation errors.
        """
        import json

        from jsonpath_ng import parse as jsonpath_parse  # type: ignore[import-untyped]

        data = json.loads(body)
        matches = jsonpath_parse(expr).find(data)
        if not matches:
            return None
        values = [m.value for m in matches]
        if len(values) == 1:
            return json.dumps(values[0], indent=4, ensure_ascii=False)
        return json.dumps(values, indent=4, ensure_ascii=False)

    @staticmethod
    def _eval_xpath(expr: str, body: str) -> str | None:
        """Evaluate an XPath expression against an XML/HTML *body* string.

        Returns the serialised result string or ``None`` when no matches
        are found.  Raises on parse or evaluation errors.
        """
        from lxml import etree

        root = etree.fromstring(body.encode("utf-8"))
        results = root.xpath(expr)
        if not results:
            return None
        parts: list[str] = []
        for node in results:
            if isinstance(node, etree._Element):
                parts.append(etree.tostring(node, pretty_print=True, encoding="unicode"))
            else:
                parts.append(str(node))
        return "\n".join(parts).rstrip()

    def _clear_filter(self) -> None:
        """Clear the active filter and restore the original body."""
        was_filtered = self._is_filtered
        self._is_filtered = False
        self._filter_expression = ""
        self._filtered_body = ""
        self._filter_error_label.hide()
        self._filter_clear_btn.hide()
        self._filter_apply_btn.show()
        if was_filtered:
            self._apply_body_format()
