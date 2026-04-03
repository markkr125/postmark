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
        """Build a single-editor script tab inside *parent_layout*.

        Called once for each script type.  The caller specifies which
        editor attribute to create via ``_build_pre_request_tab`` and
        ``_build_test_script_tab`` convenience wrappers.
        """
        raise NotImplementedError("Use _build_pre_request_tab / _build_test_script_tab")

    # -- Individual tab builders ---------------------------------------

    def _build_pre_request_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Pre-request Script tab contents."""
        self._pre_lang_combo, self._pre_history_btn = self._build_script_header(
            parent_layout,
            history_type="pre_request",
        )

        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.set_breakpoint_gutter_visible(True)
        self._pre_request_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._pre_request_edit.textChanged.connect(self._schedule_version_capture)
        parent_layout.addWidget(self._pre_request_edit, 1)

    def _build_test_script_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Post-response Script tab contents."""
        self._test_lang_combo, self._test_history_btn = self._build_script_header(
            parent_layout,
            history_type="test",
        )

        self._test_script_edit = CodeEditorWidget()
        self._test_script_edit.set_language("javascript")
        self._test_script_edit.setPlaceholderText(
            "Script to run after the response is received\u2026"
        )
        self._test_script_edit.set_breakpoint_gutter_visible(True)
        self._test_script_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._test_script_edit.textChanged.connect(self._schedule_version_capture)
        parent_layout.addWidget(self._test_script_edit, 1)

    def _build_script_header(
        self,
        parent_layout: QVBoxLayout,
        *,
        history_type: str,
    ) -> tuple[QComboBox, QPushButton]:
        """Build a language-selector + history-button row."""
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_label = QLabel("Language")
        lang_label.setObjectName("mutedLabel")
        lang_row.addWidget(lang_label)

        lang_combo = QComboBox()
        lang_combo.addItems(list(_SCRIPT_LANGUAGES.keys()))
        lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        lang_combo.setFixedWidth(120)
        lang_combo.currentTextChanged.connect(
            lambda name, ht=history_type: self._on_script_language_changed(name, ht),
        )
        lang_row.addWidget(lang_combo)

        history_btn = QPushButton("History")
        history_btn.setIcon(phi("clock-counter-clockwise", size=14))
        history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        history_btn.setToolTip("View script version history")
        history_btn.clicked.connect(
            lambda _checked=False, ht=history_type: self._open_version_history(ht),
        )
        lang_row.addWidget(history_btn)
        lang_row.addStretch()

        parent_layout.addLayout(lang_row)

        # Shared debounce timer (created once)
        if not hasattr(self, "_version_capture_timer"):
            self._version_capture_timer = QTimer()
            self._version_capture_timer.setSingleShot(True)
            self._version_capture_timer.setInterval(_VERSION_CAPTURE_MS)
            self._version_capture_timer.timeout.connect(self._capture_script_versions)

        return lang_combo, history_btn

    # -- Backward-compatible aliases -----------------------------------

    @property
    def _script_lang_combo(self) -> QComboBox:  # type: ignore[override]
        """Return the pre-request language combo for legacy callers."""
        return self._pre_lang_combo

    @property
    def _history_btn(self) -> QPushButton:  # type: ignore[override]
        """Return the pre-request history button for legacy callers."""
        return self._pre_history_btn

    # -- Language switching --------------------------------------------

    def _on_script_language_changed(self, display_name: str, script_type: str) -> None:
        """Update the matching editor when its language selector changes."""
        lang = _SCRIPT_LANGUAGES.get(display_name, "javascript")
        if script_type == "pre_request":
            self._pre_request_edit.set_language(lang)
        else:
            self._test_script_edit.set_language(lang)
        if not self._loading:  # type: ignore[attr-defined]
            self._on_field_changed()  # type: ignore[attr-defined]

    # -- Load / save / clear helpers -----------------------------------

    def _load_scripts(self, scripts: Any) -> None:
        """Populate script editors from stored data.

        Accepts our internal dict ``{"pre_request": ..., "test": ...,
        "pre_language": ..., "test_language": ...}``, a Postman events
        list, a raw JSON string, or ``None``.
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

        # Languages (per-tab, with fallback to shared 'language' key)
        fallback = "JavaScript"
        if isinstance(scripts, dict):
            shared = scripts.get("language", "").lower()
            for display, code in _SCRIPT_LANGUAGES.items():
                if code == shared:
                    fallback = display
                    break

        pre_display = fallback
        test_display = fallback
        if isinstance(scripts, dict):
            for attr, key in (("pre_display", "pre_language"), ("test_display", "test_language")):
                stored = scripts.get(key, "").lower()
                if stored:
                    for display, code in _SCRIPT_LANGUAGES.items():
                        if code == stored:
                            if attr == "pre_display":
                                pre_display = display
                            else:
                                test_display = display
                            break
        self._pre_lang_combo.setCurrentText(pre_display)
        self._test_lang_combo.setCurrentText(test_display)

    def _get_scripts_data(self) -> dict[str, str | None] | None:
        """Build the scripts dict from the editor contents."""
        pre = self._pre_request_edit.toPlainText()
        test = self._test_script_edit.toPlainText()
        if not pre and not test:
            return None

        pre_lang = _SCRIPT_LANGUAGES.get(self._pre_lang_combo.currentText(), "javascript")
        test_lang = _SCRIPT_LANGUAGES.get(self._test_lang_combo.currentText(), "javascript")
        return {
            "pre_request": pre or None,
            "test": test or None,
            "pre_language": pre_lang,
            "test_language": test_lang,
            "language": pre_lang,  # backward compat
        }

    def _clear_scripts(self) -> None:
        """Reset both script editors and language selectors."""
        self._pre_request_edit.clear()
        self._test_script_edit.clear()
        self._pre_lang_combo.setCurrentText("JavaScript")
        self._test_lang_combo.setCurrentText("JavaScript")

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

        pre = self._pre_request_edit.toPlainText()
        if pre.strip():
            pre_lang = _SCRIPT_LANGUAGES.get(
                self._pre_lang_combo.currentText(),
                "javascript",
            )
            ScriptVersionService.capture(
                request_id=request_id,
                collection_id=collection_id,
                script_type="pre_request",
                content=pre,
                language=pre_lang,
            )

        test = self._test_script_edit.toPlainText()
        if test.strip():
            test_lang = _SCRIPT_LANGUAGES.get(
                self._test_lang_combo.currentText(),
                "javascript",
            )
            ScriptVersionService.capture(
                request_id=request_id,
                collection_id=collection_id,
                script_type="test",
                content=test,
                language=test_lang,
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

    def _open_version_history(self, script_type: str = "pre_request") -> None:
        """Open the version history dialog for the current request."""
        from ui.request.request_editor.scripts.version_history import VersionHistoryDialog

        request_id = getattr(self, "_request_id", None)
        collection_id = getattr(self, "_collection_id", None)
        if request_id is None and collection_id is None:
            return

        lang_combo = self._pre_lang_combo if script_type == "pre_request" else self._test_lang_combo

        dlg = VersionHistoryDialog(
            request_id=request_id,
            collection_id=collection_id,
            current_pre=self._pre_request_edit.toPlainText(),
            current_test=self._test_script_edit.toPlainText(),
            language=_SCRIPT_LANGUAGES.get(
                lang_combo.currentText(),
                "javascript",
            ),
            initial_tab=0 if script_type == "pre_request" else 1,
            parent=self._pre_request_edit,
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
                editor.selectAll()
                editor.insertPlainText(content)
