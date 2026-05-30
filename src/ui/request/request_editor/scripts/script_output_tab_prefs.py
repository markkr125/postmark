"""Persist and restore the script output panel's bottom tab strip (QSettings)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QTabWidget, QWidget

from ui.styling.theme_manager import _APP, _ORG

_SLUG_OUTPUT = "output"
_SLUG_DEBUGGER = "debugger"
_SLUG_PROBLEMS = "problems"
_SLUG_ITERATIONS = "iterations"
_SLUG_MOCK = "mock"
_VALID_SLUGS = frozenset(
    {_SLUG_OUTPUT, _SLUG_DEBUGGER, _SLUG_PROBLEMS, _SLUG_ITERATIONS, _SLUG_MOCK}
)


def _settings_key(script_type: str) -> str:
    st = (script_type or "pre_request").strip().lower()
    if st not in ("pre_request", "test"):
        st = "pre_request"
    return f"scripting/output_sub_tab/{st}"


def load_output_sub_tab_slug(script_type: str) -> str:
    """Return the last-selected output-strip tab slug for *script_type*."""
    from PySide6.QtCore import QSettings

    raw = QSettings(_ORG, _APP).value(_settings_key(script_type), _SLUG_OUTPUT)
    slug = str(raw or _SLUG_OUTPUT).strip().lower()
    return slug if slug in _VALID_SLUGS else _SLUG_OUTPUT


def save_output_sub_tab_slug(script_type: str, slug: str) -> None:
    """Persist the active output-strip tab for *script_type*."""
    key = slug.strip().lower()
    if key not in _VALID_SLUGS:
        return
    from PySide6.QtCore import QSettings

    QSettings(_ORG, _APP).setValue(_settings_key(script_type), key)


def output_has_visible_content(output: dict[str, Any]) -> bool:
    """Return True when *output* has console, tests, variables, or an error message."""
    logs = output.get("console_logs")
    if isinstance(logs, list) and logs:
        return True
    tests = output.get("test_results")
    if isinstance(tests, list) and tests:
        return True
    var_changes = output.get("variable_changes")
    if isinstance(var_changes, dict) and var_changes:
        return True
    for key in ("error", "message"):
        val = output.get(key)
        if isinstance(val, str) and val.strip():
            return True
    return False


def _slug_for_widget(panel: Any, widget: QWidget | None) -> str | None:
    if widget is None:
        return None
    if widget is getattr(panel, "_output_tab_page", None):
        return _SLUG_OUTPUT
    if widget is getattr(panel, "_debugger_tab_page", None):
        return _SLUG_DEBUGGER
    if widget is getattr(panel, "_problems_tab", None):
        return _SLUG_PROBLEMS
    if widget is getattr(panel, "_iterations_tab_page", None):
        return _SLUG_ITERATIONS
    mock = getattr(panel, "_mock_response_tab", None)
    if mock is not None and widget is mock:
        return _SLUG_MOCK
    return None


def _widget_for_slug(panel: Any, slug: str) -> QWidget | None:
    if slug == _SLUG_OUTPUT:
        return getattr(panel, "_output_tab_page", None)
    if slug == _SLUG_DEBUGGER:
        return getattr(panel, "_debugger_tab_page", None)
    if slug == _SLUG_PROBLEMS:
        return getattr(panel, "_problems_tab", None)
    if slug == _SLUG_ITERATIONS:
        return getattr(panel, "_iterations_tab_page", None)
    if slug == _SLUG_MOCK:
        return getattr(panel, "_mock_response_tab", None)
    return None


def restore_output_sub_tab(panel: Any) -> None:
    """Select the saved output-strip tab when the panel is first built."""
    tabs: QTabWidget | None = getattr(panel, "_script_output_tabs", None)
    if tabs is None:
        return
    slug = load_output_sub_tab_slug(getattr(panel, "_script_type", "pre_request"))
    target = _widget_for_slug(panel, slug)
    if target is None:
        return
    panel._restoring_output_tab = True
    try:
        tabs.setCurrentWidget(target)
    finally:
        panel._restoring_output_tab = False


def wire_output_sub_tab_persistence(panel: Any) -> None:
    """Save the active output-strip tab whenever the user changes it."""
    tabs: QTabWidget | None = getattr(panel, "_script_output_tabs", None)
    if tabs is None or getattr(panel, "_output_tab_prefs_wired", False):
        return
    panel._output_tab_prefs_wired = True

    def _on_changed(_index: int) -> None:
        if getattr(panel, "_restoring_output_tab", False):
            return
        slug = _slug_for_widget(panel, tabs.currentWidget())
        if slug is not None:
            save_output_sub_tab_slug(getattr(panel, "_script_type", "pre_request"), slug)

    tabs.currentChanged.connect(_on_changed)
    restore_output_sub_tab(panel)


def persist_current_output_sub_tab(panel: Any) -> None:
    """Write the current tab slug to settings (e.g. after programmatic focus)."""
    tabs: QTabWidget | None = getattr(panel, "_script_output_tabs", None)
    if tabs is None:
        return
    slug = _slug_for_widget(panel, tabs.currentWidget())
    if slug is not None:
        save_output_sub_tab_slug(getattr(panel, "_script_type", "pre_request"), slug)
