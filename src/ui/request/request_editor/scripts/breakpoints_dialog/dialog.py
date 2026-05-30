"""JetBrains-style breakpoints dialog for the active script editor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.request.request_editor.scripts.breakpoints_dialog.preview import BreakpointCodePreview
from ui.request.request_editor.scripts.script_language import code_to_display, normalise_script_code
from ui.styling.icons import phi
from ui.styling.theme import COLOR_EDITOR_BREAKPOINT

if TYPE_CHECKING:
    from ui.widgets.code_editor.editor_widget import CodeEditorWidget

_DEFAULT_WIDTH = 920
_DEFAULT_HEIGHT = 620
_MIN_WIDTH = 720
_MIN_HEIGHT = 480


def _language_extension(language: str) -> str:
    lang = normalise_script_code(language)
    if lang == "python":
        return ".py"
    if lang == "typescript":
        return ".ts"
    return ".js"


def resolve_breakpoint_source(
    editor: CodeEditorWidget,
    host_pane: QWidget | None,
) -> tuple[str, str, str]:
    """Return ``(short_file, group_label, path_prefix)`` for list and header text."""
    lang = normalise_script_code(editor.language)
    short = f"script{_language_extension(lang)}"
    path_prefix = "Current script"
    group = f"{code_to_display(lang)} Line Breakpoints"

    if host_pane is None:
        return short, group, path_prefix

    opts = getattr(host_pane, "_options", None)
    if opts is not None:
        if getattr(opts, "host_kind", "") == "local_script":
            script_id = getattr(host_pane, "_local_script_id", None)
            if script_id is not None:
                try:
                    from services.local_script_service import LocalScriptService

                    row = LocalScriptService.get_script_load_dict(script_id)
                    if row is not None:
                        from ui.local_scripts.script_filename import script_display_name

                        short = script_display_name(
                            row["name"],
                            row["language"],
                            row.get("module_format", "esm"),
                        )
                        path_prefix = short
                except Exception:
                    pass
        else:
            st = getattr(opts, "script_type", "pre_request")
            label = "Pre-request" if st == "pre_request" else "Post-response"
            path_prefix = f"{label} script"
            short = f"{label.lower().replace('-', '_')}{_language_extension(lang)}"

    return short, group, path_prefix


class BreakpointsDialog(QDialog):
    """Two-pane breakpoints manager (list + properties + code preview)."""

    def __init__(
        self,
        editor: CodeEditorWidget,
        *,
        protocol: Any | None = None,
        host_pane: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Edit breakpoints for *editor*; changes apply on **Done**."""
        super().__init__(parent)
        self.setObjectName("breakpointsDialog")
        self._editor = editor
        self._protocol = protocol
        self._host_pane = host_pane
        self._short_name, self._group_label, self._path_prefix = resolve_breakpoint_source(
            editor, host_pane
        )
        self._lines: dict[int, str | None] = self._initial_lines()
        self._syncing_form = False

        self.setWindowTitle("Breakpoints")
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("breakpointsDialogSplitter")
        root.addWidget(splitter, 1)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        add_btn = QToolButton()
        add_btn.setIcon(phi("plus", size=14))
        add_btn.setToolTip("Add breakpoint")
        add_btn.setObjectName("iconButton")
        add_btn.setFixedSize(28, 28)
        add_btn.clicked.connect(self._add_breakpoint)
        toolbar.addWidget(add_btn)

        rm_btn = QToolButton()
        rm_btn.setIcon(phi("minus", size=14))
        rm_btn.setToolTip("Remove breakpoint")
        rm_btn.setObjectName("iconButton")
        rm_btn.setFixedSize(28, 28)
        rm_btn.clicked.connect(self._remove_selected)
        toolbar.addWidget(rm_btn)
        toolbar.addStretch()
        left_lay.addLayout(toolbar)

        self._tree = QTreeWidget()
        self._tree.setObjectName("breakpointsDialogTree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.currentItemChanged.connect(self._on_selection_changed)
        self._tree.itemChanged.connect(self._on_item_changed)
        left_lay.addWidget(self._tree, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(12, 0, 0, 0)
        right_lay.setSpacing(8)

        self._location_label = QLabel()
        self._location_label.setObjectName("mutedLabel")
        self._location_label.setWordWrap(True)
        right_lay.addWidget(self._location_label)

        self._enabled_cb = QCheckBox("Enabled")
        self._enabled_cb.toggled.connect(self._on_enabled_toggled)
        right_lay.addWidget(self._enabled_cb)

        cond_row = QHBoxLayout()
        cond_row.setSpacing(8)
        self._condition_cb = QCheckBox("Condition")
        self._condition_cb.toggled.connect(self._on_condition_enabled_toggled)
        cond_row.addWidget(self._condition_cb)
        self._condition_edit = QLineEdit()
        self._condition_edit.setPlaceholderText("Expression")
        self._condition_edit.setEnabled(False)
        self._condition_edit.editingFinished.connect(self._on_condition_edited)
        cond_row.addWidget(self._condition_edit, 1)
        right_lay.addLayout(cond_row)

        right_lay.addWidget(self._make_separator())

        self._preview = BreakpointCodePreview()
        right_lay.addWidget(self._preview, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 600])

        footer = QHBoxLayout()
        footer.addStretch()

        done_btn = QPushButton("Done")
        done_btn.setObjectName("primaryButton")
        done_btn.setDefault(True)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.clicked.connect(self._on_done)
        footer.addWidget(done_btn)
        root.addLayout(footer)

        self._rebuild_tree()
        if self._tree.topLevelItemCount() > 0:
            group = self._tree.topLevelItem(0)
            if group is not None and group.childCount() > 0:
                first = group.child(0)
                if first is not None:
                    self._tree.setCurrentItem(first)

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setObjectName("debugInspectorSeparator")
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedHeight(1)
        return sep

    def _initial_lines(self) -> dict[int, str | None]:
        if self._protocol is not None:
            return dict(self._protocol.breakpoints)
        return dict(self._editor.breakpoints)

    def _breakpoint_icon(self) -> Any:
        return phi("circle-fill", color=COLOR_EDITOR_BREAKPOINT, size=10)

    def _rebuild_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        group = QTreeWidgetItem([self._group_label])
        group.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = group.font(0)
        font.setBold(True)
        group.setFont(0, font)
        self._tree.addTopLevelItem(group)

        icon = self._breakpoint_icon()
        for line in sorted(self._lines):
            label = f"{self._short_name}:{line + 1}"
            item = QTreeWidgetItem([label])
            item.setIcon(0, icon)
            item.setData(0, Qt.ItemDataRole.UserRole, line)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(0, Qt.CheckState.Checked)
            group.addChild(item)

        group.setExpanded(True)
        self._tree.blockSignals(False)

        if group.childCount() == 0:
            self._clear_detail_panel()
        elif self._tree.currentItem() is None and group.childCount() > 0:
            child = group.child(0)
            if child is not None:
                self._tree.setCurrentItem(child)

    def _selected_line(self) -> int | None:
        item = self._tree.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        return int(data) if isinstance(data, int) else None

    def _on_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        line = None
        if current is not None:
            data = current.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, int):
                line = data
        if line is None:
            self._clear_detail_panel()
            return
        self._load_detail_panel(line)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or self._syncing_form:
            return
        line = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(line, int):
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            if line not in self._lines:
                self._lines[line] = None
        else:
            self._lines.pop(line, None)
        if self._selected_line() == line:
            self._load_detail_panel(line)

    def _clear_detail_panel(self) -> None:
        self._syncing_form = True
        self._location_label.setText("Select a breakpoint")
        self._enabled_cb.setChecked(False)
        self._enabled_cb.setEnabled(False)
        self._condition_cb.setChecked(False)
        self._condition_cb.setEnabled(False)
        self._condition_edit.clear()
        self._condition_edit.setEnabled(False)
        self._preview.show_excerpt(full_text="", language=self._editor.language, source_line=0)
        self._syncing_form = False

    def _load_detail_panel(self, line: int) -> None:
        self._syncing_form = True
        cond = self._lines.get(line)
        in_list = line in self._lines
        self._location_label.setText(f"{self._path_prefix}:{line + 1}")
        self._enabled_cb.setEnabled(True)
        self._enabled_cb.setChecked(in_list)
        self._condition_cb.setEnabled(in_list)
        has_cond = bool(cond)
        self._condition_cb.setChecked(has_cond)
        self._condition_edit.setEnabled(in_list and has_cond)
        self._condition_edit.setText(cond or "")
        self._preview.show_excerpt(
            full_text=self._editor.toPlainText(),
            language=self._editor.language,
            source_line=line,
        )
        self._syncing_form = False

    def _on_enabled_toggled(self, checked: bool) -> None:
        if self._syncing_form:
            return
        line = self._selected_line()
        if line is None:
            return
        item = self._tree.currentItem()
        if item is None:
            return
        self._tree.blockSignals(True)
        if checked:
            if line not in self._lines:
                self._lines[line] = None
            item.setCheckState(0, Qt.CheckState.Checked)
        else:
            self._lines.pop(line, None)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        self._tree.blockSignals(False)
        self._load_detail_panel(line)

    def _on_condition_enabled_toggled(self, checked: bool) -> None:
        if self._syncing_form:
            return
        line = self._selected_line()
        if line is None or line not in self._lines:
            return
        self._condition_edit.setEnabled(checked)
        if not checked:
            self._lines[line] = None
            self._condition_edit.clear()
        elif not self._condition_edit.text().strip():
            self._condition_edit.setFocus()
        self._on_condition_edited()

    def _on_condition_edited(self) -> None:
        if self._syncing_form:
            return
        line = self._selected_line()
        if line is None or line not in self._lines:
            return
        if not self._condition_cb.isChecked():
            self._lines[line] = None
            return
        text = self._condition_edit.text().strip()
        self._lines[line] = text or None

    def _add_breakpoint(self) -> None:
        doc = self._editor.document()
        max_line = max(1, doc.blockCount())
        default = self._editor.textCursor().blockNumber() + 1
        line_1, ok = QInputDialog.getInt(
            self,
            "Add breakpoint",
            "Line number:",
            default,
            1,
            max_line,
        )
        if not ok:
            return
        line = line_1 - 1
        if line not in self._lines:
            self._lines[line] = None
        self._rebuild_tree()
        self._select_line_in_tree(line)

    def _remove_selected(self) -> None:
        line = self._selected_line()
        if line is None:
            return
        self._lines.pop(line, None)
        self._rebuild_tree()

    def _select_line_in_tree(self, line: int) -> None:
        group = self._tree.topLevelItem(0)
        if group is None:
            return
        for i in range(group.childCount()):
            child = group.child(i)
            if child is None:
                continue
            if child.data(0, Qt.ItemDataRole.UserRole) == line:
                self._tree.setCurrentItem(child)
                return

    def _apply_to_editor(self) -> None:
        """Write dialog state back to the host editor and protocol."""
        mapping: dict[int, str | None] = {}
        for line, cond in self._lines.items():
            text = (cond or "").strip()
            mapping[line] = text or None
        self._editor.replace_breakpoints(mapping, emit=True)

        if self._protocol is not None:
            self._protocol.update_breakpoints(dict(self._editor.breakpoints))

    def _on_done(self) -> None:
        self._apply_to_editor()
        self._editor.set_breakpoint_gutter_visible(True)
        self.accept()

    def reject(self) -> None:
        """Closing without Done does not mutate editor breakpoints."""
        super().reject()
