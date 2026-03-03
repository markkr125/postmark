"""Dialog for viewing and copying HTTP request code snippets.

Shows generated code for the current request in various languages
(cURL, Python, JavaScript).
"""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.snippet_generator import SnippetGenerator
from ui.code_editor import CodeEditorWidget
from ui.icons import phi


class CodeSnippetDialog(QDialog):
    """Modal dialog displaying code snippets for a request.

    Instantiate with the request parameters and call :meth:`exec`.
    """

    def __init__(
        self,
        *,
        method: str,
        url: str,
        headers: str | None = None,
        body: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the code snippet dialog."""
        super().__init__(parent)
        self.setWindowTitle("Code Snippet")
        self.resize(600, 400)
        self.setModal(True)

        self._method = method
        self._url = url
        self._headers = headers
        self._body = body

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Language selector
        top_row = QHBoxLayout()
        lang_label = QLabel("Language:")
        lang_label.setObjectName("sectionLabel")
        top_row.addWidget(lang_label)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(SnippetGenerator.available_languages())
        self._lang_combo.setFixedWidth(200)
        self._lang_combo.currentTextChanged.connect(self._refresh)
        top_row.addWidget(self._lang_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Code display
        self._code_edit = CodeEditorWidget(read_only=True)
        layout.addWidget(self._code_edit, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._copy_btn = QPushButton("Copy to Clipboard")
        self._copy_btn.setIcon(phi("clipboard"))
        self._copy_btn.setObjectName("primaryButton")
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(self._copy_btn)

        self._status_label = QLabel("")
        self._status_label.setObjectName("mutedLabel")
        btn_row.addWidget(self._status_label)

        layout.addLayout(btn_row)

        # Generate initial snippet
        self._refresh()

    # -- Language to code-editor language mapping ----------------------

    _LANG_MAP: ClassVar[dict[str, str]] = {
        "cURL": "text",
        "Python - requests": "text",
        "Python - http.client": "text",
        "JavaScript - fetch": "text",
        "JavaScript - axios": "text",
    }

    def _refresh(self) -> None:
        """Regenerate the code snippet for the selected language."""
        lang = self._lang_combo.currentText()
        snippet = SnippetGenerator.generate(
            lang,
            method=self._method,
            url=self._url,
            headers=self._headers,
            body=self._body,
        )
        editor_lang = self._LANG_MAP.get(lang, "text")
        self._code_edit.set_language(editor_lang)
        self._code_edit.set_text(snippet)
        self._status_label.setText("")

    def _copy_to_clipboard(self) -> None:
        """Copy the current snippet text to the system clipboard."""
        clipboard: QClipboard | None = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code_edit.toPlainText())
        self._status_label.setText("Copied!")
