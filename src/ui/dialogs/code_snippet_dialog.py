"""Dialog for viewing and copying HTTP request code snippets.

Shows generated code for the current request in various languages
(cURL, Python, JavaScript).
"""

from __future__ import annotations

from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.snippet_generator import SnippetGenerator
from ui.theme import COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_WHITE


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
        lang_label.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 12px;")
        top_row.addWidget(lang_label)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(SnippetGenerator.available_languages())
        self._lang_combo.setFixedWidth(200)
        self._lang_combo.setStyleSheet(
            f"""
            QComboBox {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                padding: 4px 8px;
                color: {COLOR_TEXT};
            }}
            """
        )
        self._lang_combo.currentTextChanged.connect(self._refresh)
        top_row.addWidget(self._lang_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Code display
        self._code_edit = QTextEdit()
        self._code_edit.setReadOnly(True)
        self._code_edit.setStyleSheet(
            f"""
            QTextEdit {{
                background: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                font-family: monospace;
                font-size: 12px;
                color: {COLOR_TEXT};
            }}
            """
        )
        layout.addWidget(self._code_edit, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._copy_btn = QPushButton("Copy to Clipboard")
        self._copy_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {COLOR_ACCENT};
                color: {COLOR_WHITE};
                border: none;
                padding: 6px 16px;
                font-weight: bold;
                border-radius: 3px;
            }}
            """
        )
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(self._copy_btn)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px; min-width: 80px;"
        )
        btn_row.addWidget(self._status_label)

        layout.addLayout(btn_row)

        # Generate initial snippet
        self._refresh()

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
        self._code_edit.setPlainText(snippet)
        self._status_label.setText("")

    def _copy_to_clipboard(self) -> None:
        """Copy the current snippet text to the system clipboard."""
        clipboard: QClipboard | None = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code_edit.toPlainText())
        self._status_label.setText("Copied!")
