"""Safe QWidget coordinate mapping for transcript scroll helpers."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid


def widget_is_descendant_of(widget: QWidget, ancestor: QWidget) -> bool:
    """Return True when *widget* is *ancestor* or nested under it."""
    if not isValid(widget) or not isValid(ancestor):
        return False
    node: QWidget | None = widget
    while node is not None:
        if node is ancestor:
            return True
        node = node.parentWidget()
    return False


def map_widget_y_to_ancestor(
    widget: QWidget, ancestor: QWidget, *, offset_y: int = 0
) -> int | None:
    """Map *widget* Y into *ancestor* space, or None when hierarchy is broken."""
    if not widget_is_descendant_of(widget, ancestor):
        return None
    return widget.mapTo(ancestor, QPoint(0, offset_y)).y()


def map_widget_point_to_ancestor(
    widget: QWidget,
    ancestor: QWidget,
    point: QPoint,
) -> QPoint | None:
    """Map *point* on *widget* into *ancestor* space, or None when hierarchy is broken."""
    if not widget_is_descendant_of(widget, ancestor):
        return None
    return widget.mapTo(ancestor, point)


__all__ = [
    "map_widget_point_to_ancestor",
    "map_widget_y_to_ancestor",
    "widget_is_descendant_of",
]
