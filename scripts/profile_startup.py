#!/usr/bin/env python3
"""Diagnostic: profile Postmark startup CPU and memory costs.

Measures each phase of startup end-to-end:
1. QApplication + theme/settings init
2. MainWindow construction (no tabs yet)
3. Collection tree load (background fetch simulation)
4. Session restore (_restore_tabs) with N request tabs

Also reports per-widget memory costs and per-tab restore timing.

Usage:
    poetry run python scripts/profile_startup.py [NUM_TABS]
"""

from __future__ import annotations

import cProfile
import gc
import io
import os
import pstats
import resource
import sys
import time

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _rss_mb() -> float:
    """Return current RSS in megabytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _snapshot(label: str, start: float, mem_before: float) -> None:
    mem_after = _rss_mb()
    elapsed = time.perf_counter() - start
    print(f"  {label}: {elapsed * 1000:>8.1f} ms   RSS: {mem_after:>6.1f} MB  (+{mem_after - mem_before:>5.1f} MB)")


def main() -> None:
    num_tabs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"=== Postmark Startup Diagnostic ({num_tabs} tabs) ===\n")

    # -- Phase 1: QApplication + Theme + TabSettings --------------------
    mem0 = _rss_mb()
    t0 = time.perf_counter()

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from ui.styling.icons import load_font
    from ui.styling.tab_settings_manager import TabSettingsManager
    from ui.styling.theme_manager import ThemeManager

    theme_manager = ThemeManager(app)
    tab_settings_manager = TabSettingsManager(app)
    load_font()

    _snapshot("Phase 1 — QApp + theme + font", t0, mem0)

    # -- Phase 2: init_db -----------------------------------------------
    mem1 = _rss_mb()
    t1 = time.perf_counter()

    from database.database import init_db

    init_db()

    _snapshot("Phase 2 — init_db()", t1, mem1)

    # -- Seed test data --------------------------------------------------
    mem2 = _rss_mb()
    t2 = time.perf_counter()

    from services.collection_service import CollectionService

    svc = CollectionService()
    coll = svc.create_collection("DiagnosticCollection")
    request_ids: list[int] = []
    for i in range(num_tabs):
        req = svc.create_request(
            coll.id, "GET", f"http://example.com/api/endpoint-{i}", f"Request {i}"
        )
        request_ids.append(req.id)

    _snapshot(f"Phase 2b — seed {num_tabs} requests", t2, mem2)

    # Persist a session with N tabs
    tab_settings_manager.save_open_tabs({
        "tabs": [
            {"type": "request", "id": rid, "method": "GET", "name": f"Request {i}"}
            for i, rid in enumerate(request_ids)
        ],
        "active": 0,
    })

    # -- Phase 3: MainWindow construction --------------------------------
    mem3 = _rss_mb()
    t3 = time.perf_counter()

    from ui.main_window import MainWindow

    window = MainWindow(
        theme_manager=theme_manager,
        tab_settings_manager=tab_settings_manager,
    )

    _snapshot("Phase 3 — MainWindow.__init__()", t3, mem3)

    # -- Phase 4: load_finished → _restore_tabs --------------------------
    # Profile this phase in detail
    mem4 = _rss_mb()
    t4 = time.perf_counter()

    profiler = cProfile.Profile()
    profiler.enable()

    window.collection_widget.load_finished.emit()

    profiler.disable()

    _snapshot("Phase 4 — load_finished + _restore_tabs", t4, mem4)

    # -- Phase 5: show() -------------------------------------------------
    mem5 = _rss_mb()
    t5 = time.perf_counter()

    window.show()
    app.processEvents()

    _snapshot("Phase 5 — show() + processEvents", t5, mem5)

    # -- Summary ----------------------------------------------------------
    total_ms = (time.perf_counter() - t0) * 1000
    total_mem = _rss_mb()
    print(f"\n  TOTAL: {total_ms:>8.1f} ms   RSS: {total_mem:>6.1f} MB")

    # -- Per-widget memory estimate --------------------------------------
    print("\n--- Per-Widget Memory ---")
    gc.collect()
    mem_before_editor = _rss_mb()

    from ui.request.request_editor import RequestEditorWidget

    editors = []
    for _ in range(5):
        editors.append(RequestEditorWidget())
    gc.collect()
    mem_after_editor = _rss_mb()
    per_editor = (mem_after_editor - mem_before_editor) / 5
    print(f"  RequestEditorWidget: ~{per_editor:.1f} MB each")

    from ui.request.response_viewer import ResponseViewerWidget

    viewers = []
    mem_before_viewer = _rss_mb()
    for _ in range(5):
        viewers.append(ResponseViewerWidget())
    gc.collect()
    mem_after_viewer = _rss_mb()
    per_viewer = (mem_after_viewer - mem_before_viewer) / 5
    print(f"  ResponseViewerWidget: ~{per_viewer:.1f} MB each")

    print(f"  Pair (editor+viewer): ~{per_editor + per_viewer:.1f} MB each")
    print(f"  Estimated {num_tabs} tab pairs: ~{(per_editor + per_viewer) * num_tabs:.1f} MB")

    # -- Top 30 profiled functions in Phase 4 ----------------------------
    print("\n--- Phase 4 cProfile Top 30 (cumulative) ---")
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(30)
    print(stream.getvalue())

    # -- Top 30 by total time -------------------------------------------
    print("--- Phase 4 cProfile Top 30 (tottime) ---")
    stream2 = io.StringIO()
    stats2 = pstats.Stats(profiler, stream=stream2)
    stats2.sort_stats("tottime")
    stats2.print_stats(30)
    print(stream2.getvalue())

    window.close()


if __name__ == "__main__":
    main()
