"""JetBrains-style debug inspector: call stack | watch strip + unified variables tree."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import Shiboken

from services.scripting.debug import DebugPauseInfo, DebugProtocol
from ui.sidebar.debug_call_stack_panel import CallStackPanel
from ui.sidebar.debug_scopes_panel import DebugScopesPanel
from ui.styling.icons import phi
from ui.styling.theme import (
    DEBUG_INSPECTOR_RIGHT_PANE_H_LEFT_PX,
    DEBUG_INSPECTOR_RIGHT_PANE_H_RIGHT_PX,
    DEBUG_INSPECTOR_RIGHT_PANE_SECTION_TOP_PX,
    DEBUG_INSPECTOR_WATCH_EXPRESSION_BOTTOM_PX,
)

_SPLITTER_HANDLE_WIDTH = 5
_SPLITTER_INITIAL_LEFT = 200
_SPLITTER_INITIAL_RIGHT = 560


def _make_debug_inspector_separator() -> QFrame:
    """Theme-colored 1px rule between watch strip and variables tree."""
    sep = QFrame()
    sep.setObjectName("debugInspectorSeparator")
    sep.setFrameShape(QFrame.Shape.NoFrame)
    sep.setFixedHeight(1)
    return sep


def _qt_valid(obj: object | None) -> bool:
    """Return whether *obj* is a live Qt C++ wrapper (not deleted)."""
    return obj is not None and Shiboken.isValid(obj)


class DebugWatchesPane(QWidget):
    """Watch expression strip (rows live in :class:`DebugScopesPanel` tree)."""

    def __init__(self, tree_host: DebugScopesPanel, parent: QWidget | None = None) -> None:
        """Build title row, expression field, and add/remove controls."""
        super().__init__(parent)
        self._host = tree_host
        lay = QVBoxLayout(self)
        lay.setContentsMargins(
            DEBUG_INSPECTOR_RIGHT_PANE_H_LEFT_PX,
            DEBUG_INSPECTOR_RIGHT_PANE_SECTION_TOP_PX,
            DEBUG_INSPECTOR_RIGHT_PANE_H_RIGHT_PX,
            DEBUG_INSPECTOR_WATCH_EXPRESSION_BOTTOM_PX,
        )
        lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title = QLabel("Watches")
        title.setObjectName("sidebarSectionLabel")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._show_internals = QCheckBox("Show internals")
        self._show_internals.setObjectName("debugShowInternalsCheck")
        self._show_internals.setChecked(False)
        self._show_internals.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_internals.toggled.connect(self._host.set_show_internal_debug_vars)
        title_row.addWidget(self._show_internals)
        lay.addLayout(title_row)

        strip_row = QHBoxLayout()
        strip_row.setSpacing(6)
        self._watch_add_edit = QLineEdit()
        self._watch_add_edit.setPlaceholderText("Expression\u2026")
        self._watch_add_edit.setObjectName("debugWatchAddEdit")
        self._watch_add_edit.returnPressed.connect(self._add_watch_expression)
        strip_row.addWidget(self._watch_add_edit, 1)

        add_btn = QPushButton()
        add_btn.setIcon(phi("plus", size=14))
        add_btn.setToolTip("Add watch expression")
        add_btn.setObjectName("iconButton")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_watch_expression)
        strip_row.addWidget(add_btn)

        rm_btn = QPushButton()
        rm_btn.setIcon(phi("trash", size=14))
        rm_btn.setToolTip("Remove selected watch")
        rm_btn.setObjectName("iconButton")
        rm_btn.setFixedSize(28, 28)
        rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rm_btn.clicked.connect(self._remove_selected_watch)
        strip_row.addWidget(rm_btn)
        lay.addLayout(strip_row)

    @property
    def watch_state(self):
        """Ordered watch expressions (stored on the variables tree host)."""
        return self._host.watch_state

    @property
    def _watches_root(self):
        """Back-compat for tests targeting the strip pane."""
        return self._host.watches_root

    @property
    def _tree(self) -> QTreeWidget:
        """Unified variables tree (watches + scopes)."""
        return self._host._tree

    @property
    def _protocol(self) -> DebugProtocol | None:
        return self._host._protocol

    def _add_watch_expression(self) -> None:
        if not _qt_valid(self._watch_add_edit):
            return
        text = self._watch_add_edit.text().strip()
        if not text:
            return
        self._host.add_watch_expression(text)
        self._watch_add_edit.clear()

    def _remove_selected_watch(self) -> None:
        self._host.remove_selected_watch()

    def refresh_watches(self) -> None:
        """Queue watch expression re-evaluation when paused."""
        self._host.refresh_watches()


class DebugInspectorSplit(QWidget):
    """Horizontal split: call stack (left) | watch strip + variables tree (right)."""

    frame_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Compose call stack, watch strip, and unified variables tree."""
        super().__init__(parent)
        self.setObjectName("debugInspectorSplit")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("debugInspectorSplitter")
        self._splitter.setHandleWidth(_SPLITTER_HANDLE_WIDTH)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.splitterMoved.connect(self._sync_v_separator)
        outer.addWidget(self._splitter, 1)

        self._v_separator = QFrame(self)
        self._v_separator.setObjectName("debugInspectorVSeparator")
        self._v_separator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._v_separator.setFixedWidth(1)
        self._v_separator.hide()

        self._call_stack = CallStackPanel()
        self._call_stack.frame_selected.connect(self._on_frame_selected)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)
        self._right_lay = right_lay
        self._controls_host: QWidget | None = None

        self._scopes = DebugScopesPanel()
        self._watches = DebugWatchesPane(self._scopes)
        right_lay.addWidget(self._watches)
        right_lay.addWidget(_make_debug_inspector_separator())
        right_lay.addWidget(self._scopes, 1)

        self._splitter.addWidget(self._call_stack)
        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([_SPLITTER_INITIAL_LEFT, _SPLITTER_INITIAL_RIGHT])

        self._protocol: DebugProtocol | None = None

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep the vertical pane divider flush with the inspector top and bottom."""
        super().resizeEvent(event)
        self._sync_v_separator()

    def showEvent(self, event: QShowEvent) -> None:
        """Reposition the divider when the inspector becomes visible."""
        super().showEvent(event)
        self._sync_v_separator()

    def _sync_v_separator(self) -> None:
        """Paint a full-height 1px rule on the splitter seam (handle chrome is transparent)."""
        if not _qt_valid(self._v_separator) or not _qt_valid(self._splitter):
            return
        if self.height() < 2 or self._splitter.count() < 2:
            self._v_separator.hide()
            return
        handle = self._splitter.handle(1)
        if handle is None or not Shiboken.isValid(handle):
            self._v_separator.hide()
            return
        center_x = handle.mapTo(self, handle.rect().center()).x()
        self._v_separator.setGeometry(center_x, 0, 1, self.height())
        self._v_separator.show()
        self._v_separator.raise_()

    @property
    def call_stack(self) -> CallStackPanel:
        """Stack frame list (left column)."""
        return self._call_stack

    @property
    def watches(self) -> DebugWatchesPane:
        """Watch expression strip (above the variables tree)."""
        return self._watches

    @property
    def scopes(self) -> DebugScopesPanel:
        """Unified variables tree (watches + locals / pm / globals)."""
        return self._scopes

    @property
    def watch_state(self):
        """Shared watch expression list."""
        return self._scopes.watch_state

    @property
    def watches_tree(self) -> QTreeWidget:
        """Back-compat: same tree as :attr:`scopes_tree`."""
        return self._scopes._tree

    @property
    def scopes_tree(self) -> QTreeWidget:
        """Unified variables tree widget."""
        return self._scopes._tree

    def set_protocol(self, protocol: DebugProtocol | None) -> None:
        """Attach protocol for frame selection and watch evaluation."""
        self._protocol = protocol
        self._scopes.set_protocol(protocol)

    def set_controls_widget(self, controls: QWidget | None) -> None:
        """Place step controls in the right pane above Watches."""
        if self._controls_host is not None and _qt_valid(self._controls_host):
            self._right_lay.removeWidget(self._controls_host)
            self._controls_host.deleteLater()
            self._controls_host = None
        if controls is None or not _qt_valid(controls):
            return
        host = QWidget()
        host_lay = QVBoxLayout(host)
        host_lay.setContentsMargins(
            DEBUG_INSPECTOR_RIGHT_PANE_H_LEFT_PX,
            DEBUG_INSPECTOR_RIGHT_PANE_SECTION_TOP_PX,
            DEBUG_INSPECTOR_RIGHT_PANE_H_RIGHT_PX,
            6,
        )
        host_lay.setSpacing(6)
        host_lay.addWidget(controls)
        host_lay.addWidget(_make_debug_inspector_separator())
        self._right_lay.insertWidget(0, host)
        self._controls_host = host

    def update_pause(self, info: DebugPauseInfo) -> None:
        """Refresh call stack and the unified variables tree from a pause event."""
        self._call_stack.update_pause(info)
        self._scopes.update_pause(
            info.get("local_vars", {}),
            info.get("env_changes", {}) or {},
            info.get("global_changes", {}) or {},
        )

    def clear_session(self) -> None:
        """End session: blank watch values; scopes message when empty."""
        self._call_stack.clear_session()
        self._scopes.clear_session()

    def set_idle(self) -> None:
        """Idle state for all inspector sections."""
        from services.lsp.pm_require_types import prune_orphan_specs
        from services.lsp.servers._workspace import ensure_js_workspace
        from ui.widgets.code_editor.lsp_integration import EditorLspAdapter

        self._call_stack.set_idle()
        self._scopes.set_idle()
        self.set_protocol(None)
        prune_orphan_specs(ensure_js_workspace(), EditorLspAdapter.live_js_buffer_keys())

    def _on_frame_selected(self, index: int) -> None:
        protocol = self._protocol
        if protocol is None:
            return
        info = protocol.select_frame(index)
        if info is not None:
            self.update_pause(info)
        self.frame_selected.emit(index)
