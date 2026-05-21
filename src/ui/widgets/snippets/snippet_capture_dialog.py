"""Dialog to save editor selection as a user script snippet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from services.snippet_service import SnippetService


class SnippetCaptureDialog(QDialog):
    """Collect name, category, scope, and context for a new user snippet."""

    def __init__(
        self,
        *,
        body: str,
        language: str,
        script_type: str,
        collection_id: int | None = None,
        local_script_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Build the form; *body* is the selected editor text."""
        super().__init__(parent)
        self.setWindowTitle("Save as snippet")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._body = body
        self._language = language
        self._script_type = script_type
        self._collection_id = collection_id
        self._local_script_id = local_script_id
        self._saved_id: int | None = None

        root = QVBoxLayout(self)
        root.setSpacing(10)

        intro = QLabel("Save the selected text as a reusable snippet.")
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Snippet name")
        form.addRow("Name", self._name_edit)

        self._category_edit = QLineEdit()
        self._category_edit.setPlaceholderText("My snippets")
        form.addRow("Category", self._category_edit)

        self._context_combo = QComboBox()
        self._context_combo.addItem("Pre-request and post-response", "both")
        self._context_combo.addItem("Pre-request only", "pre")
        self._context_combo.addItem("Post-response only", "test")
        if script_type == "pre_request":
            self._context_combo.setCurrentIndex(1)
        elif script_type == "test":
            self._context_combo.setCurrentIndex(2)
        form.addRow("Context", self._context_combo)

        self._scope_combo = QComboBox()
        self._scope_combo.addItem("Global (all collections)", "global")
        if collection_id is not None:
            self._scope_combo.addItem("Current collection", "collection")
        if local_script_id is not None:
            self._scope_combo.addItem("Current local script", "local_script")
        if local_script_id is not None:
            self._scope_combo.setCurrentIndex(self._scope_combo.count() - 1)
        elif collection_id is not None:
            self._scope_combo.setCurrentIndex(1)
        form.addRow("Scope", self._scope_combo)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_btn is not None:
            save_btn.setObjectName("primaryButton")
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if cancel_btn is not None:
            cancel_btn.setObjectName("outlineButton")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @property
    def saved_snippet_id(self) -> int | None:
        """Return the new snippet id after a successful save, else ``None``."""
        return self._saved_id

    def _on_save(self) -> None:
        """Validate and persist via :class:`SnippetService`."""
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save as snippet", "Enter a snippet name.")
            return
        category = self._category_edit.text().strip() or "My snippets"
        context = str(self._context_combo.currentData() or "both")
        scope = str(self._scope_combo.currentData() or "global")
        scope_collection_id: int | None = None
        scope_local_script_id: int | None = None
        if scope == "collection":
            scope_collection_id = self._collection_id
        elif scope == "local_script":
            scope_local_script_id = self._local_script_id
        try:
            self._saved_id = SnippetService.create(
                name=name,
                language=self._language,
                body=self._body,
                category=category,
                context=context,
                scope_collection_id=scope_collection_id,
                scope_local_script_id=scope_local_script_id,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Save as snippet", str(exc))
            return
        self.accept()
