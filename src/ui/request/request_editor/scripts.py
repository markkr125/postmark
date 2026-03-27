"""Scripts tab mixin for the request editor.

Provides two ``CodeEditorWidget`` instances (pre-request and test) with
a language selector (JavaScript / Python).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout

from services.scripting.context import normalize_events as _normalize_events
from ui.widgets.code_editor import CodeEditorWidget

# Supported script languages (display label → CodeEditorWidget language)
_SCRIPT_LANGUAGES: dict[str, str] = {
    "JavaScript": "javascript",
    "Python": "python",
}


class _ScriptsMixin:
    """Mixin that builds and manages the Scripts tab contents.

    The host class must provide ``_on_field_changed`` and ``_loading``
    attributes, and must be a ``QWidget``.
    """

    # -- Tab builder ---------------------------------------------------

    def _build_scripts_tab(self, parent_layout: QVBoxLayout) -> None:
        """Construct the dual-editor Scripts tab inside *parent_layout*."""
        # Language selector row
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_label = QLabel("Language")
        lang_label.setObjectName("mutedLabel")
        lang_row.addWidget(lang_label)

        self._script_lang_combo = QComboBox()
        self._script_lang_combo.addItems(list(_SCRIPT_LANGUAGES.keys()))
        self._script_lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._script_lang_combo.setFixedWidth(120)
        self._script_lang_combo.currentTextChanged.connect(self._on_script_language_changed)
        lang_row.addWidget(self._script_lang_combo)
        lang_row.addStretch()
        parent_layout.addLayout(lang_row)

        # Pre-request script editor
        pre_label = QLabel("Pre-request Script")
        pre_label.setObjectName("sectionLabel")
        parent_layout.addWidget(pre_label)

        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        parent_layout.addWidget(self._pre_request_edit, 1)

        # Test / post-response script editor
        post_label = QLabel("Tests / Post-response Script")
        post_label.setObjectName("sectionLabel")
        parent_layout.addWidget(post_label)

        self._test_script_edit = CodeEditorWidget()
        self._test_script_edit.set_language("javascript")
        self._test_script_edit.setPlaceholderText(
            "Script to run after the response is received\u2026"
        )
        self._test_script_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        parent_layout.addWidget(self._test_script_edit, 1)

    # -- Language switching --------------------------------------------

    def _on_script_language_changed(self, display_name: str) -> None:
        """Update both editors when the language selector changes."""
        lang = _SCRIPT_LANGUAGES.get(display_name, "javascript")
        self._pre_request_edit.set_language(lang)
        self._test_script_edit.set_language(lang)
        if not self._loading:  # type: ignore[attr-defined]
            self._on_field_changed()  # type: ignore[attr-defined]

    # -- Load / save / clear helpers -----------------------------------

    def _load_scripts(self, scripts: Any) -> None:
        """Populate script editors from stored data.

        Accepts our internal dict ``{"pre_request": ..., "test": ...,
        "language": ...}``, a Postman events list, a raw JSON string,
        or ``None``.
        """
        if isinstance(scripts, str) and scripts.strip():
            # Legacy raw string — try to parse as JSON dict
            import json

            try:
                scripts = json.loads(scripts)
            except (json.JSONDecodeError, TypeError):
                # Treat entire string as pre-request script
                self._pre_request_edit.setPlainText(scripts)
                self._test_script_edit.setPlainText("")
                return

        events = _normalize_events(scripts)

        self._pre_request_edit.setPlainText(events.get("pre_request") or "")
        self._test_script_edit.setPlainText(events.get("test") or "")

        # Language
        lang_display = "JavaScript"
        if isinstance(scripts, dict):
            stored_lang = scripts.get("language", "").lower()
            for display, code in _SCRIPT_LANGUAGES.items():
                if code == stored_lang:
                    lang_display = display
                    break
        self._script_lang_combo.setCurrentText(lang_display)

    def _get_scripts_data(self) -> dict[str, str | None] | None:
        """Build the scripts dict from the editor contents."""
        pre = self._pre_request_edit.toPlainText()
        test = self._test_script_edit.toPlainText()
        if not pre and not test:
            return None

        lang = _SCRIPT_LANGUAGES.get(self._script_lang_combo.currentText(), "javascript")
        return {
            "pre_request": pre or None,
            "test": test or None,
            "language": lang,
        }

    def _clear_scripts(self) -> None:
        """Reset both script editors and the language selector."""
        self._pre_request_edit.clear()
        self._test_script_edit.clear()
        self._script_lang_combo.setCurrentText("JavaScript")

    def _has_scripts_content(self) -> bool:
        """Return whether either script editor has content."""
        return bool(
            self._pre_request_edit.toPlainText().strip()
            or self._test_script_edit.toPlainText().strip()
        )
