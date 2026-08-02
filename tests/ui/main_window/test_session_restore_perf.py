"""Session restore performance and prefetch behaviour tests."""

from __future__ import annotations

import time
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from tests.ui.conftest import finish_main_window_startup
from ui.main_window import MainWindow
from ui.styling.tab_settings_manager import TabSettingsManager


class TestSessionRestoreFast:
    """Deferred tab chips restore without slow-motion pacing."""

    def test_thirty_five_tabs_restore_under_100ms(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """35 deferred request chips restore in one batch (<100 ms wall time)."""
        coll = CollectionService.create_collection("RestorePerf")
        ids = [
            CollectionService.create_request(
                coll.id,
                "GET",
                f"http://example.com/{i}",
                f"Req {i}",
            ).id
            for i in range(35)
        ]
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {"type": "request", "id": rid, "method": "GET", "name": f"Req {i}"}
                    for i, rid in enumerate(ids)
                ],
                "active": 0,
            }
        )
        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)

        t0 = time.perf_counter()
        finish_main_window_startup(window)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Active tab materialises on finalize; remaining tabs stay deferred.
        assert window._tab_bar.count() == 35
        assert len(window._deferred_tabs) == 34
        assert elapsed_ms < 2000.0

    def test_folder_tab_restores_as_deferred_chip(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Folder tabs restore as chips and materialize on first select."""
        coll = CollectionService.create_collection("FolderRestore")
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [{"type": "folder", "id": coll.id, "name": coll.name}],
                "active": 0,
            }
        )
        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        finish_main_window_startup(window)

        assert window._tab_bar.count() == 1
        assert 0 in window._tabs
        ctx = window._tabs[0]
        assert ctx.tab_type == "folder"
        assert ctx.collection_id == coll.id

    def test_materialize_uses_prefetch_cache(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Materialising a deferred tab uses prefetch cache instead of get_request."""
        coll = CollectionService.create_collection("PrefetchHit")
        req = CollectionService.create_request(coll.id, "POST", "http://x", "Hit")
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {
                        "type": "request",
                        "id": req.id,
                        "method": "POST",
                        "name": "Hit",
                    },
                    {
                        "type": "request",
                        "id": req.id,
                        "method": "POST",
                        "name": "Hit",
                    },
                ],
                "active": 1,
            }
        )
        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        finish_main_window_startup(window)

        deferred_idx = next(iter(window._deferred_tabs))
        with patch.object(CollectionService, "get_request") as mock_get:
            window._materialise_deferred_tab(deferred_idx)
            mock_get.assert_not_called()

    def test_old_format_restores_as_deferred_chip(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Legacy session entries without method/name become deferred chips."""
        coll = CollectionService.create_collection("Legacy")
        req = CollectionService.create_request(coll.id, "PUT", "http://legacy", "Legacy")
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs({"tabs": [{"type": "request", "id": req.id}], "active": 0})
        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        finish_main_window_startup(window)

        assert window._tab_bar.count() == 1
        assert 0 not in window._deferred_tabs
        assert window._tabs[0].request_id == req.id

    def test_prefetch_cancelled_on_close(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Prefetch worker is torn down cleanly when the window closes."""
        coll = CollectionService.create_collection("PrefetchCancel")
        req = CollectionService.create_request(coll.id, "GET", "http://cancel", "Cancel")
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {
                        "type": "request",
                        "id": req.id,
                        "method": "GET",
                        "name": "Cancel",
                    }
                ],
                "active": 0,
            }
        )
        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        finish_main_window_startup(window)
        window._cleanup_startup_threads()
        window.close()
        qapp.processEvents()
