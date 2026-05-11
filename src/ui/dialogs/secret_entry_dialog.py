"""Modal for entering / clearing auth secrets for private package registries.

Used by the Settings dialog's "Private packages" section. Three modes:

* **Token** (default) — ``_authToken`` for npm/JSR ``.npmrc`` or a bearer
  token for PyPI; stored as a single opaque string.
* **Basic** — ``user`` + ``password`` combined into a base64-encoded
  ``user:password`` blob suitable for ``_auth=`` in ``.npmrc``.
* **None** — explicit "clear stored secret" action.

The dialog never persists the raw value to ``QSettings``; it writes to the
configured :class:`~services.scripting.secret_store.SecretStore` and returns
the *ref* string the caller embeds in its row.
"""

from __future__ import annotations

import base64
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from services.scripting.secret_store import SecretStore, get_default_store
from ui.styling.icons import phi


class SecretEntryDialog(QDialog):
    """Token / basic / none entry. Returns the ref via :meth:`saved_ref`."""

    AUTH_TOKEN = "token"
    AUTH_BASIC = "basic"
    AUTH_NONE = "none"

    def __init__(
        self,
        *,
        ref: str,
        kind_hint: str = "token",
        title: str = "Set authentication",
        parent: QWidget | None = None,
        store: SecretStore | None = None,
    ) -> None:
        """Build the modal.

        *ref* is the opaque keyring key the caller has chosen (e.g.
        ``npm:@mycompany``). *kind_hint* preselects the radio. *store* is
        injectable for tests; defaults to the process-wide store.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        self._ref = ref
        self._store: SecretStore = store or get_default_store()
        self._saved_ref: str = ""
        self._saved_kind: str = self.AUTH_NONE

        root = QVBoxLayout(self)
        root.setSpacing(10)

        intro = QLabel(
            f"Stored under <code>{ref}</code> in {self._store.backend_id.replace('_', ' ')}."
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setObjectName("mutedLabel")
        root.addWidget(intro)

        # -- Mode radios -----------------------------------------------
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        self._token_radio = QRadioButton("Token")
        self._token_radio.setToolTip(
            "Bearer/_authToken style. Use for most modern registries "
            "(Verdaccio, Nexus, Cloudsmith, GitHub Packages, PyPI tokens)."
        )
        self._basic_radio = QRadioButton("Basic (user:password)")
        self._basic_radio.setToolTip(
            "Encoded as base64 ``user:password`` and emitted as "
            "``_auth=`` in .npmrc."
        )
        self._none_radio = QRadioButton("None / clear")
        self._none_radio.setToolTip(
            "Remove any stored secret for this registry — useful for "
            "public mirrors that don't need authentication."
        )
        for r in (self._token_radio, self._basic_radio, self._none_radio):
            r.setCursor(Qt.CursorShape.PointingHandCursor)
            mode_row.addWidget(r)
        mode_row.addStretch()
        root.addLayout(mode_row)
        self._group = QButtonGroup(self)
        self._group.addButton(self._token_radio)
        self._group.addButton(self._basic_radio)
        self._group.addButton(self._none_radio)

        # -- Token field -----------------------------------------------
        self._token_label = QLabel("Token")
        self._token_label.setObjectName("sectionLabel")
        root.addWidget(self._token_label)
        token_row = QHBoxLayout()
        token_row.setContentsMargins(0, 0, 0, 0)
        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText("Paste your access token")
        token_row.addWidget(self._token_edit, 1)
        self._show_token_btn = QPushButton()
        self._show_token_btn.setIcon(phi("eye"))
        self._show_token_btn.setCheckable(True)
        self._show_token_btn.setObjectName("iconButton")
        self._show_token_btn.setFixedSize(28, 28)
        self._show_token_btn.setToolTip("Show / hide the token")
        self._show_token_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_token_btn.toggled.connect(self._toggle_token_visibility)
        token_row.addWidget(self._show_token_btn)
        root.addLayout(token_row)

        # -- Basic fields ----------------------------------------------
        self._user_label = QLabel("Username")
        self._user_label.setObjectName("sectionLabel")
        root.addWidget(self._user_label)
        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("e.g. ci-readonly")
        root.addWidget(self._user_edit)

        self._pass_label = QLabel("Password")
        self._pass_label.setObjectName("sectionLabel")
        root.addWidget(self._pass_label)
        pass_row = QHBoxLayout()
        pass_row.setContentsMargins(0, 0, 0, 0)
        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_row.addWidget(self._pass_edit, 1)
        self._show_pass_btn = QPushButton()
        self._show_pass_btn.setIcon(phi("eye"))
        self._show_pass_btn.setCheckable(True)
        self._show_pass_btn.setObjectName("iconButton")
        self._show_pass_btn.setFixedSize(28, 28)
        self._show_pass_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_pass_btn.toggled.connect(self._toggle_pass_visibility)
        pass_row.addWidget(self._show_pass_btn)
        root.addLayout(pass_row)

        # -- Buttons ----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("outlineButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryButton")
        save_btn.setIcon(phi("check", color="#ffffff"))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        self._group.buttonToggled.connect(self._on_mode_changed)
        if kind_hint == self.AUTH_BASIC:
            self._basic_radio.setChecked(True)
        elif kind_hint == self.AUTH_NONE:
            self._none_radio.setChecked(True)
        else:
            self._token_radio.setChecked(True)
        self._on_mode_changed()

    def _on_mode_changed(self, *_args: Any) -> None:
        token_active = self._token_radio.isChecked()
        basic_active = self._basic_radio.isChecked()
        for w in (self._token_label, self._token_edit, self._show_token_btn):
            w.setVisible(token_active)
        for w in (
            self._user_label,
            self._user_edit,
            self._pass_label,
            self._pass_edit,
            self._show_pass_btn,
        ):
            w.setVisible(basic_active)

    def _toggle_token_visibility(self, checked: bool) -> None:
        self._token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _toggle_pass_visibility(self, checked: bool) -> None:
        self._pass_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_save(self) -> None:
        if self._none_radio.isChecked():
            self._store.delete(self._ref)
            self._saved_kind = self.AUTH_NONE
            self._saved_ref = ""
            self.accept()
            return
        if self._token_radio.isChecked():
            secret = self._token_edit.text().strip()
            if not secret:
                self.reject()
                return
            self._store.put(self._ref, secret)
            self._saved_kind = self.AUTH_TOKEN
            self._saved_ref = self._ref
            self.accept()
            return
        if self._basic_radio.isChecked():
            user = self._user_edit.text().strip()
            password = self._pass_edit.text()
            if not user:
                self.reject()
                return
            blob = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            self._store.put(self._ref, blob)
            self._saved_kind = self.AUTH_BASIC
            self._saved_ref = self._ref
            self.accept()
            return

    def saved_ref(self) -> str:
        """Return the ref string written (empty on clear or cancel)."""
        return self._saved_ref

    def saved_kind(self) -> str:
        """Return ``"token"``, ``"basic"``, or ``"none"`` (matches RegistryEntry)."""
        return self._saved_kind


__all__ = ["SecretEntryDialog"]
