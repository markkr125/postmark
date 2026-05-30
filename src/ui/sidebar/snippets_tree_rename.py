"""In-place rename overlays for the snippets sidebar tree."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from services.snippet_service import SnippetService
from ui.sidebar.snippets_tree_constants import (
    KIND_CATEGORY,
    KIND_LANGUAGE,
    KIND_SNIPPET,
    ROLE_LANG_KEY,
    ROLE_NODE_KIND,
    ROLE_OLD_NAME,
    ROLE_SNIPPET_ID,
)
from ui.sidebar.snippets_tree_display import folder_label_rect, snippet_name_rect

_RENAME_EDIT_OBJECT = "snippetTreeRenameEdit"


class SnippetsInlineRename(QObject):
    """Overlay rename for snippet leaves and category folders (like local scripts)."""

    def __init__(
        self,
        tree: QTreeWidget,
        *,
        on_mutated: Callable[[], None],
        parent_widget: QWidget,
    ) -> None:
        """Attach to *tree*; call *on_mutated* after a successful persist."""
        super().__init__(tree)
        self._tree = tree
        self._on_mutated = on_mutated
        self._parent = parent_widget
        self._line_edit: QLineEdit | None = None
        self._item: QTreeWidgetItem | None = None
        self._kind: str | None = None
        self._committing = False
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def is_active(self) -> bool:
        """Return whether a rename overlay is open."""
        return self._line_edit is not None and self._line_edit.isVisible()

    def start_snippet(self, item: QTreeWidgetItem) -> None:
        """Show an overlay editor on a snippet leaf."""
        if item.data(0, ROLE_NODE_KIND) != KIND_SNIPPET:
            return
        current = str(item.text(1) or item.text(0) or "")
        row_rect = self._tree.visualItemRect(item)
        self._open_editor(item, KIND_SNIPPET, current, snippet_name_rect(row_rect))

    def start_category(self, item: QTreeWidgetItem) -> None:
        """Show an overlay editor on a category folder row."""
        if item.data(0, ROLE_NODE_KIND) != KIND_CATEGORY:
            return
        current = str(item.text(0) or item.text(1) or "")
        row_rect = self._tree.visualItemRect(item)
        self._open_editor(item, KIND_CATEGORY, current, folder_label_rect(self._tree, item, row_rect))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Commit or cancel rename when the user clicks away or presses Escape."""
        edit = self._line_edit
        if edit is None or not edit.isVisible():
            return False

        if (
            event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            self._cancel_active()
            return True

        if event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            gp = event.globalPosition().toPoint()
            local = edit.mapFromGlobal(gp)
            if not edit.rect().contains(local):
                self._commit_active(from_return=False)
                return True
        return False

    def _open_editor(
        self,
        item: QTreeWidgetItem,
        kind: str,
        text: str,
        name_rect,
    ) -> None:
        """Create a focused overlay ``QLineEdit`` over *name_rect*."""
        self._dismiss_active()
        item.setData(1, ROLE_OLD_NAME, text)
        self._item = item
        self._kind = kind

        line_edit = QLineEdit(text, self._tree.viewport())
        line_edit.setObjectName(_RENAME_EDIT_OBJECT)
        line_edit.setProperty("rename_armed", False)
        line_edit.setGeometry(name_rect)
        line_edit.selectAll()
        line_edit.show()
        line_edit.setFocus()
        self._line_edit = line_edit

        line_edit.returnPressed.connect(lambda: self._commit_active(from_return=True))

        def _arm() -> None:
            if self._line_edit is line_edit:
                line_edit.setProperty("rename_armed", True)
                line_edit.editingFinished.connect(
                    lambda: self._commit_active(from_return=False)
                )

        QTimer.singleShot(0, _arm)

    def _commit_active(self, *, from_return: bool) -> None:
        """Persist rename or no-op; always tear down the overlay."""
        edit = self._line_edit
        item = self._item
        kind = self._kind
        if edit is None or item is None or kind is None:
            return
        if self._committing:
            return
        if not from_return and not edit.isVisible():
            return
        if not from_return and not edit.property("rename_armed"):
            return

        self._committing = True
        try:
            old_name = item.data(1, ROLE_OLD_NAME)
            fallback = old_name if isinstance(old_name, str) else ""
            new_name = edit.text().strip()
            self._clear_editor()

            if kind == KIND_SNIPPET:
                self._commit_snippet(item, fallback, new_name)
            elif kind == KIND_CATEGORY:
                self._commit_category(item, fallback, new_name)
        finally:
            self._committing = False

    def _cancel_active(self) -> None:
        """Discard edits and close the overlay."""
        item = self._item
        kind = self._kind
        old_name = item.data(1, ROLE_OLD_NAME) if item is not None else None
        self._clear_editor()
        if item is None or not isinstance(old_name, str):
            return
        if kind == KIND_CATEGORY:
            item.setText(0, old_name)
            item.setText(1, old_name)
        elif kind == KIND_SNIPPET:
            item.setText(1, old_name)

    def _commit_snippet(self, item: QTreeWidgetItem, fallback: str, new_name: str) -> None:
        """Save a renamed snippet leaf."""
        sid = item.data(0, ROLE_SNIPPET_ID)
        item.setData(1, ROLE_OLD_NAME, None)
        if not isinstance(sid, int):
            return
        if not new_name:
            QMessageBox.warning(self._parent, "Rename snippet", "Enter a snippet name.")
            return
        if new_name == fallback:
            return
        try:
            SnippetService.update(sid, name=new_name)
        except ValueError as exc:
            QMessageBox.warning(self._parent, "Rename snippet", str(exc))
            return
        self._on_mutated()

    def _commit_category(self, item: QTreeWidgetItem, fallback: str, new_name: str) -> None:
        """Save a renamed category folder."""
        item.setData(1, ROLE_OLD_NAME, None)
        if not new_name or new_name == fallback:
            item.setText(0, fallback)
            item.setText(1, fallback)
            return

        lang_item = item.parent()
        if lang_item is None:
            item.setText(0, fallback)
            item.setText(1, fallback)
            return

        lang_key = lang_item.data(0, ROLE_LANG_KEY)
        if lang_item.data(0, ROLE_NODE_KIND) != KIND_LANGUAGE or not isinstance(lang_key, str):
            item.setText(0, fallback)
            item.setText(1, fallback)
            return

        SnippetService.rename_category(lang_key, fallback, new_name)
        self._on_mutated()

    def _clear_editor(self) -> None:
        """Hide and destroy the active overlay editor."""
        edit = self._line_edit
        if edit is not None:
            edit.hide()
            edit.deleteLater()
        self._line_edit = None
        self._item = None
        self._kind = None

    def _dismiss_active(self) -> None:
        """Commit pending rename via click-away handling, then close."""
        if self.is_active():
            self._commit_active(from_return=False)
        else:
            self._clear_editor()
