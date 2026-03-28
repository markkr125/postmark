"""Version history dialog with timeline and diff viewer.

Opens from the Scripts tab History button.  Shows a timeline of script
snapshots and a side-by-side diff viewer for comparing versions.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.script_version_service import ScriptVersionService
from ui.styling import theme
from ui.styling.icons import phi
from ui.widgets.code_editor import CodeEditorWidget

# Custom data role for version ID.
_ROLE_VERSION_ID = Qt.ItemDataRole.UserRole + 1


class VersionHistoryDialog(QDialog):
    """Dialog showing script version timeline and side-by-side diff."""

    def __init__(
        self,
        *,
        request_id: int | None,
        collection_id: int | None,
        current_pre: str,
        current_test: str,
        parent: QWidget | None = None,
    ) -> None:
        """Build the version history dialog."""
        super().__init__(parent)
        self.setWindowTitle("Script Version History")
        self.resize(900, 600)

        self._request_id = request_id
        self._collection_id = collection_id
        self._current_pre = current_pre
        self._current_test = current_test
        self._restored: tuple[str, str] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Bottom button row (created early so _on_tab_changed can access)
        self._restore_btn = QPushButton("Restore Selected")
        self._restore_btn.setIcon(phi("arrow-counter-clockwise", size=14))
        self._restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restore_btn.setEnabled(False)
        self._restore_btn.clicked.connect(self._on_restore)

        # Script type tabs
        self._type_tabs = QTabWidget()
        self._type_tabs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._type_tabs.currentChanged.connect(self._on_tab_changed)

        # Pre-request tab
        pre_widget = QWidget()
        pre_layout = QHBoxLayout(pre_widget)
        pre_layout.setContentsMargins(0, 0, 0, 0)
        self._pre_list, self._pre_viewer = self._build_tab(pre_layout)
        self._type_tabs.addTab(pre_widget, "Pre-request Script")

        # Test tab
        test_widget = QWidget()
        test_layout = QHBoxLayout(test_widget)
        test_layout.setContentsMargins(0, 0, 0, 0)
        self._test_list, self._test_viewer = self._build_tab(test_layout)
        self._type_tabs.addTab(test_widget, "Test Script")

        root.addWidget(self._type_tabs, 1)

        # Bottom button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._restore_btn)

        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        # Load versions
        self._load_versions()

    # -- Layout helpers ------------------------------------------------

    def _build_tab(self, layout: QHBoxLayout) -> tuple[QListWidget, _DiffViewer]:
        """Build a version-list + diff-viewer pair inside *layout*."""
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Version list
        version_list = QListWidget()
        version_list.setMaximumWidth(220)
        version_list.currentItemChanged.connect(self._on_version_selected)
        splitter.addWidget(version_list)

        # Diff viewer
        viewer = _DiffViewer()
        splitter.addWidget(viewer)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        return version_list, viewer

    # -- Data loading --------------------------------------------------

    def _load_versions(self) -> None:
        """Fetch and display versions for both script types."""
        self._load_type_versions(self._pre_list, "pre_request", self._current_pre)
        self._load_type_versions(self._test_list, "test", self._current_test)

    def _load_type_versions(
        self,
        list_widget: QListWidget,
        script_type: str,
        current_content: str,
    ) -> None:
        """Populate *list_widget* with versions for *script_type*."""
        list_widget.clear()

        # Add "Current" pseudo-entry
        current_item = QListWidgetItem("Current (unsaved)")
        current_item.setData(_ROLE_VERSION_ID, -1)
        current_item.setData(Qt.ItemDataRole.UserRole, current_content)
        list_widget.addItem(current_item)

        versions = ScriptVersionService.list_versions(
            request_id=self._request_id,
            collection_id=self._collection_id,
            script_type=script_type,
        )
        for v in versions:
            ts = v["created_at"]
            label = _format_timestamp(ts)
            preview = (v["content"] or "")[:60].replace("\n", " ")
            item = QListWidgetItem(f"{label}\n{preview}")
            item.setData(_ROLE_VERSION_ID, v["id"])
            item.setData(Qt.ItemDataRole.UserRole, v["content"])
            list_widget.addItem(item)

    # -- Selection handling --------------------------------------------

    def _on_version_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        """Show diff when a version is selected."""
        if current is None:
            return

        version_id = current.data(_ROLE_VERSION_ID)
        content = current.data(Qt.ItemDataRole.UserRole) or ""
        is_current_entry = version_id == -1

        # Determine which viewer to update
        tab_idx = self._type_tabs.currentIndex()
        if tab_idx == 0:
            current_text = self._current_pre
            viewer = self._pre_viewer
        else:
            current_text = self._current_test
            viewer = self._test_viewer

        if is_current_entry:
            viewer.show_single(current_text)
        else:
            viewer.show_diff(content, current_text)

        self._restore_btn.setEnabled(not is_current_entry)

    def _on_tab_changed(self, _index: int) -> None:
        """Reset restore button when switching tabs."""
        self._restore_btn.setEnabled(False)

    # -- Restore -------------------------------------------------------

    def _on_restore(self) -> None:
        """Accept the dialog with the selected version's content."""
        tab_idx = self._type_tabs.currentIndex()
        list_widget = self._pre_list if tab_idx == 0 else self._test_list
        item = list_widget.currentItem()
        if item is None:
            return

        content = item.data(Qt.ItemDataRole.UserRole) or ""
        script_type = "pre_request" if tab_idx == 0 else "test"
        self._restored = (script_type, content)
        self.accept()

    def restored_content(self) -> tuple[str, str] | None:
        """Return ``(script_type, content)`` if the user chose Restore."""
        return self._restored


# -- Diff viewer -------------------------------------------------------


class _DiffViewer(QWidget):
    """Side-by-side diff viewer with two read-only code editors."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the diff viewer layout."""
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # Labels
        label_row = QHBoxLayout()
        self._left_label = QLabel("Selected Version")
        self._left_label.setObjectName("mutedLabel")
        label_row.addWidget(self._left_label, 1)
        self._right_label = QLabel("Current")
        self._right_label.setObjectName("mutedLabel")
        label_row.addWidget(self._right_label, 1)
        root.addLayout(label_row)

        # Editors
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._left_editor = CodeEditorWidget()
        self._left_editor.setReadOnly(True)
        splitter.addWidget(self._left_editor)

        self._right_editor = CodeEditorWidget()
        self._right_editor.setReadOnly(True)
        splitter.addWidget(self._right_editor)

        # Synchronize scrolling
        left_bar = self._left_editor.verticalScrollBar()
        right_bar = self._right_editor.verticalScrollBar()
        left_bar.valueChanged.connect(right_bar.setValue)
        right_bar.valueChanged.connect(left_bar.setValue)

        root.addWidget(splitter, 1)

    def show_single(self, content: str) -> None:
        """Show a single version (no diff highlighting)."""
        self._left_editor.setPlainText(content)
        self._right_editor.setPlainText("")
        self._left_label.setText("Current")
        self._right_label.setText("")

    def show_diff(self, old_text: str, new_text: str) -> None:
        """Show two versions side-by-side with changed-line highlighting."""
        self._left_editor.setPlainText(old_text)
        self._right_editor.setPlainText(new_text)
        self._left_label.setText("Selected Version")
        self._right_label.setText("Current")

        # Highlight changed lines
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        import difflib

        sm = difflib.SequenceMatcher(None, old_lines, new_lines)
        removed_lines: set[int] = set()
        added_lines: set[int] = set()

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                removed_lines.update(range(i1, i2))
                added_lines.update(range(j1, j2))
            elif tag == "delete":
                removed_lines.update(range(i1, i2))
            elif tag == "insert":
                added_lines.update(range(j1, j2))

        _highlight_lines(self._left_editor, removed_lines, _removed_format())
        _highlight_lines(self._right_editor, added_lines, _added_format())


def _removed_format() -> QTextCharFormat:
    """Return a char format for removed (old) lines."""
    fmt = QTextCharFormat()
    fmt.setBackground(QColor(theme.COLOR_DANGER).lighter(170))
    return fmt


def _added_format() -> QTextCharFormat:
    """Return a char format for added (new) lines."""
    fmt = QTextCharFormat()
    fmt.setBackground(QColor(theme.COLOR_SUCCESS).lighter(170))
    return fmt


def _highlight_lines(
    editor: CodeEditorWidget,
    line_numbers: set[int],
    fmt: QTextCharFormat,
) -> None:
    """Apply *fmt* as extra selection to the given 0-based line numbers."""
    from PySide6.QtWidgets import QTextEdit

    selections: list[QTextEdit.ExtraSelection] = list(editor.extraSelections())
    doc = editor.document()
    for line_no in sorted(line_numbers):
        block = doc.findBlockByNumber(line_no)
        if not block.isValid():
            continue
        sel = QTextEdit.ExtraSelection()
        sel.format = fmt
        sel.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        sel.cursor = editor.textCursor()
        sel.cursor.setPosition(block.position())
        sel.cursor.movePosition(
            sel.cursor.MoveOperation.EndOfBlock,
            sel.cursor.MoveMode.KeepAnchor,
        )
        selections.append(sel)
    editor.setExtraSelections(selections)


def _format_timestamp(ts: datetime) -> str:
    """Format a timestamp as a human-readable relative/absolute string."""
    now = datetime.now()
    delta = now - ts
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    if seconds < 604800:
        days = seconds // 86400
        return f"{days}d ago"
    return ts.strftime("%Y-%m-%d %H:%M")
