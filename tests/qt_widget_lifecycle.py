"""Safe Qt widget teardown helpers for tests that assert collection or memory bounds."""

from __future__ import annotations

import gc
import time
import weakref
from collections.abc import Callable

from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import Shiboken

from tests.qt_popup_cleanup import flush_deferred_widget_deletes

_DEFAULT_WEAKREF_TIMEOUT_S = 5.0
_QT_FLUSH_PASSES = 16


def flush_qt_pending_deletes(qapp: QApplication) -> None:
    """Pump events until deferred Qt deletes are processed."""
    for _ in range(_QT_FLUSH_PASSES):
        qapp.processEvents()
        flush_deferred_widget_deletes(qapp)


def dispose_qt_widget(qapp: QApplication, widget: QWidget, *, flush: bool = False) -> None:
    """Queue C++ teardown for *widget*; never synchronously delete Qt wrappers."""
    if not Shiboken.isValid(widget):
        return
    detach = getattr(widget, "detach_lsp", None)
    if callable(detach):
        detach()
    widget.blockSignals(True)
    widget.hide()
    widget.close()
    widget.setParent(None)
    widget.deleteLater()
    if flush:
        flush_deferred_widget_deletes(qapp)


def run_gc_after_qt_flush(qapp: QApplication) -> None:
    """Flush Qt deletes once, then run a single GC pass (safe for Shiboken wrappers)."""
    flush_qt_pending_deletes(qapp)
    gc.collect()


def wait_for_weakrefs_cleared(
    qapp: QApplication,
    refs: list[weakref.ref],
    *,
    timeout_s: float = _DEFAULT_WEAKREF_TIMEOUT_S,
    on_retry: Callable[[], None] | None = None,
) -> int:
    """Return remaining live weakrefs after bounded Qt flush + GC polling."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if on_retry is not None:
            on_retry()
        flush_qt_pending_deletes(qapp)
        gc.collect()
        alive = sum(1 for ref in refs if ref() is not None)
        if alive == 0:
            return 0
    return sum(1 for ref in refs if ref() is not None)
