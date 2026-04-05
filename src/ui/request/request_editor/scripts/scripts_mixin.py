"""Scripts tab mixin — dual pre-request / test script editors."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from services.script_version_service import ScriptVersionService
from services.scripting.context import normalize_events as _normalize_events
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget
from ui.widgets.search_replace_bar import SearchReplaceBar

# Display label → CodeEditorWidget language.
_SCRIPT_LANGUAGES: dict[str, str] = {"JavaScript": "javascript", "Python": "python"}

_VERSION_CAPTURE_MS = 2000  # Debounce delay (ms) for version capture.
_AUTO_SAVE_CAPTURE_MS = 500  # Aggressive capture interval when auto-save enabled.

# QSettings keys.
_SETTINGS_KEY_AUTO_SAVE_OVERRIDES = "scripts/auto_save_overrides"
_SETTINGS_KEY_AUTO_SAVE_DEFAULT = "scripting/auto_save_default"


class _ScriptsMixin:
    """Mixin building and managing pre-request / test script editors."""

    # -- Individual tab builders ---------------------------------------

    def _build_pre_request_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Pre-request Script tab contents."""
        self._pre_request_edit = CodeEditorWidget()
        self._pre_request_edit.set_language("javascript")
        self._pre_request_edit.setPlaceholderText("Script to run before the request is sent\u2026")
        self._pre_request_edit.set_breakpoint_gutter_visible(True)
        self._pre_request_edit.setMinimumHeight(80)
        self._pre_request_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._pre_request_edit.textChanged.connect(self._schedule_version_capture)

        self._pre_search_bar = SearchReplaceBar(self._pre_request_edit)

        self._pre_lang_combo, self._pre_history_btn = self._build_script_header(
            parent_layout,
            history_type="pre_request",
            search_bar=self._pre_search_bar,
        )

        # Editor pane (search bar + editor + status bar).
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._pre_search_bar)
        editor_layout.addWidget(self._pre_request_edit, 1)
        self._pre_status_label = self._build_status_bar(
            editor_layout,
            self._pre_request_edit,
            self._pre_lang_combo,
        )

        # Output panel for inline script execution results.
        from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel

        self._pre_output_panel = ScriptOutputPanel(script_type="pre_request")
        self._pre_output_panel.setVisible(False)

        # Resizable splitter between editor and output.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_pane)
        splitter.addWidget(self._pre_output_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        parent_layout.addWidget(splitter, 1)

    def _build_test_script_tab(self, parent_layout: QVBoxLayout) -> None:
        """Build the Post-response Script tab contents."""
        self._test_script_edit = CodeEditorWidget()
        self._test_script_edit.set_language("javascript")
        self._test_script_edit.setPlaceholderText(
            "Script to run after the response is received\u2026"
        )
        self._test_script_edit.set_breakpoint_gutter_visible(True)
        self._test_script_edit.setMinimumHeight(80)
        self._test_script_edit.textChanged.connect(self._on_field_changed)  # type: ignore[attr-defined]
        self._test_script_edit.textChanged.connect(self._schedule_version_capture)

        self._test_search_bar = SearchReplaceBar(self._test_script_edit)

        self._test_lang_combo, self._test_history_btn = self._build_script_header(
            parent_layout,
            history_type="test",
            search_bar=self._test_search_bar,
        )

        # Editor pane (search bar + editor + status bar).
        editor_pane = QWidget()
        editor_layout = QVBoxLayout(editor_pane)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self._test_search_bar)
        editor_layout.addWidget(self._test_script_edit, 1)
        self._test_status_label = self._build_status_bar(
            editor_layout,
            self._test_script_edit,
            self._test_lang_combo,
        )

        # Output panel for inline script execution results.
        from ui.request.request_editor.scripts.output_panel import ScriptOutputPanel

        self._test_output_panel = ScriptOutputPanel(script_type="test")
        self._test_output_panel.setVisible(False)

        # Resizable splitter between editor and output.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_pane)
        splitter.addWidget(self._test_output_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        parent_layout.addWidget(splitter, 1)

    def _build_script_header(
        self,
        parent_layout: QVBoxLayout,
        *,
        history_type: str,
        search_bar: SearchReplaceBar,
    ) -> tuple[QComboBox, QPushButton]:
        """Build language-selector, history, toolbar, and auto-save row."""
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

        # -- Toolbar buttons (right-aligned, matching response viewer) --
        find_hint = QKeySequence(QKeySequence.StandardKey.Find).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        replace_hint = QKeySequence(QKeySequence.StandardKey.Replace).toString(
            QKeySequence.SequenceFormat.NativeText,
        )
        for icon, tip, slot in (
            ("magnifying-glass", f"Find ({find_hint})", search_bar.toggle_search),
            ("swap", f"Find & Replace ({replace_hint})", search_bar.toggle_replace),
            ("list-numbers", "Go to Line (Ctrl+G)", search_bar.goto_line),
        ):
            btn = QPushButton()
            btn.setIcon(phi(icon))
            btn.setFixedSize(28, 28)
            btn.setObjectName("iconButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            lang_row.addWidget(btn)

        # -- Run button ------------------------------------------------
        run_btn = QPushButton()
        run_btn.setIcon(phi("play"))
        run_btn.setFixedSize(28, 28)
        run_btn.setObjectName("iconButton")
        run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        run_btn.setToolTip("Run script (Ctrl+Enter)")
        run_btn.clicked.connect(
            lambda _checked=False, ht=history_type: self._run_inline_script(ht),
        )
        lang_row.addWidget(run_btn)
        if not hasattr(self, "_run_buttons"):
            self._run_buttons: dict[str, QPushButton] = {}
        self._run_buttons[history_type] = run_btn

        # -- Auto-save toggle (right-aligned with toolbar) -------------
        if not hasattr(self, "_auto_save_checkboxes"):
            self._auto_save_checkboxes: list[QCheckBox] = []
            self._auto_save_enabled = True

        auto_save_cb = QCheckBox("Auto-save")
        auto_save_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        auto_save_cb.setToolTip("Capture script versions continuously")
        auto_save_cb.setChecked(self._auto_save_enabled)
        auto_save_cb.toggled.connect(self._on_auto_save_toggled)
        self._auto_save_checkboxes.append(auto_save_cb)
        lang_row.addWidget(auto_save_cb)

        parent_layout.addLayout(lang_row)

        # Shared debounce timer (created once)
        if not hasattr(self, "_version_capture_timer"):
            initial_ms = _AUTO_SAVE_CAPTURE_MS if self._auto_save_enabled else _VERSION_CAPTURE_MS
            self._version_capture_timer = QTimer()
            self._version_capture_timer.setSingleShot(True)
            self._version_capture_timer.setInterval(initial_ms)
            self._version_capture_timer.timeout.connect(self._capture_script_versions)

        return lang_combo, history_btn

    def _build_status_bar(
        self,
        parent_layout: QVBoxLayout,
        editor: CodeEditorWidget,
        lang_combo: QComboBox,
    ) -> QLabel:
        """Build a status bar below *editor* showing Ln, Col, language, chars."""
        label = QLabel()
        label.setObjectName("mutedLabel")
        parent_layout.addWidget(label)

        def _update(_line: int = 0, _col: int = 0) -> None:
            cur = editor.textCursor()
            ln = cur.blockNumber() + 1
            col = cur.positionInBlock() + 1
            lang = lang_combo.currentText()
            chars = len(editor.toPlainText())
            label.setText(f"Ln {ln}, Col {col}  \u2502  {lang}  \u2502  {chars} chars")

        editor.cursor_position_changed.connect(_update)
        editor.textChanged.connect(_update)
        lang_combo.currentTextChanged.connect(lambda _: _update())
        _update()
        return label

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
        """Populate script editors from stored data (dict, events list, JSON, or None)."""
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

        # Restore per-entity auto-save preference
        self._restore_auto_save_state()

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
        # Reset auto-save to global default
        default_on = self._read_auto_save_global_default()
        self._auto_save_enabled = default_on
        for cb in self._auto_save_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(default_on)
            cb.blockSignals(False)
        self._version_capture_timer.setInterval(
            _AUTO_SAVE_CAPTURE_MS if default_on else _VERSION_CAPTURE_MS,
        )

    def _has_scripts_content(self) -> bool:
        """Return whether either script editor has content."""
        return bool(
            self._pre_request_edit.toPlainText().strip()
            or self._test_script_edit.toPlainText().strip()
        )

    # -- Inline script execution ----------------------------------------

    def _run_inline_script(self, script_type: str) -> None:
        """Run the current script inline and display results."""
        from ui.request.request_editor.scripts.script_run_worker import build_inline_context

        if script_type == "pre_request":
            editor = self._pre_request_edit
            lang_combo = self._pre_lang_combo
            panel = self._pre_output_panel
        else:
            editor = self._test_script_edit
            lang_combo = self._test_lang_combo
            panel = self._test_output_panel

        script = editor.toPlainText().strip()
        if not script:
            return

        language = _SCRIPT_LANGUAGES.get(lang_combo.currentText(), "javascript")
        response_data = panel.get_response_data() if script_type == "test" else None
        context = build_inline_context(
            script_type=script_type,
            response_data=response_data,
        )
        run_btn = self._run_buttons.get(script_type)
        panel.run_script(
            script=script,
            language=language,
            context=context,
            run_btn=run_btn,
        )

    # -- Auto-save toggle -----------------------------------------------

    def _auto_save_entity_key(self) -> str | None:
        """Return a unique key for the current request or collection."""
        rid = getattr(self, "_request_id", None)
        if rid is not None:
            return f"r:{rid}"
        cid = getattr(self, "_collection_id", None)
        if cid is not None:
            return f"c:{cid}"
        return None

    @staticmethod
    def _read_auto_save_global_default() -> bool:
        """Read the global auto-save default from QSettings."""
        from ui.styling.theme_manager import _APP, _ORG

        raw = QSettings(_ORG, _APP).value(_SETTINGS_KEY_AUTO_SAVE_DEFAULT, True)
        if isinstance(raw, str):
            return raw.lower() not in {"0", "false", "no", "off", ""}
        return bool(raw)

    @staticmethod
    def _read_auto_save_overrides() -> dict[str, bool]:
        """Read per-entity auto-save overrides from QSettings."""
        import json

        from ui.styling.theme_manager import _APP, _ORG

        raw = QSettings(_ORG, _APP).value(_SETTINGS_KEY_AUTO_SAVE_OVERRIDES, "")
        if not raw or not isinstance(raw, str):
            return {}
        try:
            items = json.loads(raw)
            return items if isinstance(items, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _write_auto_save_overrides(self, overrides: dict[str, bool]) -> None:
        """Persist the per-entity auto-save overrides."""
        import json

        from ui.styling.theme_manager import _APP, _ORG

        QSettings(_ORG, _APP).setValue(
            _SETTINGS_KEY_AUTO_SAVE_OVERRIDES,
            json.dumps(overrides, sort_keys=True),
        )

    def _restore_auto_save_state(self) -> None:
        """Restore the auto-save checkbox from per-entity override or global default."""
        key = self._auto_save_entity_key()
        overrides = self._read_auto_save_overrides()
        if key and key in overrides:
            enabled = overrides[key]
        else:
            enabled = self._read_auto_save_global_default()
        self._auto_save_enabled = enabled
        for cb in self._auto_save_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        interval = _AUTO_SAVE_CAPTURE_MS if enabled else _VERSION_CAPTURE_MS
        self._version_capture_timer.setInterval(interval)

    def _on_auto_save_toggled(self, checked: bool) -> None:
        """Sync all auto-save checkboxes, persist per entity, and adjust interval."""
        self._auto_save_enabled = checked
        for cb in self._auto_save_checkboxes:
            if cb.isChecked() != checked:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        interval = _AUTO_SAVE_CAPTURE_MS if checked else _VERSION_CAPTURE_MS
        self._version_capture_timer.setInterval(interval)
        if checked:
            self.capture_scripts_now()
        key = self._auto_save_entity_key()
        if key:
            global_default = self._read_auto_save_global_default()
            overrides = self._read_auto_save_overrides()
            if checked == global_default:
                overrides.pop(key, None)
            else:
                overrides[key] = checked
            self._write_auto_save_overrides(overrides)

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
