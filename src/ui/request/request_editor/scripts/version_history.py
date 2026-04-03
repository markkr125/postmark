"""Version history dialog with timeline and diff viewer.

Opens from the Scripts tab History button.  Shows a timeline of script
snapshots and a side-by-side diff viewer for comparing versions with
syntax highlighting, character-level inline diffs, and gutter markers.
"""

from __future__ import annotations

import difflib
from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.script_version_service import ScriptVersionService
from ui.styling.icons import phi
from ui.styling.theme import (
    COLOR_BORDER,
    COLOR_DIFF_ADDED_BG,
    COLOR_DIFF_ADDED_GUTTER,
    COLOR_DIFF_ADDED_INLINE,
    COLOR_DIFF_REMOVED_BG,
    COLOR_DIFF_REMOVED_GUTTER,
    COLOR_DIFF_REMOVED_INLINE,
)
from ui.widgets.code_editor import CodeEditorWidget

# Custom data role for version ID.
_ROLE_VERSION_ID = Qt.ItemDataRole.UserRole + 1

# Fraction of the primary screen dimensions used for the dialog.
_SCREEN_FRACTION = 0.8

# Height (in pixels) for version list items.
_LIST_ITEM_HEIGHT = 44


class VersionHistoryDialog(QDialog):
    """Dialog showing script version timeline and side-by-side diff."""

    def __init__(
        self,
        *,
        request_id: int | None,
        collection_id: int | None,
        current_pre: str,
        current_test: str,
        language: str = "javascript",
        parent: QWidget | None = None,
    ) -> None:
        """Build the version history dialog."""
        super().__init__(parent)
        self.setWindowTitle("Script Version History")

        # Size to 80 % of the primary screen.
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            w = int(geo.width() * _SCREEN_FRACTION)
            h = int(geo.height() * _SCREEN_FRACTION)
        else:
            w, h = 1200, 800
        self.resize(w, h)

        self._request_id = request_id
        self._collection_id = collection_id
        self._current_pre = current_pre
        self._current_test = current_test
        self._language = language
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
        version_list.setObjectName("versionList")
        version_list.setMaximumWidth(220)
        version_list.currentItemChanged.connect(self._on_version_selected)
        splitter.addWidget(version_list)

        # Diff viewer
        viewer = _DiffViewer(language=self._language)
        splitter.addWidget(viewer)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(1)
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
        current_item.setSizeHint(QSize(0, _LIST_ITEM_HEIGHT))
        list_widget.addItem(current_item)

        versions = ScriptVersionService.list_versions(
            request_id=self._request_id,
            collection_id=self._collection_id,
            script_type=script_type,
        )
        for v in versions:
            ts = v["created_at"]
            label = _format_timestamp(ts)
            date_str = ts.strftime("%Y-%m-%d %H:%M")
            preview = (v["content"] or "")[:60].replace("\n", " ")
            item = QListWidgetItem(f"{label}  \u00b7  {date_str}\n{preview}")
            item.setData(_ROLE_VERSION_ID, v["id"])
            item.setData(Qt.ItemDataRole.UserRole, v["content"])
            item.setSizeHint(QSize(0, _LIST_ITEM_HEIGHT))
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

# Width (in pixels) of the coloured gutter stripe for changed lines.
_GUTTER_STRIPE_PX = 3


class _DiffViewer(QWidget):
    """Side-by-side diff viewer with syntax highlighting and inline diffs."""

    def __init__(
        self,
        *,
        language: str = "javascript",
        parent: QWidget | None = None,
    ) -> None:
        """Build the diff viewer layout."""
        super().__init__(parent)
        self._language = language

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # Labels (left-padded so text is not flush against the gutter edge)
        _label_margin = 4
        label_row = QHBoxLayout()
        self._left_label = QLabel("Selected Version")
        self._left_label.setObjectName("mutedLabel")
        self._left_label.setContentsMargins(_label_margin, 0, 0, 0)
        self._left_label.setStyleSheet(
            f"border-right: 1px solid {COLOR_BORDER}; border-top: 1px solid {COLOR_BORDER};"
        )
        label_row.addWidget(self._left_label, 1)
        self._right_label = QLabel("Current")
        self._right_label.setObjectName("mutedLabel")
        self._right_label.setContentsMargins(_label_margin, 0, 0, 0)
        self._right_label.setStyleSheet(
            f"border-right: 1px solid {COLOR_BORDER}; border-top: 1px solid {COLOR_BORDER};"
        )
        label_row.addWidget(self._right_label, 1)
        root.addLayout(label_row)

        # Editors — remove outer border; keep bottom border only
        border = COLOR_BORDER
        editor_css = (
            f"QPlainTextEdit {{ border: none;"
            f" border-bottom: 1px solid {border};"
            f" border-right: 1px solid {border};"
            f" border-top: 1px solid {border}; }}"
        )
        right_editor_css = (
            f"QPlainTextEdit {{ border: none;"
            f" border-bottom: 1px solid {border};"
            f" border-right: 1px solid {border};"
            f" border-top: 1px solid {border}; }}"
        )
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._left_editor = CodeEditorWidget()
        self._left_editor.setReadOnly(True)
        self._left_editor.set_language(language)
        self._left_editor.setStyleSheet(editor_css)
        splitter.addWidget(self._left_editor)

        self._right_editor = CodeEditorWidget()
        self._right_editor.setReadOnly(True)
        self._right_editor.set_language(language)
        self._right_editor.setStyleSheet(right_editor_css)
        splitter.addWidget(self._right_editor)

        # Synchronize scrolling
        left_bar = self._left_editor.verticalScrollBar()
        right_bar = self._right_editor.verticalScrollBar()
        left_bar.valueChanged.connect(right_bar.setValue)
        right_bar.valueChanged.connect(left_bar.setValue)

        root.addWidget(splitter, 1)

    def show_single(self, content: str) -> None:
        """Show a single version (no diff highlighting)."""
        self._left_editor.set_diff_selections([])
        self._left_editor.set_diff_line_colors({})
        self._right_editor.set_diff_selections([])
        self._right_editor.set_diff_line_colors({})
        self._left_editor.setPlainText(content)
        self._right_editor.setPlainText("")
        self._left_label.setText("Current")
        self._right_label.setText("")

    def show_diff(self, old_text: str, new_text: str) -> None:
        """Show two versions side-by-side with full diff highlighting."""
        self._left_editor.setPlainText(old_text)
        self._right_editor.setPlainText(new_text)
        self._left_label.setText("Selected Version")
        self._right_label.setText("Current")

        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        sm = difflib.SequenceMatcher(None, old_lines, new_lines)
        removed_lines: set[int] = set()
        added_lines: set[int] = set()
        replace_pairs: list[tuple[range, range]] = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                removed_lines.update(range(i1, i2))
                added_lines.update(range(j1, j2))
                replace_pairs.append((range(i1, i2), range(j1, j2)))
            elif tag == "delete":
                removed_lines.update(range(i1, i2))
            elif tag == "insert":
                added_lines.update(range(j1, j2))

        # 1. Full-line background highlights
        removed_fmt = _line_format(COLOR_DIFF_REMOVED_BG)
        added_fmt = _line_format(COLOR_DIFF_ADDED_BG)
        left_sels = _build_line_selections(self._left_editor, removed_lines, removed_fmt)
        right_sels = _build_line_selections(self._right_editor, added_lines, added_fmt)

        # 2. Character-level inline diffs for replaced lines
        _add_inline_selections(
            self._left_editor,
            self._right_editor,
            old_lines,
            new_lines,
            replace_pairs,
            left_sels,
            right_sels,
        )

        self._left_editor.set_diff_selections(left_sels)
        self._right_editor.set_diff_selections(right_sels)

        # 3. Gutter stripes
        removed_color = QColor(COLOR_DIFF_REMOVED_GUTTER)
        added_color = QColor(COLOR_DIFF_ADDED_GUTTER)
        self._left_editor.set_diff_line_colors(
            {ln: removed_color for ln in removed_lines},
        )
        self._right_editor.set_diff_line_colors(
            {ln: added_color for ln in added_lines},
        )


# -- Diff formatting helpers -------------------------------------------


def _line_format(color_hex: str) -> QTextCharFormat:
    """Return a full-width-selection char format with the given background."""
    fmt = QTextCharFormat()
    fmt.setBackground(QColor(color_hex))
    fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
    return fmt


def _build_line_selections(
    editor: CodeEditorWidget,
    line_numbers: set[int],
    fmt: QTextCharFormat,
) -> list[QTextEdit.ExtraSelection]:
    """Create extra selections for full-line background highlighting."""
    selections: list[QTextEdit.ExtraSelection] = []
    doc = editor.document()
    for line_no in sorted(line_numbers):
        block = doc.findBlockByNumber(line_no)
        if not block.isValid():
            continue
        sel = QTextEdit.ExtraSelection()
        sel.format = QTextCharFormat(fmt)
        cur = QTextCursor(doc)
        cur.setPosition(block.position())
        cur.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        sel.cursor = cur
        selections.append(sel)
    return selections


def _add_inline_selections(
    left_editor: CodeEditorWidget,
    right_editor: CodeEditorWidget,
    old_lines: list[str],
    new_lines: list[str],
    replace_pairs: list[tuple[range, range]],
    left_sels: list[QTextEdit.ExtraSelection],
    right_sels: list[QTextEdit.ExtraSelection],
) -> None:
    """Add character-level inline diff selections for replaced line pairs."""
    removed_inline_fmt = QTextCharFormat()
    removed_inline_fmt.setBackground(QColor(COLOR_DIFF_REMOVED_INLINE))
    added_inline_fmt = QTextCharFormat()
    added_inline_fmt.setBackground(QColor(COLOR_DIFF_ADDED_INLINE))

    left_doc = left_editor.document()
    right_doc = right_editor.document()

    for old_range, new_range in replace_pairs:
        # Pair up lines 1:1 where both ranges overlap
        pairs = min(len(old_range), len(new_range))
        for i in range(pairs):
            old_ln = old_range[i]
            new_ln = new_range[i]
            old_line = old_lines[old_ln]
            new_line = new_lines[new_ln]

            char_sm = difflib.SequenceMatcher(None, old_line, new_line)
            for tag, ci1, ci2, cj1, cj2 in char_sm.get_opcodes():
                if tag == "equal":
                    continue
                # Highlight changed chars in the old (left) editor
                if tag in ("replace", "delete") and ci2 > ci1:
                    left_block = left_doc.findBlockByNumber(old_ln)
                    if left_block.isValid():
                        sel = QTextEdit.ExtraSelection()
                        sel.format = QTextCharFormat(removed_inline_fmt)
                        cur = QTextCursor(left_doc)
                        cur.setPosition(left_block.position() + ci1)
                        cur.setPosition(
                            left_block.position() + ci2,
                            QTextCursor.MoveMode.KeepAnchor,
                        )
                        sel.cursor = cur
                        left_sels.append(sel)
                # Highlight changed chars in the new (right) editor
                if tag in ("replace", "insert") and cj2 > cj1:
                    right_block = right_doc.findBlockByNumber(new_ln)
                    if right_block.isValid():
                        sel = QTextEdit.ExtraSelection()
                        sel.format = QTextCharFormat(added_inline_fmt)
                        cur = QTextCursor(right_doc)
                        cur.setPosition(right_block.position() + cj1)
                        cur.setPosition(
                            right_block.position() + cj2,
                            QTextCursor.MoveMode.KeepAnchor,
                        )
                        sel.cursor = cur
                        right_sels.append(sel)


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
