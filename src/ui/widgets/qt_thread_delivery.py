"""Deliver results from ``QThreadPool`` workers onto the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QMetaObject, QObject, Qt, Q_ARG
from shiboken6 import isValid


def queue_int_str(
    target: QObject,
    slot: str,
    generation: int,
    text: str,
) -> bool:
    """Invoke *slot* ``(generation, text)`` on the GUI thread; return False if *target* is gone."""
    if not isValid(target):
        return False
    QMetaObject.invokeMethod(  # type: ignore[call-overload]
        target,
        slot,
        Qt.ConnectionType.QueuedConnection,
        Q_ARG(int, generation),
        Q_ARG(str, text),
    )
    return True
