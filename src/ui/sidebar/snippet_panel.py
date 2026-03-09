"""Code snippet panel for the right sidebar.

Inline replacement for the former :class:`CodeSnippetDialog`.  Embeds
a language selector, a read-only code editor, and a copy-to-clipboard
button directly inside the sidebar.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from services.http.snippet_generator import SnippetGenerator
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget

# Map snippet language labels to Pygments lexer names.
_LANG_TO_LEXER: dict[str, str] = {
    "cURL": "bash",
    "Python (requests)": "python",
    "JavaScript (fetch)": "javascript",
}


class SnippetPanel(QWidget):
    """Inline code snippet generator panel.

    Displays the current request as a code snippet in the user's
    chosen language.  Call :meth:`update_request` whenever the
    request editor state changes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the snippet panel with default empty state."""
        super().__init__(parent)

        self._method = ""
        self._url = ""
        self._headers: str | None = None
        self._body: str | None = None
        self._auth: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(6)

        # Language selector row
        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(0, 0, 0, 0)
        selector_row.setSpacing(6)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(SnippetGenerator.available_languages())
        self._lang_combo.setFixedHeight(28)
        self._lang_combo.currentTextChanged.connect(self._refresh)
        selector_row.addWidget(self._lang_combo, 1)

        self._copy_btn = QPushButton()
        self._copy_btn.setIcon(phi("clipboard"))
        self._copy_btn.setObjectName("iconButton")
        self._copy_btn.setFixedSize(28, 28)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setToolTip("Copy to clipboard")
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        selector_row.addWidget(self._copy_btn)

        layout.addLayout(selector_row)

        # Code editor (read-only)
        self._code_edit = CodeEditorWidget(read_only=True)
        self._code_edit.setMinimumHeight(120)
        layout.addWidget(self._code_edit, 1)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setObjectName("mutedLabel")
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update_request(
        self,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
        auth: dict | None = None,
    ) -> None:
        """Update the stored request data and regenerate the snippet."""
        self._method = method
        self._url = url
        self._headers = headers
        self._body = body
        self._auth = auth
        self._refresh()

    def clear(self) -> None:
        """Reset the panel to an empty state."""
        self._method = ""
        self._url = ""
        self._headers = None
        self._body = None
        self._auth = None
        self._code_edit.set_text("")
        self._status_label.setText("")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        """Regenerate the snippet for the selected language."""
        if not self._url:
            self._code_edit.set_text("")
            return
        lang = self._lang_combo.currentText()
        snippet = SnippetGenerator.generate(
            lang,
            method=self._method,
            url=self._url,
            headers=self._headers,
            body=self._body,
            auth=self._auth,
        )
        lexer = _LANG_TO_LEXER.get(lang, "text")
        self._code_edit.set_language(lexer)
        self._code_edit.set_text(snippet)
        self._status_label.setText("")

    def _copy_to_clipboard(self) -> None:
        """Copy the current snippet text to the system clipboard."""
        clipboard: QClipboard | None = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code_edit.toPlainText())
        self._status_label.setText("Copied!")
        self._status_label.setText("Copied!")
