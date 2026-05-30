"""Watch expressions as rows under a Watches section in the debug variables tree."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from services.scripting.debug.protocol import (
    WATCH_EVAL_ERROR_PREFIX,
    WATCH_VALUE_PLACEHOLDER,
    is_watch_eval_error,
    normalize_watch_eval_result,
)
from ui.styling.icons import phi
from ui.widgets.debug_value_tree import (
    _PM_FULL_TEXT_PROP,
    _connect_debug_tree_elide_refresh,
    _elided_cell_text,
    set_debug_tree_cell_label,
)

WATCH_SECTION_SOURCE = "watch"
_VALUE_COL_MAX_LEN = 96
_WATCH_VALUE_LABEL_NAME = "debugWatchRowValueLabel"


@dataclass
class WatchState:
    """Ordered watch expressions for one :class:`DebugVariablesPanel` instance."""

    expressions: list[str] = field(default_factory=list)


def _watch_error_tooltip(raw: str) -> str:
    """Collapse multi-line evaluate errors to one line for the value-column tooltip."""
    if raw.startswith(WATCH_EVAL_ERROR_PREFIX):
        body = raw[len(WATCH_EVAL_ERROR_PREFIX) :].strip()
    else:
        body = raw.strip()
    return " ".join(body.split())


def format_watch_display(raw: str) -> tuple[str, str]:
    """Return ``(value_column, tooltip)`` for an ``evaluate()`` display string."""
    normalized = normalize_watch_eval_result(raw)
    if is_watch_eval_error(normalized):
        return "?", _watch_error_tooltip(raw)
    if len(normalized) > _VALUE_COL_MAX_LEN:
        return normalized[: _VALUE_COL_MAX_LEN - 1] + "\u2026", normalized
    return normalized, normalized


def _watch_value_label(row: QTreeWidgetItem) -> QLabel | None:
    """Return the value ``QLabel`` inside a watch row's column-1 container."""
    tree = row.treeWidget()
    if tree is None:
        return None
    container = tree.itemWidget(row, 1)
    if container is None:
        return None
    lab = container.findChild(QLabel, _WATCH_VALUE_LABEL_NAME)
    return lab if isinstance(lab, QLabel) else None


def _set_watch_value_label(
    tree: QTreeWidget, row: QTreeWidgetItem, display: str, tooltip: str
) -> None:
    """Update the stretched value label (and elide to column width)."""
    lab = _watch_value_label(row)
    if lab is None:
        set_debug_tree_cell_label(tree, row, 1, display, tooltip=tooltip)
        return
    plain = display.replace("\n", " ")
    tip = tooltip or plain
    lab.setProperty(_PM_FULL_TEXT_PROP, plain)
    lab.setToolTip(tip)
    lab.setText(_elided_cell_text(tree, 1, plain))
    row.setText(1, "")
    row.setToolTip(1, tip)


def _set_watch_row_columns(row: QTreeWidgetItem, expr: str, display: str, tooltip: str) -> None:
    """Update a watch row without painting native text under ``QLabel`` widgets."""
    tree = row.treeWidget()
    if tree is None:
        row.setText(0, expr)
        row.setText(1, display)
        row.setToolTip(1, tooltip)
        return
    set_debug_tree_cell_label(tree, row, 0, expr)
    _set_watch_value_label(tree, row, display, tooltip)


class _WatchRowSelectFilter(QObject):
    """Select the owning tree row when the user clicks a watch cell label."""

    def __init__(
        self,
        tree: QTreeWidget,
        item: QTreeWidgetItem,
        parent: QObject,
    ) -> None:
        """Bind to *parent* (the ``QLabel``) so the filter is destroyed with the row."""
        super().__init__(parent)
        self._tree = tree
        self._item = item

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            self._tree.setCurrentItem(self._item)
        return super().eventFilter(watched, event)


def _make_watch_cell_label(tree: QTreeWidget, text: str, *, object_name: str) -> QLabel:
    """Build a selectable name/value label matching scope variable rows."""
    lab = QLabel(text)
    lab.setObjectName(object_name)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lab.setWordWrap(False)
    lab.setMargin(0)
    lab.setIndent(0)
    lab.setFrameShape(QFrame.Shape.NoFrame)
    lab.setAutoFillBackground(False)
    lab.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    lab.setFont(tree.font())
    return lab


def attach_watch_row_widgets(
    tree: QTreeWidget,
    row: QTreeWidgetItem,
    *,
    on_remove: Callable[[], None] | None = None,
) -> None:
    """Name in column 0; value + optional trash aligned to the right of column 1."""
    _connect_debug_tree_elide_refresh(tree)
    expr = row.text(0)
    value = row.text(1)
    tip = row.toolTip(1)

    expr_lab = _make_watch_cell_label(tree, expr, object_name="debugTreeCellLabel")
    tree.setItemWidget(row, 0, expr_lab)
    row.setText(0, "")
    set_debug_tree_cell_label(tree, row, 0, expr)

    value_host = QWidget()
    value_host.setObjectName("debugWatchRowValueHost")
    value_host.setAutoFillBackground(False)
    value_lay = QHBoxLayout(value_host)
    value_lay.setContentsMargins(0, 0, 2, 0)
    value_lay.setSpacing(4)

    val_lab = _make_watch_cell_label(tree, value, object_name=_WATCH_VALUE_LABEL_NAME)
    val_lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    value_lay.addWidget(val_lab, 1)

    if on_remove is not None:
        btn = QPushButton()
        btn.setObjectName("debugWatchRowRemoveButton")
        btn.setIcon(phi("trash", size=14))
        btn.setToolTip("Remove watch")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.clicked.connect(on_remove)
        value_lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    tree.setItemWidget(row, 1, value_host)
    row.setText(1, "")
    _set_watch_value_label(tree, row, value, tip)

    _install_watch_row_filters(tree, row)


def _install_watch_row_filters(tree: QTreeWidget, row: QTreeWidgetItem) -> None:
    """Ensure clicks on watch cells select *row* for the toolbar remove button."""
    for col in (0, 1):
        w = tree.itemWidget(row, col)
        if w is None:
            continue
        labels = [w] if isinstance(w, QLabel) else w.findChildren(QLabel)
        for lab in labels:
            lab.installEventFilter(_WatchRowSelectFilter(tree, row, lab))


def rebuild_watch_rows(
    watches_root: QTreeWidgetItem,
    state: WatchState,
    tree: QTreeWidget,
    *,
    on_remove_at_index: Callable[[int], None] | None = None,
) -> None:
    """Replace all watch child rows under *watches_root* (structure only, values ``—``)."""
    while watches_root.childCount() > 0:
        child = watches_root.child(0)
        if child is not None:
            watches_root.removeChild(child)
    for idx, expr in enumerate(state.expressions):
        row = QTreeWidgetItem([expr, WATCH_VALUE_PLACEHOLDER])
        row.setToolTip(1, "")
        watches_root.addChild(row)
        remove_cb = (
            (lambda i=idx: on_remove_at_index(i)) if on_remove_at_index is not None else None
        )
        attach_watch_row_widgets(tree, row, on_remove=remove_cb)
