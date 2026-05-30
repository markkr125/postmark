"""Tests for the declarative Assertions tab."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QWidget,
)

from services.scripting.assertions_compiler import SUBJECT_SUGGESTIONS
from ui.request.request_editor.assertions.assertions_guide import AssertionsHelpDialog
from ui.request.request_editor.assertions.assertions_tab import AssertionsTab


class TestAssertionsTab:
    """Assertions table and help dialog."""

    def test_help_row_heading_and_button(self, qapp: QApplication, qtbot) -> None:
        """The tab shows the heading and a How it works button above the table."""
        tab = AssertionsTab()
        qtbot.addWidget(tab)
        row = tab.findChild(QWidget, "assertionsHelpRow")
        assert row is not None
        headings = [
            label.text()
            for label in row.findChildren(QLabel)
            if label.text() == "Response checks without script code"
        ]
        assert headings
        btn = row.findChild(QPushButton, "assertionsHowItWorksButton")
        assert btn is not None
        assert btn.text() == "How it works"
        tab.show()
        assert btn.isVisibleTo(tab)

    def test_help_dialog_selectable_body(self, qapp: QApplication, qtbot) -> None:
        """Help dialog body is selectable rich text."""
        dialog = AssertionsHelpDialog()
        qtbot.addWidget(dialog)
        browser = dialog.findChild(QTextBrowser, "assertionsHelpBody")
        assert browser is not None
        assert "Declarative Assertions" in browser.toHtml()
        flags = browser.textInteractionFlags()
        assert flags & Qt.TextInteractionFlag.TextSelectableByMouse

    def test_help_button_opens_dialog(
        self,
        qapp: QApplication,
        qtbot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Clicking How it works opens the explanation dialog."""
        opened: list[AssertionsHelpDialog] = []

        def record_exec(self: AssertionsHelpDialog) -> int:
            opened.append(self)
            return int(QDialog.DialogCode.Accepted)

        monkeypatch.setattr(AssertionsHelpDialog, "exec", record_exec)

        tab = AssertionsTab()
        qtbot.addWidget(tab)
        btn = tab.findChild(QPushButton, "assertionsHowItWorksButton")
        assert btn is not None
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert len(opened) == 1

    def test_subject_field_has_suggestions(self, qapp: QApplication, qtbot) -> None:
        """Subject inputs offer auto-complete covering every supported field kind."""
        tab = AssertionsTab()
        qtbot.addWidget(tab)
        tab.set_rows([])
        subject = tab.findChild(QLineEdit, "assertionSubjectEdit")
        assert subject is not None
        completer = subject.completer()
        assert completer is not None
        model = completer.model()
        assert model is not None
        suggestions = {model.index(i, 0).data() for i in range(model.rowCount())}
        assert "res.status" in suggestions
        assert "res.time" in suggestions
        assert "res.body" in suggestions
        assert any(s.startswith("res.headers[") for s in suggestions)

    def test_subject_suggestions_cover_kinds(self) -> None:
        """The shared suggestion list spans status, time, body, JSON path, headers."""
        assert "res.status" in SUBJECT_SUGGESTIONS
        assert "res.time" in SUBJECT_SUGGESTIONS
        assert "res.body" in SUBJECT_SUGGESTIONS
        assert "res.body." in SUBJECT_SUGGESTIONS
        assert any(s.startswith('res.headers["') for s in SUBJECT_SUGGESTIONS)
