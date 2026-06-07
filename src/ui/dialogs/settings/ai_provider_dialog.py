"""Modal dialog to add or edit a provider (imports all models into Settings)."""

from __future__ import annotations

import uuid
from typing import Literal

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.ai.ai_config import AiModelEntry
from services.ai.ai_logging import set_ui_log_sink
from services.ai.provider_catalog import (
    PROVIDERS,
    ModelSpec,
    allocate_provider_display_name,
    ollama_default_context_tokens,
    provider_by_key,
    provider_group_label,
)
from services.scripting.secret_store import get_default_store
from ui.dialogs.secret_entry_dialog import SecretEntryDialog
from ui.dialogs.settings.ai_page_actions import (
    ModelsListPreviewLoader,
    ai_provider_field_button_strip,
    ai_provider_form_label,
    apply_provider_edit_entries,
    entries_from_model_specs,
    make_ollama_default_context_combo,
    model_preview_lines_from_entries,
    model_preview_lines_from_specs,
    ollama_context_tokens_from_combo,
    provider_edit_allows_save_without_test,
    provider_template_entry,
    validate_provider_credentials,
)
from ui.dialogs.settings.ai_provider_workers import (
    AiProviderSetupWorker,
    cancel_provider_setup_thread,
    disconnect_provider_setup_worker,
    release_provider_setup_thread,
)
from ui.styling.icons import phi


class AiProviderDialog(QDialog):
    """Add/edit provider credentials; save imports every discovered model."""

    def __init__(
        self,
        *,
        entry: AiModelEntry | None = None,
        existing_entries: list[AiModelEntry] | None = None,
        existing_provider_display_names: frozenset[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """*entry* set when editing an existing provider (by shared credentials)."""
        super().__init__(parent)
        self._is_edit = entry is not None
        self._existing_provider_display_names = set(existing_provider_display_names or ())
        self.setWindowTitle("Edit provider" if self._is_edit else "Add provider")
        self.setModal(True)
        self.setMinimumSize(580, 560)

        self._auth_kind: Literal["token", "none"] = "none"
        self._fetched_models: tuple[ModelSpec, ...] = ()
        self._setup_thread: QThread | None = None
        self._setup_worker: AiProviderSetupWorker | None = None
        self._provider_tested_ok = False
        self._verified_fingerprint: tuple[str, ...] | None = None
        self._pending_save_after_test = False
        self._cred_row_widgets: list[QWidget] = []
        self._cred_insert_row = 2
        self._ollama_context_combo: QComboBox | None = None
        self._init_ollama_context = ollama_default_context_tokens(entry)
        self._edit_existing_entries: list[AiModelEntry] = list(existing_entries or [])
        self._edit_baseline_fingerprint: tuple[str, ...] | None = None

        if entry is None:
            self._entry_id = uuid.uuid4().hex
            init_provider = PROVIDERS[0].key
            init_base, init_ver = "", ""
            self._auth_ref = ""
            self._label_is_auto = True
            self._edit_auth_ref = ""
        else:
            self._entry_id = entry["id"]
            init_provider = entry["provider"] or PROVIDERS[0].key
            init_base, init_ver = entry["base_url"], entry["api_version"]
            self._auth_kind = entry["auth_kind"]
            self._auth_ref = entry["auth_ref"]
            self._edit_auth_ref = entry["auth_ref"]
            self._label_is_auto = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        self._form = QFormLayout()
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self._form.setVerticalSpacing(10)
        root.addLayout(self._form)

        self._provider_combo = QComboBox()
        for prov in PROVIDERS:
            self._provider_combo.addItem(prov.label, prov.key)
        idx = self._provider_combo.findData(init_provider)
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)
        self._form.addRow(ai_provider_form_label("Provider"), self._provider_combo)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. Home Ollama")
        self._label_edit.textEdited.connect(self._on_label_edited)
        self._form.addRow(ai_provider_form_label("Display name"), self._label_edit)

        test_btns = QHBoxLayout()
        test_btns.setContentsMargins(0, 0, 0, 0)
        self._test_btn = QPushButton("Test connection")
        self._test_btn.setObjectName("outlineButton")
        self._test_btn.setIcon(phi("cloud-check"))
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.clicked.connect(self._on_refresh_models)
        test_btns.addWidget(self._test_btn)
        self._cancel_test_btn = QPushButton("Cancel test")
        self._cancel_test_btn.setObjectName("outlineButton")
        self._cancel_test_btn.setIcon(phi("x"))
        self._cancel_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_test_btn.clicked.connect(self._on_cancel_test)
        self._cancel_test_btn.setVisible(False)
        test_btns.addWidget(self._cancel_test_btn)
        test_btns.addStretch()
        self._test_status = QLabel("")
        self._test_status.setObjectName("mutedLabel")
        self._test_status.setWordWrap(True)
        test_col = QVBoxLayout()
        test_col.setContentsMargins(0, 0, 0, 0)
        test_col.setSpacing(6)
        test_col.addLayout(test_btns)
        test_col.addWidget(self._test_status)
        self._test_wrap = QWidget()
        self._test_wrap.setContentsMargins(0, 0, 0, 0)
        self._test_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._test_wrap.setLayout(test_col)

        self._refresh_models_btn = QPushButton("Refresh model list")
        self._refresh_models_btn.setObjectName("outlineButton")
        self._refresh_models_btn.setIcon(phi("arrow-clockwise"))
        self._refresh_models_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_models_btn.clicked.connect(self._on_refresh_models)
        self._stop_refresh_btn = QPushButton("Stop refresh")
        self._stop_refresh_btn.setObjectName("outlineButton")
        self._stop_refresh_btn.setIcon(phi("stop"))
        self._stop_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_refresh_btn.clicked.connect(self._on_stop_refresh)
        self._stop_refresh_btn.setVisible(False)
        refresh_wrap = ai_provider_field_button_strip(
            [self._refresh_models_btn, self._stop_refresh_btn]
        )

        list_panel = QFrame()
        list_panel.setObjectName("aiProviderModelsListPanel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._models_list = QListWidget()
        self._models_list.setObjectName("aiProviderModelsList")
        self._models_list.setFrameShape(QFrame.Shape.NoFrame)
        self._models_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._models_list.setMinimumHeight(120)
        self._models_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        list_layout.addWidget(self._models_list)
        self._models_list_loader = ModelsListPreviewLoader(self._models_list)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(100)
        self._log_view.setPlaceholderText("Connection log…")

        self._error_label = QLabel("")
        self._error_label.setObjectName("mutedLabel")
        self._error_label.setWordWrap(True)
        root.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("outlineButton")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self._save_btn = QPushButton("Save")
        self._save_btn.setObjectName("primaryButton")
        self._save_btn.setIcon(phi("check", color="#ffffff"))
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

        self._cred_edits: dict[str, QLineEdit | QPushButton | QLabel] = {}
        self._provider_combo.setEnabled(not self._is_edit)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._rebuild_credential_fields(init_base=init_base, init_ver=init_ver)
        self._insert_trailing_rows(refresh_wrap, list_panel)
        if not self._is_edit:
            self._apply_default_display_name()
        elif entry is not None:
            self._label_edit.setText(provider_group_label(entry))
            self._label_is_auto = not str(entry.get("provider_display_name") or "").strip()
        self._refresh_key_label()
        if self._is_edit:
            self._edit_baseline_fingerprint = self._credentials_fingerprint()
            lines = model_preview_lines_from_entries(self._edit_existing_entries)
            if lines:
                QTimer.singleShot(0, lambda: self._models_list_loader.start(lines))
        set_ui_log_sink(self._append_log)
        self.resize(580, 560)

    def _insert_trailing_rows(self, refresh_wrap: QWidget, list_panel: QWidget) -> None:
        row = self._cred_insert_row
        self._form.insertRow(row, ai_provider_form_label("Connection"), self._test_wrap)
        row += 1
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setObjectName("aiProviderDialogSeparator")
        self._form.insertRow(row, sep)
        row += 1
        self._form.insertRow(row, ai_provider_form_label("Models found"), refresh_wrap)
        row += 1
        self._form.insertRow(row, ai_provider_form_label(""), list_panel)
        row += 1
        self._form.insertRow(row, ai_provider_form_label("Log"), self._log_view)

    def _append_log(self, line: str) -> None:
        self._log_view.appendPlainText(line)
        self._log_view.verticalScrollBar().setValue(self._log_view.verticalScrollBar().maximum())

    def _apply_default_display_name(self) -> None:
        if self._label_is_auto:
            self._label_edit.setText(
                allocate_provider_display_name(
                    self._current_provider_key(),
                    self._existing_provider_display_names,
                )
            )

    def _resolved_provider_display_name(self) -> str:
        """User-entered name, or a unique catalog default when the field is empty."""
        raw = self._label_edit.text().strip()
        if raw:
            return raw
        return allocate_provider_display_name(
            self._current_provider_key(),
            self._existing_provider_display_names,
        )

    def _on_label_edited(self, _text: str) -> None:
        self._label_is_auto = False

    def _current_provider_key(self) -> str:
        data = self._provider_combo.currentData()
        return data if isinstance(data, str) else PROVIDERS[0].key

    def _on_provider_changed(self, *_a: object) -> None:
        self._invalidate_verification()
        self._rebuild_credential_fields(init_base="", init_ver="")
        self._apply_default_display_name()

    def _invalidate_verification(self) -> None:
        """Clear a successful test when credentials or URL change."""
        self._models_list_loader.cancel()
        self._provider_tested_ok = False
        self._verified_fingerprint = None
        self._fetched_models = ()
        self._test_status.setText("")
        self._models_list.clear()

    def _credentials_fingerprint(self) -> tuple[str, ...]:
        """Provider type, URL, and API key — excludes display name and Ollama default context."""
        key_material = ""
        if self._auth_kind == "token" and self._auth_ref:
            key_material = get_default_store().get(self._auth_ref) or ""
        return (
            self._current_provider_key(),
            self._collect_base_url(),
            self._collect_api_version(),
            self._auth_kind,
            self._auth_ref,
            key_material,
        )

    def _connection_is_verified(self) -> bool:
        """True when the current credentials match a successful test with models."""
        if not self._provider_tested_ok or not self._fetched_models:
            return False
        return self._verified_fingerprint == self._credentials_fingerprint()

    def _edit_connection_unchanged(self) -> bool:
        return provider_edit_allows_save_without_test(
            is_edit=self._is_edit,
            existing_entries=self._edit_existing_entries,
            baseline_fingerprint=self._edit_baseline_fingerprint,
            current_fingerprint=self._credentials_fingerprint(),
        )

    def _on_non_connection_field_edited(self, *_a: object) -> None:
        """Display name and Ollama default context do not require a connection retest."""

    def _clear_cred_rows(self) -> None:
        for widget in self._cred_row_widgets:
            self._form.removeRow(widget)
        self._cred_row_widgets.clear()
        self._cred_insert_row = 2
        self._cred_edits.clear()
        self._ollama_context_combo = None

    def _add_cred_row(self, label_text: str, field: QWidget) -> None:
        self._form.insertRow(self._cred_insert_row, ai_provider_form_label(label_text), field)
        self._cred_row_widgets.append(field)
        self._cred_insert_row += 1

    def _rebuild_credential_fields(self, *, init_base: str, init_ver: str) -> None:
        self._clear_cred_rows()
        spec = provider_by_key(self._current_provider_key())
        if spec is None:
            return
        for field in spec.credential_fields:
            if field.field_id == "api_key":
                btn = QPushButton("Set API key…")
                btn.setObjectName("outlineButton")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(self._on_set_key)
                status = QLabel()
                status.setObjectName("mutedLabel")
                wrap = ai_provider_field_button_strip([btn, status])
                self._add_cred_row(field.label, wrap)
                self._cred_edits["api_key_btn"] = btn
                self._cred_edits["api_key_label"] = status
            else:
                edit = QLineEdit()
                edit.setPlaceholderText(field.placeholder)
                if field.field_id == "base_url":
                    edit.setText(init_base or field.default or spec.default_base_url)
                elif field.field_id == "api_version":
                    edit.setText(init_ver)
                elif field.default:
                    edit.setText(field.default)
                edit.textChanged.connect(self._on_credentials_edited)
                self._add_cred_row(field.label, edit)
                self._cred_edits[field.field_id] = edit
        if spec.key == "ollama":
            self._ollama_context_combo = make_ollama_default_context_combo(
                self._init_ollama_context, self._on_non_connection_field_edited
            )
            self._add_cred_row("Default context", self._ollama_context_combo)

    def _collect_ollama_default_context(self) -> int:
        return ollama_context_tokens_from_combo(self._ollama_context_combo)

    def _on_credentials_edited(self, *_a: object) -> None:
        self._invalidate_verification()

    def _field_text(self, field_id: str) -> str:
        w = self._cred_edits.get(field_id)
        return w.text().strip() if isinstance(w, QLineEdit) else ""

    def _collect_base_url(self) -> str:
        spec = provider_by_key(self._current_provider_key())
        url = self._field_text("base_url")
        if url:
            return url
        return spec.default_base_url if spec else ""

    def _collect_api_version(self) -> str:
        return self._field_text("api_version")

    def _ensure_auth_ref(self) -> str:
        if self._auth_kind == "token" and not self._auth_ref:
            self._auth_ref = f"ai:{self._entry_id}"
        return self._auth_ref

    def _validate_credentials(self) -> str | None:
        return validate_provider_credentials(
            provider_key=self._current_provider_key(),
            auth_kind=self._auth_kind,
            auth_ref=self._auth_ref,
            base_url=self._collect_base_url(),
            api_version=self._collect_api_version(),
        )

    def _on_set_key(self) -> None:
        dlg = SecretEntryDialog(
            ref=f"ai:{self._entry_id}", kind_hint="token", title="Set API key", parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.saved_kind() == "none":
                self._auth_kind, self._auth_ref = "none", ""
            else:
                self._auth_kind, self._auth_ref = "token", dlg.saved_ref()
            self._invalidate_verification()
            self._refresh_key_label()

    def _refresh_key_label(self) -> None:
        label = self._cred_edits.get("api_key_label")
        if not isinstance(label, QLabel):
            return
        has_key = self._auth_kind != "none" and bool(self._auth_ref)
        if not has_key and get_default_store().get(f"ai:{self._entry_id}"):
            self._auth_kind, self._auth_ref = "token", f"ai:{self._entry_id}"
            has_key = True
        label.setText("Key set" if has_key else "No key set")

    def _show_models_preview(self, models: tuple[ModelSpec, ...]) -> None:
        lines = model_preview_lines_from_specs(models)
        if lines:
            self._models_list_loader.start(lines)

    def _set_test_running(self, running: bool) -> None:
        self._test_btn.setEnabled(not running)
        self._cancel_test_btn.setVisible(running)
        self._refresh_models_btn.setEnabled(not running)
        self._stop_refresh_btn.setVisible(running)
        self._save_btn.setEnabled(not running)

    def _on_refresh_models(self) -> None:
        """Fetch the model list using the current credentials."""
        self._pending_save_after_test = False
        self._start_connection_test()

    def _on_stop_refresh(self) -> None:
        """Stop an in-flight model list refresh."""
        self._on_cancel_test()

    def _on_cancel_test(self) -> None:
        """Stop an in-flight connection test without closing the dialog."""
        if self._setup_thread is None:
            return
        self._pending_save_after_test = False
        self._cancel_running_test()
        self._test_status.setText("Test cancelled.")

    def _start_connection_test(self) -> None:
        if self._setup_thread is not None:
            return
        err = self._validate_credentials()
        if err:
            self._test_status.setText(f"✗ {err}")
            if self._pending_save_after_test:
                self._pending_save_after_test = False
                self._error_label.setText(err)
            return
        self._error_label.setText("")
        self._log_view.clear()
        self._test_status.setText("Testing…")
        self._set_test_running(True)
        self._ensure_auth_ref()
        self._setup_thread = QThread()
        self._setup_worker = AiProviderSetupWorker()
        self._setup_worker.set_params(
            provider_key=self._current_provider_key(),
            base_url=self._collect_base_url(),
            api_version=self._collect_api_version(),
            auth_kind=self._auth_kind,
            auth_ref=self._auth_ref,
            entry_id=self._entry_id,
            ollama_default_context=self._collect_ollama_default_context(),
        )
        self._setup_worker.moveToThread(self._setup_thread)
        self._setup_thread.started.connect(self._setup_worker.run)
        self._setup_worker.log_line.connect(self._append_log, Qt.ConnectionType.QueuedConnection)
        self._setup_worker.finished.connect(
            self._on_setup_finished, Qt.ConnectionType.QueuedConnection
        )
        self._setup_worker.finished.connect(self._setup_thread.quit)
        self._setup_thread.finished.connect(self._on_setup_thread_done)
        self._setup_thread.start()

    def _on_setup_finished(self, ok: bool, detail: str, models_obj: object) -> None:
        if self._setup_thread is None:
            return
        pending_save = self._pending_save_after_test
        self._pending_save_after_test = False
        self._provider_tested_ok = ok
        self._test_status.setText(f"{'✓' if ok else '✗'} {detail}")
        models = models_obj if isinstance(models_obj, tuple) else ()
        self._fetched_models = tuple(m for m in models if isinstance(m, ModelSpec))
        if ok and self._fetched_models:
            self._verified_fingerprint = self._credentials_fingerprint()
            self._show_models_preview(self._fetched_models)
        else:
            self._verified_fingerprint = None
        if pending_save:
            if ok and self._fetched_models:
                self._error_label.setText("")
                self.accept()
            else:
                msg = detail if detail else "Connection test failed."
                self._error_label.setText(msg)
                self._test_btn.setFocus()

    def _on_setup_thread_done(self) -> None:
        self._setup_worker, self._setup_thread = release_provider_setup_thread(
            self._setup_thread,
            self._setup_worker,
            set_test_running=self._set_test_running,
        )

    def _cancel_running_test(self) -> None:
        """Stop an in-flight test; blocks until the worker thread has exited."""
        self._setup_worker, self._setup_thread = cancel_provider_setup_thread(
            self._setup_thread,
            self._setup_worker,
            disconnect_worker=lambda w: disconnect_provider_setup_worker(
                w,
                log_slot=self._append_log,
                finished_slot=self._on_setup_finished,
            ),
            set_test_running=self._set_test_running,
        )

    def _on_accept(self) -> None:
        if self._setup_thread is not None:
            return
        err = self._validate_credentials()
        if err:
            self._error_label.setText(err)
            return
        if self._connection_is_verified() or self._edit_connection_unchanged():
            self._error_label.setText("")
            self.accept()
            return
        self._pending_save_after_test = True
        self._start_connection_test()

    def result_entries(self) -> list[AiModelEntry]:
        """All model rows to store. Call only after :meth:`exec` accepts."""
        if self._connection_is_verified() and self._fetched_models:
            return entries_from_model_specs(
                provider_template_entry(
                    entry_id=self._entry_id,
                    provider_key=self._current_provider_key(),
                    base_url=self._collect_base_url(),
                    api_version=self._collect_api_version(),
                    auth_kind=self._auth_kind,
                    auth_ref=self._ensure_auth_ref(),
                    default_context=self._collect_ollama_default_context(),
                ),
                self._fetched_models,
                provider_display_name=self._resolved_provider_display_name(),
            )
        if self._edit_connection_unchanged():
            return apply_provider_edit_entries(
                self._edit_existing_entries,
                provider_display_name=self._resolved_provider_display_name(),
                provider_key=self._current_provider_key(),
                default_context=self._collect_ollama_default_context(),
            )
        return []

    def replace_auth_ref(self) -> str:
        """Auth ref of the provider being edited (empty when adding)."""
        return self._edit_auth_ref if self._is_edit else ""

    def _stop_log_and_test(self) -> None:
        self._models_list_loader.cancel()
        set_ui_log_sink(None)
        self._cancel_running_test()

    def reject(self) -> None:
        """Cancel the dialog and stop any in-flight connection test."""
        self._stop_log_and_test()
        super().reject()

    def done(self, r: int) -> None:
        """Close the dialog and stop any in-flight connection test."""
        self._stop_log_and_test()
        super().done(r)


__all__ = ["AiProviderDialog"]
