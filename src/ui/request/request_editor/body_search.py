"""Body search and replace mixin for the request editor.

Provides ``_BodySearchMixin`` with the find/replace bar UI construction
and all search, navigation, and replacement methods.  Mixed into
``RequestEditorWidget``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_WARNING
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.key_value_table import KeyValueTableWidget

# Body mode identifiers (must match editor_widget._BODY_MODES order)
_BODY_MODES = ("none", "raw", "form-data", "x-www-form-urlencoded", "graphql", "binary")

# Raw body format sub-options
_RAW_FORMATS = ("Text", "JSON", "XML", "HTML")


class _BodySearchMixin:
    """Mixin that adds body-tab construction and find/replace.

    Expects the host class to provide ``_on_field_changed``,
    ``_on_body_mode_changed``, ``_on_prettify``, ``_on_wrap_toggle``,
    ``_update_body_language``, ``_on_body_validation``,
    ``_on_select_binary_file``, and ``_build_graphql_page`` attributes.
    """

    # -- Host-class interface (declared for mypy) -----------------------
    _body_code_editor: CodeEditorWidget
    _body_mode_buttons: dict

    def _on_field_changed(self) -> None: ...
    def _on_body_mode_changed(self, checked: bool) -> None: ...
    def _on_prettify(self) -> None: ...
    def _on_wrap_toggle(self) -> None: ...
    def _update_body_language(self) -> None: ...
    def _on_body_validation(self, errors: list) -> None: ...
    def _on_select_binary_file(self) -> None: ...

    _build_graphql_page: Callable[[], QWidget]

    # -- Body tab construction (called from __init__) -------------------

    def _build_body_tab(self, body_layout: QVBoxLayout) -> None:
        """Construct the body tab contents: mode radios, search bar, stack."""
        # Body mode radio buttons
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self._body_mode_group = QButtonGroup(cast(QObject, self))
        self._body_mode_buttons: dict[str, QRadioButton] = {}
        for mode in _BODY_MODES:
            rb = QRadioButton(mode)
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            self._body_mode_buttons[mode] = rb
            self._body_mode_group.addButton(rb)
            mode_row.addWidget(rb)
            rb.toggled.connect(self._on_body_mode_changed)
        self._body_mode_buttons["none"].setChecked(True)
        mode_row.addStretch()
        body_layout.addLayout(mode_row)

        # Find / replace bar
        self._body_search_bar = self._build_search_bar()
        body_layout.addWidget(self._body_search_bar)

        # Body content stack (switches per mode)
        self._body_stack = QStackedWidget()

        # Page 0: None mode
        none_page = QLabel("This request has no body.")
        none_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        none_page.setObjectName("emptyStateLabel")
        self._body_stack.addWidget(none_page)

        # Page 1: Raw \u2014 code editor with toolbar
        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(4)

        raw_toolbar = QHBoxLayout()
        raw_toolbar.setSpacing(6)
        self._prettify_btn = QPushButton("Pretty")
        self._prettify_btn.setIcon(phi("magic-wand", color="#ffffff"))
        self._prettify_btn.setObjectName("smallPrimaryButton")
        self._prettify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prettify_btn.clicked.connect(self._on_prettify)
        raw_toolbar.addWidget(self._prettify_btn)

        self._wrap_btn = QPushButton("Wrap")
        self._wrap_btn.setIcon(phi("text-align-left"))
        self._wrap_btn.setObjectName("outlineButton")
        self._wrap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wrap_btn.setCheckable(True)
        self._wrap_btn.setChecked(True)
        self._wrap_btn.clicked.connect(self._on_wrap_toggle)
        raw_toolbar.addWidget(self._wrap_btn)

        self._raw_format_combo = QComboBox()
        self._raw_format_combo.addItems(list(_RAW_FORMATS))
        self._raw_format_combo.setFixedWidth(80)
        self._raw_format_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._raw_format_combo.currentTextChanged.connect(self._on_field_changed)
        self._raw_format_combo.currentTextChanged.connect(self._update_body_language)
        self._raw_format_combo.hide()
        raw_toolbar.addWidget(self._raw_format_combo)

        self._body_error_label = QLabel()
        self._body_error_label.setObjectName("mutedLabel")
        self._body_error_label.hide()
        raw_toolbar.addWidget(self._body_error_label)
        raw_toolbar.addStretch()
        raw_layout.addLayout(raw_toolbar)

        self._body_code_editor = CodeEditorWidget()
        self._body_code_editor.textChanged.connect(self._on_field_changed)
        self._body_code_editor.validation_changed.connect(self._on_body_validation)
        raw_layout.addWidget(self._body_code_editor, 1)
        self._body_stack.addWidget(raw_page)

        # Page 2: form-data / x-www-form-urlencoded
        self._body_form_table = KeyValueTableWidget(
            placeholder_key="Key", placeholder_value="Value"
        )
        self._body_form_table.data_changed.connect(self._on_field_changed)
        self._body_stack.addWidget(self._body_form_table)

        # Page 3: Binary \u2014 file picker
        binary_page = QWidget()
        binary_layout = QVBoxLayout(binary_page)
        binary_layout.setContentsMargins(0, 8, 0, 0)
        self._binary_file_btn = QPushButton("Select File")
        self._binary_file_btn.setIcon(phi("file"))
        self._binary_file_btn.setObjectName("outlineButton")
        self._binary_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._binary_file_btn.setFixedWidth(120)
        self._binary_file_btn.clicked.connect(self._on_select_binary_file)
        binary_layout.addWidget(self._binary_file_btn)
        self._binary_file_label = QLabel("No file selected.")
        self._binary_file_label.setObjectName("mutedLabel")
        binary_layout.addWidget(self._binary_file_label)
        binary_layout.addStretch()
        self._body_stack.addWidget(binary_page)

        # Page 4: GraphQL (from _GraphQLMixin)
        gql_page = self._build_graphql_page()
        self._body_stack.addWidget(gql_page)

        body_layout.addWidget(self._body_stack, 1)

    # -- UI construction (called from _build_body_tab) ------------------

    def _build_search_bar(self) -> QWidget:
        """Build and return the hidden find/replace bar widget.

        Creates a search row with input, prev/next/close buttons,
        and a collapsible replace row with replace-one and replace-all.
        """
        bar = QWidget()
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(0, 4, 0, 4)
        bar_layout.setSpacing(2)

        # -- Search row ------------------------------------------------
        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self._replace_toggle_btn = QPushButton()
        self._replace_toggle_btn.setIcon(phi("caret-right"))
        self._replace_toggle_btn.setFixedSize(22, 22)
        self._replace_toggle_btn.setCheckable(True)
        self._replace_toggle_btn.setObjectName("iconButton")
        self._replace_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replace_toggle_btn.clicked.connect(self._toggle_replace_row)
        search_row.addWidget(self._replace_toggle_btn)

        self._body_search_input = QLineEdit()
        self._body_search_input.setPlaceholderText("Find in body\u2026")
        self._body_search_input.textChanged.connect(self._on_body_search_changed)
        search_row.addWidget(self._body_search_input, 1)

        self._body_search_count_label = QLabel()
        self._body_search_count_label.setObjectName("mutedLabel")
        self._body_search_count_label.setFixedWidth(70)
        search_row.addWidget(self._body_search_count_label)

        prev_btn = QPushButton()
        prev_btn.setIcon(phi("caret-up"))
        prev_btn.setFixedSize(22, 22)
        prev_btn.setObjectName("iconButton")
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.clicked.connect(self._body_search_prev)
        search_row.addWidget(prev_btn)

        next_btn = QPushButton()
        next_btn.setIcon(phi("caret-down"))
        next_btn.setFixedSize(22, 22)
        next_btn.setObjectName("iconButton")
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(self._body_search_next)
        search_row.addWidget(next_btn)

        close_btn = QPushButton()
        close_btn.setIcon(phi("x"))
        close_btn.setFixedSize(22, 22)
        close_btn.setObjectName("iconButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._close_body_search)
        search_row.addWidget(close_btn)

        bar_layout.addLayout(search_row)

        # -- Replace row (hidden by default) ---------------------------
        self._replace_row = QWidget()
        replace_layout = QHBoxLayout(self._replace_row)
        replace_layout.setContentsMargins(26, 0, 0, 0)  # align with search input
        replace_layout.setSpacing(4)

        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replace\u2026")
        replace_layout.addWidget(self._replace_input, 1)

        replace_one_btn = QPushButton()
        replace_one_btn.setIcon(phi("swap"))
        replace_one_btn.setFixedSize(22, 22)
        replace_one_btn.setObjectName("iconButton")
        replace_one_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        replace_one_btn.setToolTip("Replace current match")
        replace_one_btn.clicked.connect(self._replace_one)
        replace_layout.addWidget(replace_one_btn)

        replace_all_btn = QPushButton()
        replace_all_btn.setIcon(phi("list-checks"))
        replace_all_btn.setFixedSize(22, 22)
        replace_all_btn.setObjectName("iconButton")
        replace_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        replace_all_btn.setToolTip("Replace all matches")
        replace_all_btn.clicked.connect(self._replace_all)
        replace_layout.addWidget(replace_all_btn)

        self._replace_row.hide()
        bar_layout.addWidget(self._replace_row)

        # Search state
        self._body_search_matches: list[int] = []
        self._body_search_index: int = -1

        bar.hide()
        return bar

    # -- Toggle / close ------------------------------------------------

    def _toggle_body_search(self) -> None:
        """Show or hide the body search bar.

        Does nothing when the body mode is ``none`` (no body to search).
        """
        from PySide6.QtWidgets import QRadioButton

        if self._body_mode_buttons.get("none", QRadioButton()).isChecked():
            return

        if not self._body_search_bar.isHidden():
            self._close_body_search()
        else:
            self._body_search_bar.show()
            self._body_search_input.setFocus()
            self._body_search_input.selectAll()

    def _toggle_body_replace(self) -> None:
        """Open the search bar with the replace row visible."""
        from PySide6.QtWidgets import QRadioButton

        if self._body_mode_buttons.get("none", QRadioButton()).isChecked():
            return

        if self._body_search_bar.isHidden():
            self._body_search_bar.show()
        self._replace_row.show()
        self._replace_toggle_btn.setChecked(True)
        self._replace_toggle_btn.setIcon(phi("caret-down"))
        self._body_search_input.setFocus()
        self._body_search_input.selectAll()

    def _close_body_search(self) -> None:
        """Hide the search bar, clear highlights and reset state."""
        self._body_search_bar.hide()
        self._body_search_input.clear()
        self._replace_input.clear()
        self._replace_row.hide()
        self._replace_toggle_btn.setChecked(False)
        self._replace_toggle_btn.setIcon(phi("caret-right"))
        self._body_search_matches = []
        self._body_search_index = -1
        self._body_code_editor.set_search_selections([])

    def _toggle_replace_row(self) -> None:
        """Toggle the replace row visibility."""
        if self._replace_row.isHidden():
            self._replace_row.show()
            self._replace_toggle_btn.setChecked(True)
            self._replace_toggle_btn.setIcon(phi("caret-down"))
        else:
            self._replace_row.hide()
            self._replace_toggle_btn.setChecked(False)
            self._replace_toggle_btn.setIcon(phi("caret-right"))

    # -- Search logic --------------------------------------------------

    def _on_body_search_changed(self, text: str) -> None:
        """Re-search when the search input text changes."""
        self._body_code_editor.set_search_selections([])
        self._body_search_matches = []
        self._body_search_index = -1

        if not text:
            self._body_search_count_label.setText("")
            return

        body_text = self._body_code_editor.toPlainText()
        start = 0
        while True:
            idx = body_text.find(text, start)
            if idx == -1:
                break
            self._body_search_matches.append(idx)
            start = idx + 1

        if not self._body_search_matches:
            self._body_search_count_label.setText("No results")
            return

        # Highlight all matches
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_WARNING))
        selections: list[QTextEdit.ExtraSelection] = []
        for pos in self._body_search_matches:
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(self._body_code_editor.document())
            cur.setPosition(pos)
            cur.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        self._body_code_editor.set_search_selections(selections)

        self._body_search_index = 0
        self._goto_body_match()

    def _body_search_next(self) -> None:
        """Move to the next search match, wrapping around."""
        if not self._body_search_matches:
            return
        self._body_search_index = (self._body_search_index + 1) % len(self._body_search_matches)
        self._goto_body_match()

    def _body_search_prev(self) -> None:
        """Move to the previous search match, wrapping around."""
        if not self._body_search_matches:
            return
        self._body_search_index = (self._body_search_index - 1) % len(self._body_search_matches)
        self._goto_body_match()

    def _goto_body_match(self) -> None:
        """Scroll to the current match and update the counter label."""
        if self._body_search_index < 0 or self._body_search_index >= len(self._body_search_matches):
            return
        pos = self._body_search_matches[self._body_search_index]
        text = self._body_search_input.text()
        cursor = self._body_code_editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
        self._body_code_editor.setTextCursor(cursor)
        self._body_code_editor.ensureCursorVisible()
        total = len(self._body_search_matches)
        self._body_search_count_label.setText(f"{self._body_search_index + 1} of {total}")

    # -- Replace logic -------------------------------------------------

    def _replace_one(self) -> None:
        """Replace the current match and re-search."""
        if not self._body_search_matches:
            return
        if self._body_search_index < 0:
            return
        pos = self._body_search_matches[self._body_search_index]
        needle = self._body_search_input.text()
        replacement = self._replace_input.text()

        cursor = self._body_code_editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(needle), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)

        # Re-search to refresh matches
        self._on_body_search_changed(needle)

    def _replace_all(self) -> None:
        """Replace every match at once and re-search."""
        if not self._body_search_matches:
            return
        needle = self._body_search_input.text()
        replacement = self._replace_input.text()

        # Replace in reverse order to preserve earlier positions
        cursor = self._body_code_editor.textCursor()
        cursor.beginEditBlock()
        for pos in reversed(self._body_search_matches):
            cursor.setPosition(pos)
            cursor.setPosition(pos + len(needle), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        cursor.endEditBlock()

        # Re-search (likely no matches remaining)
        self._on_body_search_changed(needle)
