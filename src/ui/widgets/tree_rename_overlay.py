"""Click-away and Escape handling for tree overlay rename editors."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLineEdit
from shiboken6 import Shiboken


class TreeRenameClickAway(QObject):
    """Commit or cancel a single active rename ``QLineEdit`` on outside click / Escape."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Install an application-wide event filter when the app exists."""
        super().__init__(parent)
        self._line_edit: QLineEdit | None = None
        self._on_commit: Callable[[], None] | None = None
        self._on_cancel: Callable[[], None] | None = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _valid_edit(self) -> QLineEdit | None:
        """Return the active editor when its C++ object is still alive."""
        edit = self._line_edit
        if edit is None or not Shiboken.isValid(edit):
            self._clear()
            return None
        return edit

    def is_active(self) -> bool:
        """Return whether a rename overlay is visible."""
        edit = self._valid_edit()
        return edit is not None and edit.isVisible()

    def arm(
        self,
        line_edit: QLineEdit,
        *,
        on_commit: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Track *line_edit* until commit, cancel, or a new ``arm`` replaces it."""
        self.dismiss_active(commit=True)
        self._line_edit = line_edit
        self._on_commit = on_commit
        self._on_cancel = on_cancel

    def dismiss_active(self, *, commit: bool) -> None:
        """Finish the current rename with commit or cancel if one is open."""
        if not self.is_active():
            self._clear()
            return
        if commit:
            self._try_commit()
        elif self._on_cancel is not None:
            self._on_cancel()
        self._clear()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Commit on outside click; cancel on Escape."""
        edit = self._valid_edit()
        if edit is None or not edit.isVisible():
            return False

        if (
            event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            if self._on_cancel is not None:
                self._on_cancel()
            self._clear()
            return True

        if event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            gp = event.globalPosition().toPoint()
            local = edit.mapFromGlobal(gp)
            if not edit.rect().contains(local):
                self._try_commit()
                self._clear()
                return True
        return False

    def _try_commit(self) -> None:
        """Invoke the commit callback when the editor is armed."""
        edit = self._valid_edit()
        if edit is None or not edit.property("rename_armed"):
            return
        if self._on_commit is not None:
            self._on_commit()

    def release(self) -> None:
        """Drop references without committing or cancelling."""
        self._clear()

    def _clear(self) -> None:
        """Drop references to the active editor."""
        self._line_edit = None
        self._on_commit = None
        self._on_cancel = None
