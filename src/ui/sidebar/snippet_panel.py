"""Code snippet panel for the right sidebar.

Inline replacement for the former :class:`CodeSnippetDialog`.  Embeds
a language selector, a read-only code editor, a copy-to-clipboard
button, and a settings popup directly inside the sidebar.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtGui import QClipboard, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from services.http.snippet_generator import SnippetGenerator, SnippetOptions
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget

_SHOW_GRACE_SEC = 0.15

# QSettings keys
_SETTINGS_PREFIX = "snippet"
_KEY_LANGUAGE = f"{_SETTINGS_PREFIX}/last_language"
_KEY_INDENT_COUNT = f"{_SETTINGS_PREFIX}/indent_count"
_KEY_INDENT_TYPE = f"{_SETTINGS_PREFIX}/indent_type"
_KEY_TRIM_BODY = f"{_SETTINGS_PREFIX}/trim_body"
_KEY_FOLLOW_REDIRECT = f"{_SETTINGS_PREFIX}/follow_redirect"
_KEY_REQUEST_TIMEOUT = f"{_SETTINGS_PREFIX}/request_timeout"
_KEY_INCLUDE_BOILERPLATE = f"{_SETTINGS_PREFIX}/include_boilerplate"
_KEY_ASYNC_AWAIT = f"{_SETTINGS_PREFIX}/async_await"
_KEY_ES6_FEATURES = f"{_SETTINGS_PREFIX}/es6_features"
_KEY_MULTILINE = f"{_SETTINGS_PREFIX}/multiline"
_KEY_LONG_FORM = f"{_SETTINGS_PREFIX}/long_form"
_KEY_LINE_CONTINUATION = f"{_SETTINGS_PREFIX}/line_continuation"
_KEY_QUOTE_TYPE = f"{_SETTINGS_PREFIX}/quote_type"
_KEY_FOLLOW_ORIGINAL_METHOD = f"{_SETTINGS_PREFIX}/follow_original_method"
_KEY_SILENT_MODE = f"{_SETTINGS_PREFIX}/silent_mode"


class SnippetSettingsPopup(QFrame):
    """Small floating popup for snippet generation settings.

    Positioned below the gear button.  All changes apply immediately
    (live preview) and persist via QSettings.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the settings popup with controls for all options."""
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setObjectName("infoPopup")
        self._show_time: float = 0.0

        settings = QSettings()
        form = QFormLayout(self)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(6)

        # Indent count
        self._indent_count = QSpinBox()
        self._indent_count.setRange(1, 8)
        self._indent_count.setValue(int(str(settings.value(_KEY_INDENT_COUNT, 2))))
        self._indent_count_label = QLabel("Indent count:")
        form.addRow(self._indent_count_label, self._indent_count)

        # Indent type
        self._indent_type = QComboBox()
        self._indent_type.addItems(["Space", "Tab"])
        saved_type = str(settings.value(_KEY_INDENT_TYPE, "space"))
        self._indent_type.setCurrentText("Tab" if saved_type == "tab" else "Space")
        self._indent_type_label = QLabel("Indent type:")
        form.addRow(self._indent_type_label, self._indent_type)

        # Trim body
        self._trim_body = QCheckBox()
        self._trim_body.setChecked(bool(settings.value(_KEY_TRIM_BODY, False)))
        self._trim_body_label = QLabel("Trim body:")
        form.addRow(self._trim_body_label, self._trim_body)

        # Follow redirect
        self._follow_redirect = QCheckBox()
        self._follow_redirect.setChecked(
            settings.value(_KEY_FOLLOW_REDIRECT, True) not in (False, "false")
        )
        self._redirect_label = QLabel("Follow redirects:")
        form.addRow(self._redirect_label, self._follow_redirect)

        # Request timeout
        self._request_timeout = QSpinBox()
        self._request_timeout.setRange(0, 300)
        self._request_timeout.setSuffix(" s")
        self._request_timeout.setSpecialValueText("None")
        self._request_timeout.setValue(int(str(settings.value(_KEY_REQUEST_TIMEOUT, 0))))
        self._timeout_label = QLabel("Timeout:")
        form.addRow(self._timeout_label, self._request_timeout)

        # Include boilerplate
        self._include_boilerplate = QCheckBox()
        self._include_boilerplate.setChecked(
            settings.value(_KEY_INCLUDE_BOILERPLATE, True) not in (False, "false")
        )
        self._boilerplate_label = QLabel("Include boilerplate:")
        form.addRow(self._boilerplate_label, self._include_boilerplate)

        # Async/await
        self._async_await = QCheckBox()
        self._async_await.setChecked(bool(settings.value(_KEY_ASYNC_AWAIT, False)))
        self._async_label = QLabel("Async/await:")
        form.addRow(self._async_label, self._async_await)

        # ES6 features
        self._es6_features = QCheckBox()
        self._es6_features.setChecked(bool(settings.value(_KEY_ES6_FEATURES, False)))
        self._es6_label = QLabel("ES6 features:")
        form.addRow(self._es6_label, self._es6_features)

        # --- cURL-specific options ---

        # Multiline
        self._multiline = QCheckBox()
        self._multiline.setChecked(settings.value(_KEY_MULTILINE, True) not in (False, "false"))
        self._multiline_label = QLabel("Multiline:")
        form.addRow(self._multiline_label, self._multiline)

        # Long-form options
        self._long_form = QCheckBox()
        self._long_form.setChecked(settings.value(_KEY_LONG_FORM, True) not in (False, "false"))
        self._long_form_label = QLabel("Long form options:")
        form.addRow(self._long_form_label, self._long_form)

        # Line continuation character
        self._line_continuation = QComboBox()
        self._line_continuation.addItems(["\\", "^", "`"])
        saved_cont = str(settings.value(_KEY_LINE_CONTINUATION, "\\"))
        idx = self._line_continuation.findText(saved_cont)
        if idx >= 0:
            self._line_continuation.setCurrentIndex(idx)
        self._continuation_label = QLabel("Line continuation:")
        form.addRow(self._continuation_label, self._line_continuation)

        # Quote type
        self._quote_type = QComboBox()
        self._quote_type.addItems(["single", "double"])
        saved_quote = str(settings.value(_KEY_QUOTE_TYPE, "single"))
        self._quote_type.setCurrentText(saved_quote)
        self._quote_label = QLabel("Quote type:")
        form.addRow(self._quote_label, self._quote_type)

        # Follow original method
        self._follow_original_method = QCheckBox()
        self._follow_original_method.setChecked(
            bool(settings.value(_KEY_FOLLOW_ORIGINAL_METHOD, False))
        )
        self._orig_method_label = QLabel("Follow original method:")
        form.addRow(self._orig_method_label, self._follow_original_method)

        # Silent mode
        self._silent_mode = QCheckBox()
        self._silent_mode.setChecked(bool(settings.value(_KEY_SILENT_MODE, False)))
        self._silent_label = QLabel("Silent mode:")
        form.addRow(self._silent_label, self._silent_mode)

        # Connect for live preview
        self._indent_count.valueChanged.connect(self._save)
        self._indent_type.currentTextChanged.connect(self._save)
        self._trim_body.toggled.connect(self._save)
        self._follow_redirect.toggled.connect(self._save)
        self._request_timeout.valueChanged.connect(self._save)
        self._include_boilerplate.toggled.connect(self._save)
        self._async_await.toggled.connect(self._save)
        self._es6_features.toggled.connect(self._save)
        self._multiline.toggled.connect(self._save)
        self._long_form.toggled.connect(self._save)
        self._line_continuation.currentTextChanged.connect(self._save)
        self._quote_type.currentTextChanged.connect(self._save)
        self._follow_original_method.toggled.connect(self._save)
        self._silent_mode.toggled.connect(self._save)

        self._on_settings_changed: list[object] = []

    def set_language_options(self, applicable: tuple[str, ...]) -> None:
        """Show/hide controls based on the current language's options."""
        has_indent = "indent_count" in applicable
        self._indent_count_label.setVisible(has_indent)
        self._indent_count.setVisible(has_indent)
        self._indent_type_label.setVisible(has_indent)
        self._indent_type.setVisible(has_indent)

        has_trim = "trim_body" in applicable
        self._trim_body_label.setVisible(has_trim)
        self._trim_body.setVisible(has_trim)

        has_redirect = "follow_redirect" in applicable
        self._redirect_label.setVisible(has_redirect)
        self._follow_redirect.setVisible(has_redirect)

        has_timeout = "request_timeout" in applicable
        self._timeout_label.setVisible(has_timeout)
        self._request_timeout.setVisible(has_timeout)

        has_boilerplate = "include_boilerplate" in applicable
        self._boilerplate_label.setVisible(has_boilerplate)
        self._include_boilerplate.setVisible(has_boilerplate)

        has_async = "async_await" in applicable
        self._async_label.setVisible(has_async)
        self._async_await.setVisible(has_async)

        has_es6 = "es6_features" in applicable
        self._es6_label.setVisible(has_es6)
        self._es6_features.setVisible(has_es6)

        has_multiline = "multiline" in applicable
        self._multiline_label.setVisible(has_multiline)
        self._multiline.setVisible(has_multiline)

        has_long_form = "long_form" in applicable
        self._long_form_label.setVisible(has_long_form)
        self._long_form.setVisible(has_long_form)

        has_continuation = "line_continuation" in applicable
        self._continuation_label.setVisible(has_continuation)
        self._line_continuation.setVisible(has_continuation)

        has_quote = "quote_type" in applicable
        self._quote_label.setVisible(has_quote)
        self._quote_type.setVisible(has_quote)

        has_orig_method = "follow_original_method" in applicable
        self._orig_method_label.setVisible(has_orig_method)
        self._follow_original_method.setVisible(has_orig_method)

        has_silent = "silent_mode" in applicable
        self._silent_label.setVisible(has_silent)
        self._silent_mode.setVisible(has_silent)

    def get_options(self) -> SnippetOptions:
        """Build a :class:`SnippetOptions` from current control values."""
        return SnippetOptions(
            indent_count=self._indent_count.value(),
            indent_type="tab" if self._indent_type.currentText() == "Tab" else "space",
            trim_body=self._trim_body.isChecked(),
            follow_redirect=self._follow_redirect.isChecked(),
            request_timeout=self._request_timeout.value(),
            include_boilerplate=self._include_boilerplate.isChecked(),
            async_await=self._async_await.isChecked(),
            es6_features=self._es6_features.isChecked(),
            multiline=self._multiline.isChecked(),
            long_form=self._long_form.isChecked(),
            line_continuation=self._line_continuation.currentText(),
            quote_type=self._quote_type.currentText(),
            follow_original_method=self._follow_original_method.isChecked(),
            silent_mode=self._silent_mode.isChecked(),
        )

    def on_settings_changed(self, callback: object) -> None:
        """Register a callback invoked when any setting changes."""
        self._on_settings_changed.append(callback)

    def show_below(self, anchor: QWidget) -> None:
        """Position the popup below *anchor* and show it."""
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(pos)
        self._show_time = time.monotonic()
        self.show()
        self.activateWindow()
        self.setFocus()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        """Close on click-outside or parent window move/resize."""
        etype = event.type()
        if (
            etype in (QEvent.Type.Move, QEvent.Type.Resize)
            and obj is not self
            and hasattr(obj, "isWindow")
            and obj.isWindow()  # type: ignore[union-attr]
        ):
            self.close()
            return False
        if etype == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if time.monotonic() - self._show_time < _SHOW_GRACE_SEC:
                return False
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.close()
                return False
        return super().eventFilter(obj, event)

    def closeEvent(self, event: object) -> None:
        """Remove the app-wide event filter when the popup closes."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)  # type: ignore[arg-type]

    def _save(self) -> None:
        """Persist current values to QSettings and notify listeners."""
        settings = QSettings()
        settings.setValue(_KEY_INDENT_COUNT, self._indent_count.value())
        settings.setValue(
            _KEY_INDENT_TYPE,
            "tab" if self._indent_type.currentText() == "Tab" else "space",
        )
        settings.setValue(_KEY_TRIM_BODY, self._trim_body.isChecked())
        settings.setValue(_KEY_FOLLOW_REDIRECT, self._follow_redirect.isChecked())
        settings.setValue(_KEY_REQUEST_TIMEOUT, self._request_timeout.value())
        settings.setValue(_KEY_INCLUDE_BOILERPLATE, self._include_boilerplate.isChecked())
        settings.setValue(_KEY_ASYNC_AWAIT, self._async_await.isChecked())
        settings.setValue(_KEY_ES6_FEATURES, self._es6_features.isChecked())
        settings.setValue(_KEY_MULTILINE, self._multiline.isChecked())
        settings.setValue(_KEY_LONG_FORM, self._long_form.isChecked())
        settings.setValue(_KEY_LINE_CONTINUATION, self._line_continuation.currentText())
        settings.setValue(_KEY_QUOTE_TYPE, self._quote_type.currentText())
        settings.setValue(_KEY_FOLLOW_ORIGINAL_METHOD, self._follow_original_method.isChecked())
        settings.setValue(_KEY_SILENT_MODE, self._silent_mode.isChecked())

        for cb in self._on_settings_changed:
            if callable(cb):
                cb()


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

        # Restore last-selected language
        settings = QSettings()
        saved_lang = str(settings.value(_KEY_LANGUAGE, "cURL"))
        idx = self._lang_combo.findText(saved_lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)

        self._lang_combo.currentTextChanged.connect(self._on_language_changed)
        selector_row.addWidget(self._lang_combo, 1)

        # Settings gear button
        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(phi("gear"))
        self._settings_btn.setObjectName("iconButton")
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("Snippet settings")
        self._settings_btn.clicked.connect(self._toggle_settings)
        selector_row.addWidget(self._settings_btn)

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

        # Settings popup (lazy)
        self._settings_popup: SnippetSettingsPopup | None = None

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
    def _current_options(self) -> SnippetOptions | None:
        """Build options from the settings popup or QSettings."""
        if self._settings_popup is not None:
            return self._settings_popup.get_options()
        settings = QSettings()
        return SnippetOptions(
            indent_count=int(str(settings.value(_KEY_INDENT_COUNT, 2))),
            indent_type=str(settings.value(_KEY_INDENT_TYPE, "space")),
            trim_body=settings.value(_KEY_TRIM_BODY, False) not in (False, "false"),
            follow_redirect=settings.value(_KEY_FOLLOW_REDIRECT, True) not in (False, "false"),
            request_timeout=int(str(settings.value(_KEY_REQUEST_TIMEOUT, 0))),
            include_boilerplate=settings.value(_KEY_INCLUDE_BOILERPLATE, True)
            not in (False, "false"),
            async_await=settings.value(_KEY_ASYNC_AWAIT, False) not in (False, "false", 0, "0"),
            es6_features=settings.value(_KEY_ES6_FEATURES, False) not in (False, "false", 0, "0"),
            multiline=settings.value(_KEY_MULTILINE, True) not in (False, "false"),
            long_form=settings.value(_KEY_LONG_FORM, True) not in (False, "false"),
            line_continuation=str(settings.value(_KEY_LINE_CONTINUATION, "\\")),
            quote_type=str(settings.value(_KEY_QUOTE_TYPE, "single")),
            follow_original_method=settings.value(_KEY_FOLLOW_ORIGINAL_METHOD, False)
            not in (False, "false", 0, "0"),
            silent_mode=settings.value(_KEY_SILENT_MODE, False) not in (False, "false", 0, "0"),
        )

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
            options=self._current_options(),
        )
        info = SnippetGenerator.get_language_info(lang)
        lexer = info.lexer if info else "text"
        self._code_edit.set_language(lexer)
        self._code_edit.set_text(snippet)
        self._status_label.setText("")

    def _on_language_changed(self, lang: str) -> None:
        """Handle language combo change — persist and refresh."""
        QSettings().setValue(_KEY_LANGUAGE, lang)
        if self._settings_popup is not None:
            info = SnippetGenerator.get_language_info(lang)
            if info:
                self._settings_popup.set_language_options(info.applicable_options)
        self._refresh()

    def _toggle_settings(self) -> None:
        """Show or hide the snippet settings popup."""
        if self._settings_popup is not None and self._settings_popup.isVisible():
            self._settings_popup.hide()
            return

        if self._settings_popup is None:
            self._settings_popup = SnippetSettingsPopup(self)
            self._settings_popup.on_settings_changed(self._refresh)

        lang = self._lang_combo.currentText()
        info = SnippetGenerator.get_language_info(lang)
        if info:
            self._settings_popup.set_language_options(info.applicable_options)
        self._settings_popup.show_below(self._settings_btn)

    def _copy_to_clipboard(self) -> None:
        """Copy the current snippet text to the system clipboard."""
        clipboard: QClipboard | None = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._code_edit.toPlainText())
        self._status_label.setText("Copied!")
