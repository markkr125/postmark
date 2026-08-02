"""Variable map cache behaviour on tab switch."""

from __future__ import annotations

from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from services.collection_service import CollectionService
from services.environment_service import EnvironmentService
from tests.ui.conftest import finish_main_window_startup
from ui.main_window import MainWindow
from ui.styling.tab_settings_manager import TabSettingsManager


class TestVariableMapCache:
    """``build_combined_variable_detail_map`` is cached per tab switch."""

    def test_repeated_tab_switch_uses_cache(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Switching back to the same request tab reuses the variable map cache."""
        coll = CollectionService.create_collection("VarCache")
        req_a = CollectionService.create_request(coll.id, "GET", "http://a", "A")
        req_b = CollectionService.create_request(coll.id, "GET", "http://b", "B")
        tab_settings = TabSettingsManager(qapp)
        tab_settings.save_open_tabs(
            {
                "tabs": [
                    {
                        "type": "request",
                        "id": req_a.id,
                        "method": "GET",
                        "name": "A",
                    },
                    {
                        "type": "request",
                        "id": req_b.id,
                        "method": "GET",
                        "name": "B",
                    },
                ],
                "active": 0,
            }
        )
        window = MainWindow(tab_settings_manager=tab_settings)
        qtbot.addWidget(window)
        finish_main_window_startup(window)

        env_id = window._env_selector.current_environment_id()
        cache_key_a = (env_id, req_a.id, None)
        assert cache_key_a in window._variable_map_cache

        with patch.object(
            EnvironmentService,
            "build_combined_variable_detail_map",
            wraps=EnvironmentService.build_combined_variable_detail_map,
        ) as mock_build:
            window._tab_bar.setCurrentIndex(1)
            window._on_tab_changed(1)
            window._flush_tab_change()
            mock_build.reset_mock()
            window._tab_bar.setCurrentIndex(0)
            window._on_tab_changed(0)
            window._flush_tab_change()
            calls_for_a = [
                call
                for call in mock_build.call_args_list
                if len(call[0]) > 1 and call[0][1] == req_a.id
            ]
            assert calls_for_a == []
