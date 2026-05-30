"""Dialog to create or edit user script snippets."""

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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.snippet_service import SnippetService, UserSnippetDict
from ui.widgets.code_editor import CodeEditorWidget

_STUB_JS = "// …"
_STUB_PY = "# …"
_LANG_JS = "javascript"
_LANG_TS = "typescript"
_LANG_PY = "python"

_DEFAULT_WIDTH = 720
_DEFAULT_HEIGHT = 580
_MIN_WIDTH = 640
_MIN_HEIGHT = 480
_BODY_MIN_HEIGHT = 280


def _stub_for_language(language: str) -> str:
    """Return the default body stub for sidebar create mode."""
    short = SnippetService.normalize_language(language)
    return _STUB_PY if short == "py" else _STUB_JS


def _language_display(short_code: str) -> str:
    """Map DB short code to a read-only label."""
    code = (short_code or "").lower().strip()
    labels = {"js": "JavaScript", "ts": "TypeScript", "py": "Python"}
    return labels.get(code, code)


class SnippetCaptureDialog(QDialog):
    """Collect snippet metadata; create from the editor, sidebar, or edit existing rows."""

    def __init__(
        self,
        *,
        body: str = "",
        language: str = "javascript",
        script_type: str = "pre_request",
        snippet_id: int | None = None,
        edit_row: UserSnippetDict | None = None,
        from_sidebar: bool = False,
        initial_category: str = "",
        parent: QWidget | None = None,
    ) -> None:
        """Build the form for editor-create, sidebar-create, or edit mode."""
        super().__init__(parent)
        self._snippet_id = snippet_id
        self._from_sidebar = from_sidebar
        self._is_edit = snippet_id is not None
        self._saved_id: int | None = snippet_id
        self._language = language
        self._edit_row = edit_row

        if self._is_edit and edit_row is not None:
            self._language = SnippetService.to_editor_language(str(edit_row["language"]))
            body = str(edit_row["body"])
        elif from_sidebar and not self._is_edit:
            body = _stub_for_language(language)

        self._body_fixed = body if not self._is_edit and not from_sidebar else ""

        self.setModal(True)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setWindowTitle(self._dialog_title())

        root = QVBoxLayout(self)
        root.setSpacing(10)

        if self._is_edit:
            intro_text = "Edit name, category, context, and body."
        elif from_sidebar:
            intro_text = "Create a reusable snippet."
        else:
            intro_text = "Save the selected text as a reusable snippet."
        intro = QLabel(intro_text)
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

        self._language_combo: QComboBox | None = None
        self._language_label: QLabel | None = None

        if from_sidebar and not self._is_edit:
            self._language_combo = QComboBox()
            self._language_combo.addItem("JavaScript", _LANG_JS)
            self._language_combo.addItem("TypeScript", _LANG_TS)
            self._language_combo.addItem("Python", _LANG_PY)
            norm = SnippetService.normalize_language(language)
            idx = {"js": 0, "ts": 1, "py": 2}.get(norm, 0)
            self._language_combo.setCurrentIndex(idx)
            self._language_combo.currentIndexChanged.connect(self._on_sidebar_language_changed)
            form.addRow("Language", self._language_combo)
        elif self._is_edit:
            short = str(edit_row["language"]) if edit_row is not None else language
            self._language_label = QLabel(_language_display(short))
            self._language_label.setObjectName("mutedLabel")
            form.addRow("Language", self._language_label)

        self._context_combo = QComboBox()
        self._context_combo.addItem("Pre-request and post-response", "both")
        self._context_combo.addItem("Pre-request only", "pre")
        self._context_combo.addItem("Post-response only", "test")
        if self._is_edit and edit_row is not None:
            self._apply_context_combo(str(edit_row.get("context") or "both"))
            self._name_edit.setText(str(edit_row["name"]))
            self._category_edit.setText(str(edit_row.get("category") or "My snippets"))
        elif script_type == "pre_request":
            self._context_combo.setCurrentIndex(1)
        elif script_type == "test":
            self._context_combo.setCurrentIndex(2)
        form.addRow("Context", self._context_combo)

        if from_sidebar and not self._is_edit and (initial_category or "").strip():
            self._category_edit.setText(initial_category.strip())

        root.addLayout(form)

        self._body_edit: CodeEditorWidget | None = None
        if self._is_edit or from_sidebar:
            body_label = QLabel("Body")
            body_label.setObjectName("sectionLabel")
            root.addWidget(body_label)

            self._body_edit = CodeEditorWidget(parent=self)
            self._body_edit.setMinimumHeight(_BODY_MIN_HEIGHT)
            self._body_edit.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._sync_body_editor_language()
            self._body_edit.setPlainText(body)
            root.addWidget(self._body_edit, 1)

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
        """Return the snippet id after a successful save, else ``None``."""
        return self._saved_id

    def _apply_context_combo(self, context: str) -> None:
        """Select the combo index for stored context *context*."""
        ctx = (context or "both").lower().strip()
        for i in range(self._context_combo.count()):
            if str(self._context_combo.itemData(i)) == ctx:
                self._context_combo.setCurrentIndex(i)
                return

    def _editor_language_for_body(self) -> str:
        """Return the :class:`CodeEditorWidget` language for the current mode."""
        if self._from_sidebar and not self._is_edit and self._language_combo is not None:
            return str(self._language_combo.currentData() or _LANG_JS)
        if self._is_edit and self._edit_row is not None:
            return SnippetService.to_editor_language(str(self._edit_row["language"]))
        return self._language

    def _sync_body_editor_language(self) -> None:
        """Apply syntax highlighting and completion schema for the snippet language."""
        if self._body_edit is None:
            return
        self._body_edit.set_language(self._editor_language_for_body())

    def _on_sidebar_language_changed(self, _index: int) -> None:
        """Update stub body and editor language when the language combo changes."""
        if self._body_edit is None or self._language_combo is None:
            return
        lang = str(self._language_combo.currentData() or _LANG_JS)
        self._sync_body_editor_language()
        self._body_edit.setPlainText(_stub_for_language(lang))

    def _resolved_language(self) -> str:
        """Language string passed to :class:`SnippetService`."""
        if self._from_sidebar and not self._is_edit and self._language_combo is not None:
            return str(self._language_combo.currentData() or _LANG_JS)
        return self._language

    def _resolved_body(self) -> str:
        """Body text for create/update."""
        if self._body_edit is not None:
            return self._body_edit.toPlainText()
        return self._body_fixed

    def _dialog_title(self) -> str:
        """Window / message-box title for the current mode."""
        return "Edit snippet" if self._is_edit else "Save as snippet"

    def _on_save(self) -> None:
        """Validate and persist via :class:`SnippetService`."""
        title = self.windowTitle()
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, title, "Enter a snippet name.")
            return
        category = self._category_edit.text().strip() or "My snippets"
        context = str(self._context_combo.currentData() or "both")
        body = self._resolved_body()
        if not body.strip():
            QMessageBox.warning(self, title, "Snippet body cannot be empty.")
            return
        try:
            if self._snippet_id is not None:
                SnippetService.update(
                    self._snippet_id,
                    name=name,
                    category=category,
                    body=body,
                    context=context,
                )
                self._saved_id = self._snippet_id
            else:
                self._saved_id = SnippetService.create(
                    name=name,
                    language=self._resolved_language(),
                    body=body,
                    category=category,
                    context=context,
                )
        except ValueError as exc:
            QMessageBox.warning(self, title, str(exc))
            return
        self.accept()
