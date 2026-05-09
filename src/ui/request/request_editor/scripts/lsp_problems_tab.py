"""Problems tab: language-server diagnostics list for script editors."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from services.lsp.client import Diagnostic
from services.lsp.qt_lsp_offsets import lsp_to_qpos
from services.scripting.runtime_settings import RuntimeSettings
from ui.styling.icons import phi
from ui.styling.theme import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_WARNING,
)

if TYPE_CHECKING:
    from ui.widgets.code_editor.editor_widget import CodeEditorWidget


def format_problem_line(d: Diagnostic) -> str:
    """Single-line summary shown in the list and copied via **Copy**."""
    line_1 = d.line + 1
    col_1 = d.column + 1
    sev = d.severity.upper() if d.severity else "DIAGNOSTIC"
    return f"{sev}  Ln {line_1}, Col {col_1}  {d.message}  ({d.source})"


def severity_foreground_color(severity: str) -> QColor:
    """IDE-style colour for *severity* (error / warning / info / hint)."""
    key = (severity or "").strip().lower()
    if key == "error":
        return QColor(COLOR_DANGER)
    if key == "warning":
        return QColor(COLOR_WARNING)
    if key == "info":
        return QColor(COLOR_ACCENT)
    if key == "hint":
        return QColor(COLOR_TEXT_MUTED)
    return QColor(COLOR_TEXT)


_PROBLEM_ICON_PX = 14


def severity_phi_icon(severity: str) -> QIcon:
    """Return a Phosphor glyph tinted for *severity* (error / warning / info / hint)."""
    key = (severity or "").strip().lower()
    sz = _PROBLEM_ICON_PX
    if key == "error":
        return phi("x-circle", color=COLOR_DANGER, size=sz)
    if key == "warning":
        return phi("warning-circle", color=COLOR_WARNING, size=sz)
    if key == "info":
        return phi("info", color=COLOR_ACCENT, size=sz)
    if key == "hint":
        return phi("lightbulb", color=COLOR_TEXT_MUTED, size=sz)
    return phi("info", color=COLOR_TEXT, size=sz)


class _ScriptProblemsItemDelegate(QStyledItemDelegate):
    """Paint Problems rows without the global Highlight / HighlightedText selection path.

    ``ThemeManager`` sets ``QPalette.HighlightedText`` to ``ThemePalette["bg"]`` (often
    near-white in the light scheme).  Qt Fusion paints selected ``QListWidget`` rows with
    that role, which replaces each item's ``ForegroundRole`` severity tint and yields
    unreadable contrast.  This delegate clears the selected state for the base paint,
    draws a subtle translucent fill plus a square **1px** accent border for selection,
    and forces palette text roles to the row's severity colour.
    """

    def __init__(self, list_widget: QListWidget) -> None:
        """Attach to *list_widget* as its item delegate."""
        super().__init__(list_widget)
        self._list = list_widget

    def _base_is_light(self) -> bool:
        return self._list.palette().color(QPalette.ColorRole.Base).lightnessF() > 0.5

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Draw hover/selection chrome, then delegate text using severity colour."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)

        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        text_color = opt.palette.color(QPalette.ColorRole.Text)
        if isinstance(fg, QBrush):
            text_color = fg.color()

        inner = opt.rect.adjusted(4, 1, -4, -1)
        light = self._base_is_light()

        painter.save()
        if selected:
            tint = QColor(0, 0, 0, 12) if light else QColor(255, 255, 255, 16)
            painter.fillRect(inner, tint)
            pen = QPen(QColor(COLOR_ACCENT))
            pen.setWidth(1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(inner.adjusted(0, 0, -1, -1))
        elif hovered:
            tint = QColor(0, 0, 0, 8) if light else QColor(255, 255, 255, 12)
            painter.fillRect(inner, tint)
        painter.restore()

        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        opt.backgroundBrush = QBrush(Qt.GlobalColor.transparent)
        opt.palette.setColor(QPalette.ColorRole.Text, text_color)
        opt.palette.setColor(QPalette.ColorRole.WindowText, text_color)
        opt.palette.setColor(QPalette.ColorRole.HighlightedText, text_color)

        super().paint(painter, opt, index)


class ScriptLspProblemsTab(QWidget):
    """Lists ``publishDiagnostics`` for the bound script :class:`CodeEditorWidget`."""

    problem_count_changed = Signal(int)  # emitted after each rebuild (including empty)

    _ROLE_DIAG = Qt.ItemDataRole.UserRole

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build stacked empty-state vs list UI."""
        super().__init__(parent)
        self._editor: CodeEditorWidget | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(4)

        self._stack = QStackedWidget()
        empty_host = QFrame()
        empty_host.setObjectName("scriptLspProblemsEmptyFrame")
        empty_host.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        empty_col = QVBoxLayout(empty_host)
        empty_col.setContentsMargins(4, 8, 4, 8)
        self._empty_label = QLabel()
        self._empty_label.setObjectName("mutedLabel")
        self._empty_label.setWordWrap(True)
        self._empty_label.setTextFormat(Qt.TextFormat.PlainText)
        empty_col.addWidget(self._empty_label)

        self._list = QListWidget()
        self._list.setObjectName("scriptLspProblemsList")
        self._list.itemClicked.connect(self._navigate_to_item)
        self._list.itemActivated.connect(self._navigate_to_item)
        self._list.itemDoubleClicked.connect(self._navigate_to_item)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        self._list.setIconSize(QSize(_PROBLEM_ICON_PX, _PROBLEM_ICON_PX))
        self._list.setItemDelegate(_ScriptProblemsItemDelegate(self._list))

        self._stack.addWidget(empty_host)
        self._stack.addWidget(self._list)
        root.addWidget(self._stack, 1)

        self._apply_diagnostics([])

    def set_editor(self, editor: CodeEditorWidget | None) -> None:
        """Bind to *editor* or clear connections when ``None``."""
        if self._editor is not None:
            with contextlib.suppress(Exception):
                self._editor.lsp_diagnostics_changed.disconnect(self._on_lsp_diagnostics_changed)
        self._editor = editor
        if editor is not None:
            editor.lsp_diagnostics_changed.connect(self._on_lsp_diagnostics_changed)
        self._apply_diagnostics([])

    def _on_lsp_diagnostics_changed(self, diags_obj: object) -> None:
        if not isinstance(diags_obj, list):
            self._apply_diagnostics([])
            return
        raw = cast(list[Any], diags_obj)
        cleaned = [d for d in raw if isinstance(d, Diagnostic)]
        self._apply_diagnostics(cleaned)

    def _apply_diagnostics(self, diags: list[Diagnostic]) -> None:
        """Rebuild the list or show the empty state."""
        self._list.clear()
        sorted_diags = sorted(diags, key=lambda d: (d.line, d.column, d.message, d.source))
        if not sorted_diags:
            self._stack.setCurrentIndex(0)
            self._set_empty_message()
            self.problem_count_changed.emit(0)
            return

        self._stack.setCurrentIndex(1)
        for d in sorted_diags:
            label = format_problem_line(d)
            item = QListWidgetItem(severity_phi_icon(d.severity), label)
            item.setData(self._ROLE_DIAG, d)
            item.setForeground(severity_foreground_color(d.severity))
            self._list.addItem(item)
        self.problem_count_changed.emit(len(sorted_diags))

    def diagnostic_count(self) -> int:
        """Return the number of rows in the problems list (0 when showing empty state)."""
        return self._list.count()

    def _set_empty_message(self) -> None:
        editor = self._editor
        adapter = getattr(editor, "_lsp_adapter", None) if editor is not None else None
        if not RuntimeSettings.lsp_enabled():
            text = (
                "No language-server diagnostics.\n"
                "Turn on Scripting LSP under Settings → Scripting to use Deno/jedi analysis."
            )
        elif adapter is None:
            text = (
                "No language-server diagnostics.\n"
                "Switch the script language to JavaScript, TypeScript, or Python to attach the server."
            )
        elif not bool(getattr(adapter, "is_ready", False)):
            text = (
                "No language-server diagnostics yet.\n"
                "The server is still starting or unavailable — try again shortly."
            )
        else:
            text = "No problems reported by the language server for this script."
        self._empty_label.setText(text)

    def _navigate_to_item(self, item: QListWidgetItem) -> None:
        """Move the bound editor cursor to the diagnostic range start."""
        editor = self._editor
        if editor is None:
            return
        raw = item.data(self._ROLE_DIAG)
        if not isinstance(raw, Diagnostic):
            return
        d = raw
        pos = lsp_to_qpos(editor.document(), d.line, d.column)
        cur = editor.textCursor()
        cur.setPosition(pos)
        editor.setTextCursor(cur)
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        editor.centerCursor()

    def _on_list_context_menu(self, pos: QPoint) -> None:
        """Offer **Copy** for the exact problem line under *pos*."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(lambda _checked=False, i=item: self._copy_problem_line(i))
        menu.addAction(copy_action)
        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _copy_problem_line(self, item: QListWidgetItem) -> None:
        """Place the list row text on the system clipboard."""
        QGuiApplication.clipboard().setText(item.text())
