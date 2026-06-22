"""RAM regression tests for virtualized AI transcript loading."""

from __future__ import annotations

import gc
import resource
import tracemalloc
from pathlib import Path
from typing import Any, cast

from PySide6.QtWidgets import QApplication

from services.ai.chat.transcript_window import INITIAL_TAIL_TURNS
from tests.qt_widget_lifecycle import run_gc_after_qt_flush
from tests.ui.sidebar.ai.test_session_transcript_load import _long_messages, _tail_payload
from ui.main_window.ai_chat_controller import _AiChatControllerMixin
from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent


class _Host(_AiChatControllerMixin):
    """Minimal controller host."""

    def __init__(self, panel: AiChatPanel) -> None:
        """Wire panel."""
        from types import SimpleNamespace

        from ui.sidebar.ai.workers.session_load_worker import AiChatSessionLoader

        self._right_sidebar = cast(
            Any,
            SimpleNamespace(
                ai_chat_panel=panel,
                set_ai_session_title=lambda _title: None,
                set_ai_session_title_rename_enabled=lambda _enabled: None,
            ),
        )
        self._active_ai_session_id = None
        self._session_load_generation = 0
        self._manual_ai_session_titles = set()
        from PySide6.QtWidgets import QWidget

        self._session_loader = AiChatSessionLoader(QWidget())


def _bubble_count(panel: AiChatPanel) -> int:
    """Return rendered bubble count."""
    return len(panel.findChildren(ChatMessageBubble))


def _rendered_markdown_count(panel: AiChatPanel) -> int:
    """Count assistant markdown bodies that finished Pygments rendering."""
    count = 0
    for body in panel.findChildren(MarkdownContent):
        if not body.is_render_deferred():
            count += 1
    return count


def _median_rss_kb() -> int:
    """Sample process RSS three times and return the median (Linux KB)."""
    samples = [resource.getrusage(resource.RUSAGE_SELF).ru_maxrss for _ in range(3)]
    samples.sort()
    return samples[1]


def _heap_growth_bytes() -> int:
    """Return positive lineno heap growth from the current tracemalloc compare."""
    assert _HEAP_SNAP_BEFORE is not None
    snap_after = tracemalloc.take_snapshot()
    stats = snap_after.compare_to(_HEAP_SNAP_BEFORE, "lineno")
    return int(sum(stat.size_diff for stat in stats if stat.size_diff > 0))


def _current_rss_kb() -> int:
    """Return the process resident set size in KiB (Linux ``VmRSS`` when available)."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        pass
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


_HEAP_SNAP_BEFORE: tracemalloc.Snapshot | None = None


def _fresh_panel(qtbot) -> AiChatPanel:
    """Create a sized, exposed chat panel for isolated memory samples."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)
    return panel


def _measure_tail_load(panel: AiChatPanel, host: _Host, messages: list, qapp) -> dict[str, int]:
    """Load a tail page and return memory samples."""
    global _HEAP_SNAP_BEFORE
    tracemalloc.start()
    _HEAP_SNAP_BEFORE = tracemalloc.take_snapshot()
    payload = _tail_payload("mem", "Mem", messages[-INITIAL_TAIL_TURNS * 2 :], has_older=True)
    host._session_load_generation = 1
    host._on_session_load_finished(1, payload)
    panel.flush_transcript_load()
    run_gc_after_qt_flush(qapp)
    for _ in range(3):
        qapp.processEvents()
    heap = _heap_growth_bytes()
    tracemalloc.stop()
    _HEAP_SNAP_BEFORE = None
    return {
        "bubbles": _bubble_count(panel),
        "rendered": _rendered_markdown_count(panel),
        "rss_kb": _median_rss_kb(),
        "heap": heap,
    }


def _measure_full_load(panel: AiChatPanel, messages: list, qtbot, qapp) -> dict[str, int]:
    """Load the full transcript without virtualization."""
    global _HEAP_SNAP_BEFORE
    tracemalloc.start()
    _HEAP_SNAP_BEFORE = tracemalloc.take_snapshot()
    panel.load_transcript(messages)
    panel.flush_transcript_load()
    qtbot.wait(10)
    run_gc_after_qt_flush(qapp)
    for _ in range(3):
        qapp.processEvents()
    heap = _heap_growth_bytes()
    tracemalloc.stop()
    _HEAP_SNAP_BEFORE = None
    return {
        "bubbles": _bubble_count(panel),
        "rendered": _rendered_markdown_count(panel),
        "rss_kb": _median_rss_kb(),
        "heap": heap,
    }


def _measure_tail_footprint(
    panel: AiChatPanel, host: _Host, messages: list, qapp
) -> dict[str, int]:
    """Load a tail page and return live RSS + widget counts."""
    payload = _tail_payload("mem", "Mem", messages[-INITIAL_TAIL_TURNS * 2 :], has_older=True)
    host._session_load_generation = 1
    host._on_session_load_finished(1, payload)
    panel.flush_transcript_load()
    run_gc_after_qt_flush(qapp)
    for _ in range(3):
        qapp.processEvents()
    return {
        "bubbles": _bubble_count(panel),
        "rss_kb": _current_rss_kb(),
    }


def _measure_full_footprint(panel: AiChatPanel, messages: list, qtbot, qapp) -> dict[str, int]:
    """Load the full transcript and return live RSS + widget counts."""
    panel.load_transcript(messages)
    panel.flush_transcript_load()
    qtbot.wait(10)
    run_gc_after_qt_flush(qapp)
    for _ in range(3):
        qapp.processEvents()
    return {
        "bubbles": _bubble_count(panel),
        "rss_kb": _current_rss_kb(),
    }


def test_tail_load_bounded_widgets(qapp: QApplication, qtbot) -> None:
    """Tail load materializes far fewer bubbles than a full session."""
    messages = _long_messages(40)
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)
    host = _Host(panel)
    tail = _measure_tail_load(panel, host, messages, qapp)
    panel.clear()
    gc.collect()
    full = _measure_full_load(panel, messages, qtbot, qapp)
    assert full["bubbles"] == 40
    assert tail["bubbles"] <= INITIAL_TAIL_TURNS * 2 + 2
    assert tail["bubbles"] < full["bubbles"]


def test_tail_load_lower_heap_than_full(qapp: QApplication, qtbot) -> None:
    """Virtual tail load uses less resident memory than full materialization."""
    messages = _long_messages(40)
    tail_panel = _fresh_panel(qtbot)
    tail = _measure_tail_footprint(tail_panel, _Host(tail_panel), messages, qapp)

    full_panel = _fresh_panel(qtbot)
    full = _measure_full_footprint(full_panel, messages, qtbot, qapp)

    assert full["bubbles"] == 40
    assert tail["bubbles"] < full["bubbles"]
    assert tail["rss_kb"] < full["rss_kb"]


def test_tail_load_fewer_rendered_markdown_bodies(qapp: QApplication, qtbot) -> None:
    """Tail load defers more assistant markdown than full load."""
    messages = _long_messages(40)
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(360, 480)
    qtbot.waitExposed(panel)
    host = _Host(panel)
    tail = _measure_tail_load(panel, host, messages, qapp)
    panel.clear()
    gc.collect()
    full = _measure_full_load(panel, messages, qtbot, qapp)
    assert tail["rendered"] < full["rendered"] - 5
