"""Scripts tab mixin for the request editor.

Provides two ``CodeEditorWidget`` instances (pre-request and test) with
a language selector (JavaScript / Python), debounced version capture,
and cross-session undo.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from services.script_version_service import ScriptVersionService
from services.scripting.context import normalize_events as _normalize_events
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget

# Supported script languages (display label → CodeEditorWidget language)
_SCRIPT_LANGUAGES: dict[str, str] = {
    "JavaScript": "javascript",
    "Python": "python",
}

# Debounce delay (ms) for version capture after script edits.
_VERSION_CAPTURE_MS = 2000


class _ScriptsMixin:
    """Mixin that builds and manages the Scripts tab contents.

    The host class must provide ``_on_field_changed`` and ``_loading``
    attributes, and must be a ``QWidget``.
    """

    # -- Tab builder ---------------------------------------------------

    def _build_scripts_tab(self, parent_layout: QVBoxLayout) -> None:
        """Construct the dual-editor Scripts tab inside *parent_layout*."""
        # Language selector + history button row
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

        self._history_btn = QPushButton("History")
        self._history_btn.setIcon(phi("clock-counter-clockwise", size=14))
        self._history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_btn.setToolTip("View script version history")
        self._history_btn.clicked.connect(self._open_version_history)
        lang_row.addWidget(self._history_btn)

        parent_layout.addLayout(lang_row)

        # Pre-request script editor
        pre_label = QLabel("Pre-request Script")
        pre_label.setObjectName("sectionLabel")
        parent_layout.addWidget(pre_label)

        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.set_breakpoint_gutter_visible(True)
        self._pre_request_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._pre_request_edit.textChanged.connect(self._schedule_version_capture)
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
        self._test_script_edit.set_breakpoint_gutter_visible(True)
        self._test_script_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._test_script_edit.textChanged.connect(self._schedule_version_capture)
        parent_layout.addWidget(self._test_script_edit, 1)

        # Version capture debounce timer
        self._version_capture_timer = QTimer()
        self._version_capture_timer.setSingleShot(True)
        self._version_capture_timer.setInterval(_VERSION_CAPTURE_MS)
        self._version_capture_timer.timeout.connect(self._capture_script_versions)

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

    # -- Version capture -----------------------------------------------

    def _schedule_version_capture(self) -> None:
        """Restart the debounce timer on any script text change."""
        if self._loading:  # type: ignore[attr-defined]
            return
        self._version_capture_timer.start()

    def _capture_script_versions(self) -> None:
        """Capture current script content as version snapshots."""
        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return

        lang = _SCRIPT_LANGUAGES.get(self._script_lang_combo.currentText(), "javascript")

        pre = self._pre_request_edit.toPlainText()
        if pre.strip():
            ScriptVersionService.capture(
                request_id=request_id,
                collection_id=collection_id,
                script_type="pre_request",
                content=pre,
                language=lang,
            )

        test = self._test_script_edit.toPlainText()
        if test.strip():
            ScriptVersionService.capture(
                request_id=request_id,
                collection_id=collection_id,
                script_type="test",
                content=test,
                language=lang,
            )

    def capture_scripts_now(self) -> None:
        """Force an immediate version snapshot (called on Send / Save)."""
        self._version_capture_timer.stop()
        self._capture_script_versions()

    # -- Cross-session undo --------------------------------------------

    def _script_cross_session_undo(self, editor: CodeEditorWidget, script_type: str) -> bool:
        """Attempt cross-session undo for *editor*.

        Returns ``True`` if a previous version was restored, ``False``
        if no earlier version exists.
        """
        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return False

        current = editor.toPlainText()
        previous = ScriptVersionService.get_previous_content(
            request_id=request_id,
            collection_id=collection_id,
            script_type=script_type,
            current_content=current,
        )
        if previous is None:
            return False

        # Replace content — this counts as a new Qt undo entry.
        editor.selectAll()
        editor.insertPlainText(previous)
        return True

    # -- Version history dialog ----------------------------------------

    def _open_version_history(self) -> None:
        """Open the version history dialog for the current request."""
        from ui.request.request_editor.scripts.version_history import VersionHistoryDialog

        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return

        dlg = VersionHistoryDialog(
            request_id=request_id,
            collection_id=collection_id,
            current_pre=self._pre_request_edit.toPlainText(),
            current_test=self._test_script_edit.toPlainText(),
            parent=self._pre_request_edit,  # type: ignore[arg-type]
        )
        if dlg.exec():
            restored = dlg.restored_content()
            if restored:
                script_type, content = restored
                editor = (
                    self._pre_request_edit
                    if script_type == "pre_request"
                    else self._test_script_edit
                )
                editor.selectAll()
                editor.insertPlainText(content)
