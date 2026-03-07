"""Floating popup that displays resolved variable details on hover.

When the user hovers over a ``{{variable}}`` reference in any input
widget, this popup appears near the cursor showing:

* The variable name.
* The resolved value (editable).
* The source — ``Collection``, ``Environment``, or ``Local``.

The user can:
* **Edit + Update** → persist the value globally.
* **Edit + close** → store as a per-request local override.
* **Reset** → revert a local override back to the original value.
* **Add to** (unresolved only) → create the variable in a collection
  or environment.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QEnterEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

if TYPE_CHECKING:
    from services.environment_service import VariableDetail

# Grace period (seconds) after show — prevents the triggering hover from
# immediately closing the popup.
_SHOW_GRACE_SEC = 0.15

# Auto-hide timeout (ms) — popup closes automatically after this delay
# unless the mouse is over it or the value input has focus.
_AUTO_HIDE_MS = 8000

# Delay (ms) before showing the popup on hover.  Shorter than the
# default Qt tooltip delay (~700 ms) for a snappier feel.
_HOVER_DELAY_MS = 150


class VariablePopup(QFrame):
    """Floating popup showing a variable's resolved value and source.

    Styled via the global QSS rule targeting
    ``objectName="variablePopup"``.  Inherits ``QFrame`` so that QSS
    ``border`` renders reliably on frameless top-level windows.

    The popup auto-closes on:
    * Click outside.
    * ``Escape`` key.
    * Timeout (:data:`_AUTO_HIDE_MS`) when not being interacted with.
    * Parent window move/resize.
    """

    # Singleton — only one variable popup should be visible at a time.
    _instance: VariablePopup | None = None

    # Callback invoked when the user clicks Update.  Set once by
    # MainWindow via :meth:`set_save_callback`.
    # Signature: ``(var_name, new_value, source, source_id) -> None``
    _save_callback: Callable[[str, str, str, int], None] | None = None

    # Callback invoked when the popup closes with an edited value
    # that was NOT persisted via Update.  The override applies only
    # to the current request tab ("use for this request only").
    # Signature: ``(var_name, new_value, source, source_id) -> None``
    _local_override_callback: Callable[[str, str, str, int], None] | None = None

    # Callback invoked when the user clicks Reset on a local override.
    # Signature: ``(var_name) -> None``
    _reset_local_override_callback: Callable[[str], None] | None = None

    # Callback invoked when the user adds an unresolved variable.
    # Signature: ``(var_name, value, target) -> None``
    # *target* is ``"collection"`` or ``"environment"``.
    _add_variable_callback: Callable[[str, str, str], None] | None = None

    # Whether an environment is currently selected.  Updated by
    # ``MainWindow`` whenever the active environment changes.
    _has_environment: bool = False

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the popup with frameless tool-window flags."""
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("variablePopup")
        self.setFixedWidth(280)

        self._show_time: float = 0.0
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.close)

        # State from the last _populate call
        self._var_name: str = ""
        self._source: str = ""
        self._source_id: int = 0
        self._original_value: str = ""
        self._is_local: bool = False
        self._persisted: bool = False  # True when Update was clicked
        self._reset_clicked: bool = False  # True when Reset clicked on local

        # -- Layout ---------------------------------------------------
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # Variable name title
        self._name_label = QLabel()
        self._name_label.setObjectName("variablePopupName")
        root.addWidget(self._name_label)

        # Resolved value in an editable input
        self._value_input = QLineEdit()
        self._value_input.setObjectName("variablePopupValue")
        self._value_input.textChanged.connect(self._on_value_changed)
        root.addWidget(self._value_input)

        # Bottom row: source badge + action buttons
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)

        self._source_badge = QLabel()
        self._source_badge.setObjectName("variablePopupBadge")
        bottom_row.addWidget(self._source_badge)
        bottom_row.addStretch()

        self._update_btn = QPushButton("Update")
        self._update_btn.setObjectName("variablePopupUpdateBtn")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setFixedHeight(22)
        self._update_btn.clicked.connect(self._on_update_clicked)
        self._update_btn.hide()
        bottom_row.addWidget(self._update_btn)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setObjectName("variablePopupResetBtn")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setFixedHeight(22)
        self._reset_btn.clicked.connect(self._on_reset_clicked)
        self._reset_btn.hide()
        bottom_row.addWidget(self._reset_btn)

        root.addLayout(bottom_row)

        # -- Unresolved: "Add to" select box --------------------------
        self._add_select = QPushButton("Add to \u25be")
        self._add_select.setObjectName("variablePopupAddSelect")
        self._add_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_select.setFixedHeight(26)
        self._add_select.clicked.connect(self._toggle_add_panel)
        root.addWidget(self._add_select)

        # Inline dropdown panel (expands below the select box)
        self._add_panel = QFrame()
        self._add_panel.setObjectName("variablePopupAddPanel")
        panel_layout = QVBoxLayout(self._add_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Warning label for missing environment
        self._no_env_label = QLabel("No environment selected.")
        self._no_env_label.setObjectName("variablePopupNoEnv")
        self._no_env_label.setWordWrap(True)
        panel_layout.addWidget(self._no_env_label)

        # Target buttons
        self._target_collection = QPushButton("  \u24b8  Collection")
        self._target_collection.setObjectName("variablePopupTarget")
        self._target_collection.setCursor(Qt.CursorShape.PointingHandCursor)
        self._target_collection.clicked.connect(lambda: self._on_add_target("collection"))
        panel_layout.addWidget(self._target_collection)

        self._target_environment = QPushButton("  \u24ba  Environment")
        self._target_environment.setObjectName("variablePopupTarget")
        self._target_environment.setCursor(Qt.CursorShape.PointingHandCursor)
        self._target_environment.clicked.connect(lambda: self._on_add_target("environment"))
        panel_layout.addWidget(self._target_environment)

        root.addWidget(self._add_panel)

        # Start hidden
        self._add_select.hide()
        self._add_panel.hide()

    # -- Class-level configuration ------------------------------------

    @classmethod
    def set_save_callback(
        cls,
        callback: Callable[[str, str, str, int], None] | None,
    ) -> None:
        """Register a callback for variable update persistence.

        Called once by ``MainWindow`` during initialisation.  The
        callback receives ``(var_name, new_value, source, source_id)``.
        """
        cls._save_callback = callback

    @classmethod
    def set_local_override_callback(
        cls,
        callback: Callable[[str, str, str, int], None] | None,
    ) -> None:
        """Register a callback for per-request variable overrides.

        Called once by ``MainWindow`` during initialisation.  The
        callback receives ``(var_name, new_value, source, source_id)``
        when the popup closes with an edited value that the user chose
        not to persist globally.
        """
        cls._local_override_callback = callback

    @classmethod
    def set_reset_local_override_callback(
        cls,
        callback: Callable[[str], None] | None,
    ) -> None:
        """Register a callback to remove a per-request local override.

        Called once by ``MainWindow`` during initialisation.  The
        callback receives ``(var_name,)`` when the user clicks
        **Reset** on a locally-overridden variable.
        """
        cls._reset_local_override_callback = callback

    @classmethod
    def set_add_variable_callback(
        cls,
        callback: Callable[[str, str, str], None] | None,
    ) -> None:
        """Register a callback for creating an unresolved variable.

        Called once by ``MainWindow`` during initialisation.  The
        callback receives ``(var_name, value, target)`` where *target*
        is ``"collection"`` or ``"environment"``.
        """
        cls._add_variable_callback = callback

    @classmethod
    def set_has_environment(cls, has_env: bool) -> None:
        """Update whether an environment is currently selected.

        Called by ``MainWindow`` whenever the active environment
        changes so the popup can show/hide the no-env warning.
        """
        cls._has_environment = has_env

    # -- Public API ---------------------------------------------------

    @classmethod
    def show_variable(
        cls,
        var_name: str,
        detail: VariableDetail | None,
        global_pos: QPoint,
        parent: QWidget | None = None,
    ) -> None:
        """Show the popup for *var_name* near *global_pos*.

        If *detail* is ``None`` the variable is shown as unresolved.
        Re-uses a singleton instance so that at most one popup is
        visible at any time.
        """
        # Dismiss any existing popup
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

        popup = cls(parent)
        cls._instance = popup
        popup._populate(var_name, detail)
        popup._show_at(global_pos)

    @classmethod
    def hide_popup(cls) -> None:
        """Close the currently visible popup, if any."""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

    @classmethod
    def hover_delay_ms(cls) -> int:
        """Return the recommended hover delay before showing the popup."""
        return _HOVER_DELAY_MS

    # -- Internal -----------------------------------------------------

    def _populate(self, var_name: str, detail: VariableDetail | None) -> None:
        """Fill in the popup content."""
        self._var_name = var_name
        self._is_local = False
        self._persisted = False
        self._reset_clicked = False

        self._name_label.setText(var_name)

        if detail is not None:
            is_local: bool = detail.get("is_local", False)
            self._is_local = is_local
            self._original_value = detail["value"]
            self._source = detail["source"]
            self._source_id = detail["source_id"]
            self._value_input.setText(detail["value"])
            self._value_input.setReadOnly(False)
            self._value_input.setPlaceholderText("")

            if is_local:
                # Local override — show "Local" badge with buttons
                self._source_badge.setText("Local")
                self._source_badge.setProperty("varSource", "local")
                self._update_btn.show()
                self._reset_btn.show()
            else:
                source = detail["source"].capitalize()
                self._source_badge.setText(source)
                self._source_badge.setProperty("varSource", detail["source"])
                self._update_btn.hide()
                self._reset_btn.hide()

            # Hide "Add to" for resolved variables
            self._add_select.hide()
            self._add_panel.hide()
        else:
            self._original_value = ""
            self._source = "unresolved"
            self._source_id = 0
            self._value_input.setText("")
            self._value_input.setReadOnly(False)
            self._value_input.setPlaceholderText("Enter value")
            self._source_badge.setText("Unresolved")
            self._source_badge.setProperty("varSource", "unresolved")

            # Hide Update/Reset for unresolved
            self._update_btn.hide()
            self._reset_btn.hide()

            # Show "Add to" toggle
            self._setup_add_targets()

        # Force QSS re-evaluation for the badge property selector
        self._source_badge.style().unpolish(self._source_badge)
        self._source_badge.style().polish(self._source_badge)

    def _setup_add_targets(self) -> None:
        """Configure the 'Add to' select box for unresolved variables."""
        has_env = VariablePopup._has_environment
        self._no_env_label.setVisible(not has_env)
        self._target_collection.setEnabled(False)  # disabled until value entered
        self._target_environment.setEnabled(False)
        self._add_select.setText("Add to \u25be")
        self._add_select.show()
        self._add_panel.hide()  # collapsed by default

    def _show_at(self, global_pos: QPoint) -> None:
        """Position the popup near *global_pos* and show it.

        Adjusts placement so the popup stays on-screen.
        """
        self.adjustSize()
        # Offset slightly so the popup doesn't overlap the cursor
        target = QPoint(global_pos.x() + 8, global_pos.y() + 12)
        screen = QApplication.screenAt(global_pos)
        if screen is not None:
            geo = screen.availableGeometry()
            if target.x() + self.width() > geo.right():
                target.setX(global_pos.x() - self.width() - 4)
            if target.y() + self.sizeHint().height() > geo.bottom():
                target.setY(global_pos.y() - self.sizeHint().height() - 4)

        self.move(target)
        self._show_time = time.monotonic()
        self.show()
        self._auto_hide_timer.start(_AUTO_HIDE_MS)

        # Install app-wide event filter for click-outside dismiss
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # -- Value editing ------------------------------------------------

    def _on_value_changed(self, text: str) -> None:
        """Show or hide action buttons when the value diverges."""
        if self._source == "unresolved":
            has_value = bool(text.strip())
            has_env = VariablePopup._has_environment
            self._target_collection.setEnabled(has_value)
            self._target_environment.setEnabled(has_value and has_env)
            # Collapse panel when value is cleared
            if not has_value and not self._add_panel.isHidden():
                self._toggle_add_panel()
            return

        if self._is_local:
            # For local overrides, buttons stay visible always
            return

        changed = text != self._original_value
        self._update_btn.setVisible(changed)
        self._reset_btn.setVisible(changed)
        # Pause auto-hide while the user is editing
        if self._value_input.hasFocus():
            self._auto_hide_timer.stop()

    def _on_update_clicked(self) -> None:
        """Persist the edited variable value and close the popup."""
        new_value = self._value_input.text()
        cb = VariablePopup._save_callback
        if cb is not None and self._source != "unresolved":
            cb(
                self._var_name,
                new_value,
                self._source,
                self._source_id,
            )
        self._persisted = True
        self.close()

    def _on_reset_clicked(self) -> None:
        """Reset the value input or remove a local override."""
        if self._is_local:
            # Remove the local override and close
            cb = VariablePopup._reset_local_override_callback
            if cb is not None:
                cb(self._var_name)
            self._reset_clicked = True
            self.close()
        else:
            self._value_input.setText(self._original_value)

    def _toggle_add_panel(self) -> None:
        """Expand or collapse the inline target list."""
        expanding = self._add_panel.isHidden()
        self._add_panel.setVisible(expanding)
        arrow = "\u25b4" if expanding else "\u25be"
        self._add_select.setText(f"Add to {arrow}")
        self.adjustSize()

    def _on_add_target(self, target: str) -> None:
        """Add the unresolved variable to *target*."""
        value = self._value_input.text().strip()
        if not value:
            return
        cb = VariablePopup._add_variable_callback
        if cb is not None:
            cb(self._var_name, value, target)
        self._persisted = True
        self.close()

    # -- Dismiss behaviour --------------------------------------------

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        """Close on click-outside or parent window move/resize."""
        etype = event.type()

        # Close when any top-level window moves or resizes.
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
            click_pos = event.globalPosition().toPoint()
            if not self.geometry().contains(click_pos):
                self.close()
                return False

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Close on Escape, save on Enter/Return."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._update_btn.isVisible():
                self._on_update_clicked()
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        """Stop auto-hide timer while mouse is over the popup."""
        self._auto_hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Restart auto-hide timer when mouse leaves the popup."""
        if not self._value_input.hasFocus():
            self._auto_hide_timer.start(_AUTO_HIDE_MS)
        super().leaveEvent(event)

    def closeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        """Remove the event filter, emit local override if needed, and clear singleton."""
        self._auto_hide_timer.stop()

        # If the value was edited but not persisted via Update and not
        # reset, treat it as a local (per-request) override.
        new_value = self._value_input.text()
        if (
            not self._persisted
            and not self._reset_clicked
            and new_value != self._original_value
            and self._source != "unresolved"
        ):
            cb = VariablePopup._local_override_callback
            if cb is not None:
                cb(self._var_name, new_value, self._source, self._source_id)

        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if VariablePopup._instance is self:
            VariablePopup._instance = None
        super().closeEvent(event)  # type: ignore[arg-type]
