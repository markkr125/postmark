"""Search and filter mixin for the saved responses panel body editor."""

from __future__ import annotations

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QTextEdit, QWidget

from ui.styling.theme import COLOR_WARNING
from ui.widgets.code_editor import CodeEditorWidget


class _PanelSearchFilterMixin:
    """Mixin that adds body search and filter methods to SavedResponsesPanel.

    Expects the host class to provide:

    - ``_body_edit: CodeEditorWidget``
    - ``_body_language: str``
    - ``_body_raw_text: str``
    - ``_body_view_mode: str``
    - ``_body_filter_btn: QPushButton``
    - ``_body_search_btn: QPushButton``
    - ``_filter_bar: QWidget``
    - ``_filter_input: QLineEdit``
    - ``_filter_error_label: QLabel``
    - ``_filter_apply_btn: QPushButton``
    - ``_filter_clear_btn: QPushButton``
    - ``_search_bar: QWidget``
    - ``_search_input: QLineEdit``
    - ``_search_count_label: QLabel``
    - ``_search_matches: list[int]``
    - ``_search_index: int``
    - ``_is_filtered: bool``
    - ``_filter_expression: str``
    - ``_refresh_body_view()``
    """

    # -- type stubs for mypy ------------------------------------------
    _body_edit: CodeEditorWidget
    _body_language: str
    _body_raw_text: str
    _body_view_mode: str
    _body_filter_btn: QPushButton
    _body_search_btn: QPushButton
    _filter_bar: QWidget
    _filter_input: QLineEdit
    _filter_error_label: QLabel
    _filter_apply_btn: QPushButton
    _filter_clear_btn: QPushButton
    _search_bar: QWidget
    _search_input: QLineEdit
    _search_count_label: QLabel
    _search_matches: list[int]
    _search_index: int
    _is_filtered: bool
    _filter_expression: str

    def _refresh_body_view(self, _mode: str | None = None) -> None: ...

    # -- Search --------------------------------------------------------

    def _reset_search_filter(self) -> None:
        """Reset search and filter UI state to defaults."""
        self._close_search()
        self._is_filtered = False
        self._filter_expression = ""
        self._filter_bar.hide()
        self._body_filter_btn.setChecked(False)
        self._filter_input.clear()
        self._filter_error_label.hide()
        self._filter_clear_btn.hide()
        self._filter_apply_btn.show()

    def _toggle_search(self) -> None:
        """Show or hide the body search bar."""
        if not self._search_bar.isHidden():
            self._close_search()
        else:
            self._search_bar.show()
            self._body_search_btn.setChecked(True)
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _close_search(self) -> None:
        """Hide the search bar and clear highlights."""
        self._search_bar.hide()
        self._body_search_btn.setChecked(False)
        self._search_input.clear()
        self._body_edit.set_search_selections([])

    def _on_search_text_changed(self, text: str) -> None:
        """Highlight all occurrences of *text* in the body."""
        self._body_edit.set_search_selections([])
        self._search_matches = []
        self._search_index = -1

        if not text:
            self._search_count_label.setText("")
            return

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

    # -- Filter --------------------------------------------------------

    def _toggle_filter(self) -> None:
        """Show or hide the filter bar."""
        if not self._filter_bar.isHidden():
            self._filter_bar.hide()
            self._body_filter_btn.setChecked(False)
        else:
            self._filter_bar.show()
            self._body_filter_btn.setChecked(True)
            self._update_filter_placeholder()
            self._filter_input.setFocus()

    def _update_filter_placeholder(self) -> None:
        """Set the filter input placeholder based on the body language."""
        lang = self._body_language or "text"
        if lang in ("xml", "html"):
            self._filter_input.setPlaceholderText("Filter using XPath: //item")
        else:
            self._filter_input.setPlaceholderText("Filter using JSONPath: $.store.books")

    def _apply_filter(self) -> None:
        """Evaluate the filter expression and display matching results."""
        from ui.sidebar.saved_responses.helpers import format_code_text

        expr = self._filter_input.text().strip()
        if not expr:
            return

        self._filter_error_label.hide()
        body = self._body_raw_text
        if self._body_view_mode == "Pretty":
            body = format_code_text(body, self._body_language or "text", pretty=True)

        self._run_filter(expr, body)

    def _run_filter(self, expr: str, body: str) -> None:
        """Run *expr* against *body* and display results in the editor."""
        is_xml = self._body_language in ("xml", "html")

        try:
            result = _eval_xpath(expr, body) if is_xml else _eval_jsonpath(expr, body)
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
        self._filter_error_label.hide()
        self._filter_apply_btn.hide()
        self._filter_clear_btn.show()
        self._body_edit.set_text(result)

    def _clear_filter(self) -> None:
        """Clear the active filter and restore the original body."""
        was_filtered = self._is_filtered
        self._is_filtered = False
        self._filter_expression = ""
        self._filter_error_label.hide()
        self._filter_clear_btn.hide()
        self._filter_apply_btn.show()
        if was_filtered:
            self._refresh_body_view()


# -- Standalone filter evaluators (not methods) -------------------------


def _eval_jsonpath(expr: str, body: str) -> str | None:
    """Evaluate a JSONPath expression against a JSON *body* string."""
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


def _eval_xpath(expr: str, body: str) -> str | None:
    """Evaluate an XPath expression against an XML/HTML *body* string."""
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
