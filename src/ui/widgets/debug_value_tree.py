"""Shared QTreeWidget helpers for JetBrains-style debug value previews.

Used by the script debug hover popup and the sidebar variables panel.  CDP
materialisation may attach :data:`CLASSNAME_KEY` so nested object previews show
a concrete class name instead of a generic ``Object``.

Value rows embed :func:`attach_selectable_cell_widgets` so name and value
columns support mouse text selection; native item text in those columns is
cleared after handoff so the delegate does not paint under the label (avoids
double-struck blur). Section headers keep native painting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
)

from ui.styling import theme

# 1. Tree size limits keep huge snapshots responsive.
MAX_TREE_DEPTH: int = 8
MAX_CHILDREN_PER_NODE: int = 100
MAX_TREE_NODES: int = 400
# 2. Inline dict/list previews show at most this many entries before ``…``.
PREVIEW_INLINE_KEYS: int = 4
# 3. Sentinel injected by CDP scope materialisation (see ``deno_scope`` duplicate literal).
CLASSNAME_KEY: str = "__pm_className__"

# Colours align with ``QLabel[objectName="sidebarSourceDot"][varSource=…]`` in
# ``ui.styling.global_qss.py`` (environment / collection / local).  Update both when tuning.


@lru_cache(maxsize=8)
def _cached_source_dot_icon(color_hex: str) -> QIcon:
    """Build a 10x10 circular dot icon (cache keyed by resolved hex for theme changes)."""
    pm = QPixmap(QSize(10, 10))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(QPen(Qt.GlobalColor.transparent))
    painter.drawEllipse(1, 1, 8, 8)
    painter.end()
    return QIcon(pm)


def source_dot_icon(source: str) -> QIcon:
    """Return a small coloured dot for a variable *source* (sidebar section headers).

    Maps the same semantic roles as ``sidebarSourceDot`` in ``global_qss.py``:
    ``environment`` → accent, ``collection`` → success, ``local`` and ``global`` → warning.
    """
    key = source if source in ("environment", "collection", "local", "global") else "local"
    color_hex = {
        "environment": theme.COLOR_ACCENT,
        "collection": theme.COLOR_SUCCESS,
        "local": theme.COLOR_WARNING,
        "global": theme.COLOR_WARNING,
    }[key]
    return _cached_source_dot_icon(color_hex)


@dataclass
class TreeFillState:
    """Mutable counters while building a debug value tree."""

    nodes: int = 0


def _dict_data_keys(d: dict[Any, Any]) -> list[Any]:
    """Sorted dict keys excluding the classname sentinel."""
    return sorted((k for k in d if k != CLASSNAME_KEY), key=lambda k: str(k))


def _inline_atom(value: Any) -> str:
    """Short inner form for dict/list inline previews (avoids deep recursion)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        if len(value) > 28:
            frag = value[:24] + "…"
            return json.dumps(frag, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return f"Object{{{len(_dict_data_keys(value))}}}"
    if isinstance(value, list | tuple):
        return f"Array[{len(value)}]"
    return type(value).__name__


def preview_cell(value: Any, *, max_len: int = 96) -> str:
    """Return a short second-column preview for *value* (JetBrains-style)."""
    if value is None:
        s = "null"
    elif isinstance(value, bool):
        s = "true" if value else "false"
    elif isinstance(value, int | float):
        s = str(value)
    elif isinstance(value, str):
        s = json.dumps(value, ensure_ascii=False)
    elif isinstance(value, dict):
        keys = _dict_data_keys(value)
        cn_raw = value.get(CLASSNAME_KEY)
        class_name = cn_raw.strip() if isinstance(cn_raw, str) else ""
        take = keys[:PREVIEW_INLINE_KEYS]
        parts = [f"{k}: {_inline_atom(value[k])}" for k in take]
        if len(keys) > PREVIEW_INLINE_KEYS:
            parts.append("…")
        inner = ", ".join(parts) if parts else " "
        if class_name:
            s = f"{class_name} {{ {inner} }}"
        else:
            if not keys:
                s = f"Object{{{0}}}"
            elif len(keys) > PREVIEW_INLINE_KEYS:
                s = f"{{ {inner} }}"
            else:
                s = f"{{ {inner} }}"
    elif isinstance(value, list | tuple):
        n = len(value)
        take = list(value[:PREVIEW_INLINE_KEYS])
        shown = ", ".join(_inline_atom(v) for v in take)
        if n > PREVIEW_INLINE_KEYS:
            rest = n - PREVIEW_INLINE_KEYS
            s = f"[{shown}, … +{rest} more]"
        else:
            s = f"[{shown}]"
    else:
        s = type(value).__name__
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _value_tooltip(value: Any) -> str:
    """Full tooltip text for the value column."""
    try:
        if isinstance(value, dict | list | tuple):
            return json.dumps(value, indent=2, ensure_ascii=False)
        return str(value)
    except (TypeError, ValueError):
        return repr(value)


def is_expandable_container(value: Any) -> bool:
    """Return True if *value* should be shown in the tree view."""
    return isinstance(value, dict | list | tuple)


def debug_tree_cell_text(item: QTreeWidgetItem, column: int) -> str:
    """Return visible text for *column* (``QLabel`` item widget or native item text)."""
    tree = item.treeWidget()
    if tree is not None:
        w = tree.itemWidget(item, column)
        if w is not None and isinstance(w, QLabel):
            return w.text()
    return item.text(column)


def attach_selectable_cell_widgets(item: QTreeWidgetItem) -> None:
    """Show name/value columns with selectable ``QLabel`` cells.

    Native text in those columns is cleared after the label is attached so the
    default delegate does not repaint the same string under the widget.

    Section roots (``UserRole`` value ``"section"``) keep the default delegate so the
    source dot icon and bold title render unchanged.
    """
    tree = item.treeWidget()
    if tree is None:
        return
    if item.data(0, Qt.ItemDataRole.UserRole) == "section":
        return
    for col in (0, 1):
        text = item.text(col)
        tip = item.toolTip(col)
        lab = QLabel(text)
        lab.setObjectName("debugTreeCellLabel")
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lab.setToolTip(tip)
        lab.setWordWrap(False)
        lab.setMargin(0)
        lab.setIndent(0)
        lab.setFrameShape(QFrame.Shape.NoFrame)
        lab.setAutoFillBackground(False)
        lab.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        # Match the tree viewport font (avoids mismatched metrics vs item delegate text).
        lab.setFont(tree.font())
        tree.setItemWidget(item, col, lab)
        item.setText(col, "")


def fill_tree_item(
    parent_item: QTreeWidgetItem,
    value: Any,
    depth: int,
    state: TreeFillState,
    ancestor_ids: frozenset[int],
) -> None:
    """Recursively attach children under *parent_item* for *value*."""
    if state.nodes >= MAX_TREE_NODES:
        return
    if depth >= MAX_TREE_DEPTH:
        more = QTreeWidgetItem(["…", "(max depth)"])
        parent_item.addChild(more)
        attach_selectable_cell_widgets(more)
        state.nodes += 1
        return

    oid = id(value) if isinstance(value, dict | list | tuple) else 0
    if oid and oid in ancestor_ids:
        cycle = QTreeWidgetItem(["", "(circular)"])
        parent_item.addChild(cycle)
        attach_selectable_cell_widgets(cycle)
        state.nodes += 1
        return

    next_ancestors = ancestor_ids | {oid} if oid else ancestor_ids

    if isinstance(value, dict):
        keys = _dict_data_keys(value)[:MAX_CHILDREN_PER_NODE]
        for key in keys:
            if state.nodes >= MAX_TREE_NODES:
                break
            child_val = value[key]
            row = QTreeWidgetItem([str(key), preview_cell(child_val)])
            row.setToolTip(1, _value_tooltip(child_val))
            parent_item.addChild(row)
            attach_selectable_cell_widgets(row)
            state.nodes += 1
            if is_expandable_container(child_val) and child_val:
                fill_tree_item(row, child_val, depth + 1, state, next_ancestors)
    elif isinstance(value, list | tuple):
        for idx, child_val in enumerate(value[:MAX_CHILDREN_PER_NODE]):
            if state.nodes >= MAX_TREE_NODES:
                break
            label = f"[{idx}]"
            row = QTreeWidgetItem([label, preview_cell(child_val)])
            row.setToolTip(1, _value_tooltip(child_val))
            parent_item.addChild(row)
            attach_selectable_cell_widgets(row)
            state.nodes += 1
            if is_expandable_container(child_val) and child_val:
                fill_tree_item(row, child_val, depth + 1, state, next_ancestors)


def populate_debug_tree(tree: QTreeWidget, value: Any) -> None:
    """Clear *tree* and fill it from JSON-like *value* (dict or sequence)."""
    tree.clear()
    state = TreeFillState()
    if isinstance(value, dict):
        keys = _dict_data_keys(value)[:MAX_CHILDREN_PER_NODE]
        for key in keys:
            if state.nodes >= MAX_TREE_NODES:
                break
            child_val = value[key]
            top = QTreeWidgetItem([str(key), preview_cell(child_val)])
            top.setToolTip(1, _value_tooltip(child_val))
            tree.addTopLevelItem(top)
            attach_selectable_cell_widgets(top)
            state.nodes += 1
            if is_expandable_container(child_val) and child_val:
                fill_tree_item(top, child_val, 1, state, frozenset())
    elif isinstance(value, list | tuple):
        for idx, child_val in enumerate(value[:MAX_CHILDREN_PER_NODE]):
            if state.nodes >= MAX_TREE_NODES:
                break
            top = QTreeWidgetItem([f"[{idx}]", preview_cell(child_val)])
            top.setToolTip(1, _value_tooltip(child_val))
            tree.addTopLevelItem(top)
            attach_selectable_cell_widgets(top)
            state.nodes += 1
            if is_expandable_container(child_val) and child_val:
                fill_tree_item(top, child_val, 1, state, frozenset())
    if state.nodes >= MAX_TREE_NODES and tree.topLevelItemCount() > 0:
        trunc = QTreeWidgetItem(["…", "(truncated)"])
        tree.addTopLevelItem(trunc)
        attach_selectable_cell_widgets(trunc)


def make_debug_value_tree(
    *,
    object_name: str = "debugVariablesTree",
    show_header: bool = False,
) -> QTreeWidget:
    """Build a two-column Name|Value tree with global-QSS-friendly *object_name*."""
    tree = QTreeWidget()
    tree.setObjectName(object_name)
    tree.setColumnCount(2)
    if show_header:
        tree.setHeaderLabels(["Name", "Value"])
    else:
        tree.setHeaderLabels(["", ""])
        tree.header().hide()
    tree.setAlternatingRowColors(True)
    tree.setRootIsDecorated(True)
    tree.setUniformRowHeights(False)
    tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    hdr = tree.header()
    hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    return tree
