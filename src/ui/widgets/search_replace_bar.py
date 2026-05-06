"""Standalone search / replace bar for ``CodeEditorWidget``.

Provides a toggleable ``SearchReplaceBar`` that attaches to any
:class:`~ui.widgets.code_editor.CodeEditorWidget` and handles
find, highlight, navigation, replacement, and go-to-line.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.styling.icons import phi
from ui.styling.theme import COLOR_WARNING
from ui.widgets.code_editor import CodeEditorWidget


class SearchReplaceBar(QWidget):
    """Find / replace bar for a script ``CodeEditorWidget``.

    Parameters
    ----------
    editor:
        The editor to search.
    parent:
        Parent widget (for script tabs, pass the **editor pane** that contains
        this bar and the ``CodeEditorWidget`` so **Ctrl+P** parameter hints are
        registered on the pane and still work while the find field has focus).
    """

    def __init__(self, editor: CodeEditorWidget, parent: QWidget | None = None) -> None:
        """Build the hidden search/replace bar and wire shortcuts."""
        super().__init__(parent)
        self._editor = editor
        self._matches: list[int] = []
        self._match_index: int = -1
        self._pane_parameter_hint_sc: QShortcut | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

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

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Find\u2026")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.returnPressed.connect(self._search_next)
        search_row.addWidget(self._search_input, 1)

        self._count_label = QLabel()
        self._count_label.setObjectName("mutedLabel")
        self._count_label.setFixedWidth(70)
        search_row.addWidget(self._count_label)

        prev_btn = QPushButton()
        prev_btn.setIcon(phi("caret-up"))
        prev_btn.setFixedSize(22, 22)
        prev_btn.setObjectName("iconButton")
        prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prev_btn.clicked.connect(self._search_prev)
        search_row.addWidget(prev_btn)

        next_btn = QPushButton()
        next_btn.setIcon(phi("caret-down"))
        next_btn.setFixedSize(22, 22)
        next_btn.setObjectName("iconButton")
        next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.clicked.connect(self._search_next)
        search_row.addWidget(next_btn)

        close_btn = QPushButton()
        close_btn.setIcon(phi("x"))
        close_btn.setFixedSize(22, 22)
        close_btn.setObjectName("iconButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close_search)
        search_row.addWidget(close_btn)

        layout.addLayout(search_row)

        # -- Replace row (hidden by default) ---------------------------
        self._replace_row = QWidget()
        replace_layout = QHBoxLayout(self._replace_row)
        replace_layout.setContentsMargins(26, 0, 0, 0)
        replace_layout.setSpacing(4)

        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replace\u2026")
        replace_layout.addWidget(self._replace_input, 1)

        # Spacer matching the count label above
        _count_spacer = QWidget()
        _count_spacer.setFixedWidth(70)
        replace_layout.addWidget(_count_spacer)

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

        # Spacer matching the close button above
        _close_spacer = QWidget()
        _close_spacer.setFixedWidth(22)
        replace_layout.addWidget(_close_spacer)

        self._replace_row.hide()
        layout.addWidget(self._replace_row)

        self.hide()
        self._install_shortcuts()

    # -- Shortcuts (scoped to the editor) ------------------------------

    def _install_shortcuts(self) -> None:
        """Install platform-native Find, Replace, and Go-to-Line shortcuts."""
        find_sc = QShortcut(QKeySequence.StandardKey.Find, self._editor)
        find_sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        find_sc.activated.connect(self.toggle_search)

        replace_sc = QShortcut(QKeySequence.StandardKey.Replace, self._editor)
        replace_sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        replace_sc.activated.connect(self.toggle_replace)

        goto_sc = QShortcut(QKeySequence("Ctrl+G"), self._editor)
        goto_sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        goto_sc.activated.connect(self.goto_line)

        # Ctrl+P must work while the find field has focus (sibling of the editor).
        hub = self.parentWidget()
        if hub is not None:
            self._pane_parameter_hint_sc = QShortcut(QKeySequence("Ctrl+P"), hub)
            self._pane_parameter_hint_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self._pane_parameter_hint_sc.activated.connect(self._editor.trigger_parameter_hint)

    # -- Public API ----------------------------------------------------

    def toggle_search(self) -> None:
        """Show the search bar, or close it if already visible."""
        if not self.isHidden():
            self.close_search()
            return
        self.show()
        self._search_input.setFocus()
        self._search_input.selectAll()

    def toggle_replace(self) -> None:
        """Show the search bar with the replace row visible."""
        if self.isHidden():
            self.show()
        self._replace_row.show()
        self._replace_toggle_btn.setChecked(True)
        self._replace_toggle_btn.setIcon(phi("caret-down"))
        self._search_input.setFocus()
        self._search_input.selectAll()

    def close_search(self) -> None:
        """Hide the bar, clear highlights, and reset state."""
        self.hide()
        self._search_input.clear()
        self._replace_input.clear()
        self._replace_row.hide()
        self._replace_toggle_btn.setChecked(False)
        self._replace_toggle_btn.setIcon(phi("caret-right"))
        self._matches = []
        self._match_index = -1
        self._editor.set_search_selections([])
        self._editor.setFocus()

    def goto_line(self) -> None:
        """Show a go-to-line dialog and jump to the chosen line."""
        total = self._editor.blockCount()
        line, ok = QInputDialog.getInt(
            self._editor,
            "Go to Line",
            f"Line number (1\u2013{total}):",
            value=self._editor.textCursor().blockNumber() + 1,
            minValue=1,
            maxValue=total,
        )
        if ok:
            block = self._editor.document().findBlockByNumber(line - 1)
            cursor = QTextCursor(block)
            self._editor.setTextCursor(cursor)
            self._editor.centerCursor()
            self._editor.setFocus()

    # -- Internal toggle -----------------------------------------------

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

    def _on_search_changed(self, text: str) -> None:
        """Re-search when the input text changes."""
        self._editor.set_search_selections([])
        self._matches = []
        self._match_index = -1

        if not text:
            self._count_label.setText("")
            return

        body = self._editor.toPlainText()
        start = 0
        while True:
            idx = body.find(text, start)
            if idx == -1:
                break
            self._matches.append(idx)
            start = idx + 1

        if not self._matches:
            self._count_label.setText("No results")
            return

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(COLOR_WARNING))
        selections: list[QTextEdit.ExtraSelection] = []
        for pos in self._matches:
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(self._editor.document())
            cur.setPosition(pos)
            cur.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        self._editor.set_search_selections(selections)

        self._match_index = 0
        self._goto_match()

    def _search_next(self) -> None:
        """Move to the next match with wrap-around."""
        if not self._matches:
            return
        self._match_index = (self._match_index + 1) % len(self._matches)
        self._goto_match()

    def _search_prev(self) -> None:
        """Move to the previous match with wrap-around."""
        if not self._matches:
            return
        self._match_index = (self._match_index - 1) % len(self._matches)
        self._goto_match()

    def _goto_match(self) -> None:
        """Scroll to the current match and update the counter."""
        if self._match_index < 0 or self._match_index >= len(self._matches):
            return
        pos = self._matches[self._match_index]
        text = self._search_input.text()
        cursor = self._editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(text), QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
        total = len(self._matches)
        self._count_label.setText(f"{self._match_index + 1} of {total}")

    # -- Replace logic -------------------------------------------------

    def _replace_one(self) -> None:
        """Replace the current match and re-search."""
        if not self._matches or self._match_index < 0:
            return
        pos = self._matches[self._match_index]
        needle = self._search_input.text()
        replacement = self._replace_input.text()

        cursor = self._editor.textCursor()
        cursor.setPosition(pos)
        cursor.setPosition(pos + len(needle), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)
        self._on_search_changed(needle)

    def _replace_all(self) -> None:
        """Replace all matches at once and re-search."""
        if not self._matches:
            return
        needle = self._search_input.text()
        replacement = self._replace_input.text()

        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        for pos in reversed(self._matches):
            cursor.setPosition(pos)
            cursor.setPosition(pos + len(needle), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        cursor.endEditBlock()
        self._on_search_changed(needle)
