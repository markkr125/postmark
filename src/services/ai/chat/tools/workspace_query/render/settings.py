"""Safe application settings renderer for the workspace query tool."""

from __future__ import annotations

from services.scripting.context import mask_sensitive_value
from services.scripting.runtime_settings import RuntimeSettings
from ui.styling.history_settings_manager import HistorySettingsManager
from ui.styling.tab_settings_manager import TabSettingsManager


def _safe_setting_line(label: str, value: object) -> str:
    """Format one settings row with sensitive-value masking."""
    return f"- {label}: {mask_sensitive_value(label, str(value))}"


def _render_settings() -> str:
    """Render non-secret runtime, history, and tab settings (never AI provider keys)."""
    lines = ["Application settings (safe subset):"]
    runtime_rows: list[tuple[str, object]] = []
    for label, getter in (
        ("Deno path", RuntimeSettings.deno_path),
        ("Python path", RuntimeSettings.python_path),
        ("LSP enabled", RuntimeSettings.lsp_enabled),
        ("Format on save", RuntimeSettings.format_on_save),
        ("Allow local subrequests", RuntimeSettings.allow_local_subrequests),
    ):
        try:
            runtime_rows.append((label, getter()))
        except Exception:
            runtime_rows.append((label, "unavailable"))
    lines.extend(_safe_setting_line(label, value) for label, value in runtime_rows)
    try:
        history = HistorySettingsManager()
        history_rows = (
            ("History retention days", history.retention_days),
            ("History max items per day", history.max_items_per_day),
            ("History unlimited per day", history.unlimited_per_day),
            ("History max response bytes", history.max_response_bytes),
        )
        lines.extend(_safe_setting_line(label, value) for label, value in history_rows)
    except Exception:
        lines.append("- History settings: unavailable")
    try:
        tabs = TabSettingsManager()
        tab_rows = (
            ("Tabs small labels", tabs.small_labels),
            ("Tabs wrap mode", tabs.wrap_mode),
            ("Tabs show path for duplicates", tabs.show_path_for_duplicates),
            ("Tabs mark modified", tabs.mark_modified),
            ("Tabs show full path on hover", tabs.show_full_path_on_hover),
            ("Tabs open new tabs at end", tabs.open_new_tabs_at_end),
            ("Tabs enable preview tab", tabs.enable_preview_tab),
            ("Tabs activate on close", tabs.activate_on_close),
        )
        lines.extend(_safe_setting_line(label, value) for label, value in tab_rows)
    except Exception:
        lines.append("- Tab settings: unavailable")
    lines.append(
        "Writable Agent keys: deno_path, python_path, lsp_enabled, format_on_save, "
        "allow_local_subrequests, history_*, tabs_* (see mutate:update:settings)."
    )
    return "\n".join(lines)
