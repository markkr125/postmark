"""Provider-row action buttons for the AI settings models tree."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Literal

from PySide6.QtCore import QByteArray, QPoint, Qt, QSettings, QTimer
from PySide6.QtWidgets import QListWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QWidget,
)

from services.ai.ai_config import AiModelEntry
from services.ai.provider_catalog import (
    OLLAMA_CONTEXT_OPTIONS,
    OLLAMA_DEFAULT_CONTEXT_TOKENS,
    ModelSpec,
    cost_display_for_entry,
    format_model_cost_display,
    model_row_label,
    persisted_cost_fields,
    provider_by_key,
)
from ui.styling.icons import phi, phi_menu
from ui.styling.theme import TREE_ROW_HEIGHT
from ui.styling.theme_manager import _APP, _ORG

_AI_PROVIDER_LABEL_MIN_WIDTH = 112
_HEADER_SETTINGS_KEY = "ui/ai_models_tree_header/v4"
_DEFAULT_DATA_COLUMN_WIDTHS = (240, 300, 72, 120)
_ENABLED_COLUMN_WIDTH = 32
ENABLED_COLUMN = 0
NAME_COLUMN = 1
_NAME_COLUMN = NAME_COLUMN
CAPABILITIES_COLUMN = 5
_PERSIST_DEBOUNCE_MS = 250
_MODELS_LIST_BATCH_SIZE = 32


def ai_provider_form_label(text: str) -> QLabel:
    """Right-aligned label for the provider add/edit dialog."""
    lbl = QLabel(text)
    lbl.setMinimumWidth(_AI_PROVIDER_LABEL_MIN_WIDTH)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def ai_provider_field_button_strip(widgets: list[QWidget]) -> QWidget:
    """Full-width, left-aligned row for outline buttons in the provider dialog form."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for widget in widgets:
        row.addWidget(widget)
    row.addStretch()
    wrap = QWidget()
    wrap.setContentsMargins(0, 0, 0, 0)
    wrap.setLayout(row)
    wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return wrap


def make_ollama_default_context_combo(
    init_tokens: int,
    on_changed: Callable[[], None],
) -> QComboBox:
    """Context-size selector for the Ollama provider dialog."""
    combo = QComboBox()
    for label, tokens in OLLAMA_CONTEXT_OPTIONS:
        combo.addItem(label, tokens)
    idx = combo.findData(init_tokens)
    combo.setCurrentIndex(idx if idx >= 0 else combo.findData(OLLAMA_DEFAULT_CONTEXT_TOKENS))
    combo.currentIndexChanged.connect(on_changed)
    return combo


def ollama_context_tokens_from_combo(combo: QComboBox | None) -> int:
    """Read selected Ollama default context tokens from *combo*."""
    if combo is None:
        return 0
    raw = combo.currentData()
    return raw if isinstance(raw, int) and raw > 0 else OLLAMA_DEFAULT_CONTEXT_TOKENS


def validate_provider_credentials(
    *,
    provider_key: str,
    auth_kind: str,
    auth_ref: str,
    base_url: str,
    api_version: str,
) -> str | None:
    """Return a user-facing error when required provider fields are missing."""
    spec = provider_by_key(provider_key)
    if spec is None:
        return "Unknown provider."
    for field in spec.credential_fields:
        if not field.required:
            continue
        if field.field_id == "api_key":
            if auth_kind == "none" or not auth_ref:
                return "API key is required."
        elif field.field_id == "base_url" and not base_url.strip():
            return "Base URL is required."
        elif field.field_id == "api_version" and not api_version.strip():
            return "API version is required."
    return None


def provider_edit_allows_save_without_test(
    *,
    is_edit: bool,
    existing_entries: list[AiModelEntry],
    baseline_fingerprint: tuple[str, ...] | None,
    current_fingerprint: tuple[str, ...],
) -> bool:
    """True when provider type, URL, and credentials are unchanged since open."""
    if not is_edit or not existing_entries or baseline_fingerprint is None:
        return False
    return current_fingerprint == baseline_fingerprint


def model_preview_line_for_spec(spec: ModelSpec) -> str:
    """One models-list row for the provider dialog (no LiteLLM lookup)."""
    suffix = ""
    if spec.input_cost_per_token > 0 or spec.output_cost_per_token > 0:
        cost = format_model_cost_display(
            spec.input_cost_per_token,
            spec.output_cost_per_token,
            model=spec.model,
        )
        if cost:
            suffix = f"  —  {cost}"
    return f"{spec.label}  ({spec.model}){suffix}"


def model_preview_lines_from_entries(entries: list[AiModelEntry]) -> tuple[str, ...]:
    """Preview lines from saved rows; uses persisted costs only (GUI-thread safe)."""
    rows = sorted(
        [row for row in entries if str(row.get("model") or "")],
        key=lambda row: str(row.get("label") or row.get("model") or "").lower(),
    )
    lines: list[str] = []
    for row in rows:
        model = str(row["model"])
        label = str(row.get("label") or model)
        cost = cost_display_for_entry(row)
        suffix = f"  —  {cost}" if cost and cost != "—" else ""
        lines.append(f"{label}  ({model}){suffix}")
    return tuple(lines)


class ModelsListPreviewLoader:
    """Append preview lines to a QListWidget in batches (keeps the dialog responsive)."""

    def __init__(self, list_widget: QListWidget) -> None:
        """Bind to the provider dialog models list."""
        self._list = list_widget
        self._generation = 0
        self._queue: list[str] = []

    def start(self, lines: tuple[str, ...]) -> None:
        """Replace the list contents and load *lines* on the next event-loop ticks."""
        self.cancel()
        self._generation += 1
        generation = self._generation
        self._queue = list(lines)
        self._list.setUpdatesEnabled(False)
        self._list.clear()
        self._list.setUpdatesEnabled(True)
        self._append_batch(generation)

    def cancel(self) -> None:
        """Drop any in-flight batched append."""
        self._generation += 1
        self._queue.clear()

    def _append_batch(self, generation: int) -> None:
        if generation != self._generation or not self._queue:
            return
        batch = self._queue[:_MODELS_LIST_BATCH_SIZE]
        self._queue = self._queue[_MODELS_LIST_BATCH_SIZE:]
        self._list.setUpdatesEnabled(False)
        for line in batch:
            self._list.addItem(line)
        self._list.setUpdatesEnabled(True)
        if self._queue:
            QTimer.singleShot(0, lambda: self._append_batch(generation))


def model_preview_lines_from_specs(specs: tuple[ModelSpec, ...]) -> tuple[str, ...]:
    """Preview lines from fetched specs (no LiteLLM lookup)."""
    ordered = sorted(specs, key=lambda spec: spec.label.lower())
    return tuple(model_preview_line_for_spec(spec) for spec in ordered)


def apply_provider_edit_entries(
    entries: list[AiModelEntry],
    *,
    provider_display_name: str,
    provider_key: str,
    default_context: int = 0,
) -> list[AiModelEntry]:
    """Update display name and optional Ollama default context without re-fetching models."""
    out: list[AiModelEntry] = []
    for row in entries:
        updated: AiModelEntry = {**row, "provider_display_name": provider_display_name}
        if provider_key == "ollama" and default_context > 0:
            updated["default_context"] = default_context
        out.append(updated)
    return out


def provider_template_entry(
    *,
    entry_id: str,
    provider_key: str,
    base_url: str,
    api_version: str,
    auth_kind: Literal["token", "none"],
    auth_ref: str,
    default_context: int = 0,
) -> AiModelEntry:
    """Shared credential fields for :func:`entries_from_model_specs`."""
    row: AiModelEntry = {
        "id": entry_id,
        "provider": provider_key,
        "label": "",
        "model": "",
        "base_url": base_url,
        "api_version": api_version,
        "auth_kind": auth_kind,
        "auth_ref": auth_ref,
    }
    if provider_key == "ollama" and default_context > 0:
        row["default_context"] = default_context
    return row


def entries_from_model_specs(
    template: AiModelEntry,
    models: tuple[ModelSpec, ...],
    *,
    provider_display_name: str,
) -> list[AiModelEntry]:
    """Build persisted rows from fetched :class:`ModelSpec` values."""
    out: list[AiModelEntry] = []
    auth_ref = template.get("auth_ref", "")
    display = provider_display_name.strip()
    for m in models:
        row: AiModelEntry = {
            "id": uuid.uuid4().hex,
            "provider": template["provider"],
            "label": model_row_label(m),
            "provider_display_name": display,
            "model": m.model,
            "base_url": template.get("base_url", ""),
            "api_version": template.get("api_version", ""),
            "auth_kind": template["auth_kind"],
            "auth_ref": auth_ref,
            "context": m.context,
            "tools": m.tools,
            "vision": m.vision,
            "text": m.text,
            "insert": m.insert,
            "reasoning": m.reasoning,
            "reasoning_efforts": list(m.reasoning_efforts),
            "reasoning_default": m.reasoning_default,
            "reasoning_effort": m.reasoning_default if m.reasoning else "",
            "thinking": m.thinking,
            "thinking_default": m.thinking_default,
            "thinking_enabled": m.thinking_default if m.thinking else "",
            "enabled": False,
        }
        if m.context_tiers:
            row["context_tiers"] = list(m.context_tiers)
        row["tiers_checked"] = True
        for key, val in persisted_cost_fields(m).items():
            if key == "input_cost_per_token":
                row["input_cost_per_token"] = val
            else:
                row["output_cost_per_token"] = val
        dc = template.get("default_context")
        if isinstance(dc, int) and dc > 0:
            row["default_context"] = dc
        out.append(row)
    return out


def make_provider_gear_button(
    *,
    on_edit: Callable[[], None],
    on_refresh: Callable[[], None],
    on_select_all: Callable[[], None],
    on_deselect_all: Callable[[], None],
    on_remove: Callable[[], None],
) -> QWidget:
    """Gear menu aligned to the right of the Capabilities column on provider rows."""
    wrap = QWidget()
    wrap.setFixedHeight(TREE_ROW_HEIGHT)
    row = QHBoxLayout(wrap)
    row.setContentsMargins(4, 0, 4, 0)
    row.setSpacing(0)
    row.addStretch(1)

    menu = QMenu(wrap)
    menu.setObjectName("aiProviderActionsMenu")
    menu.setToolTipsVisible(True)
    edit_act = menu.addAction(phi_menu("pencil-simple"), "Edit provider")
    edit_act.setToolTip("Edit credentials and connection settings")
    edit_act.triggered.connect(on_edit)
    refresh_act = menu.addAction(phi_menu("arrow-clockwise"), "Refresh models")
    refresh_act.setToolTip("Re-fetch the model list from this provider")
    refresh_act.triggered.connect(on_refresh)
    select_act = menu.addAction(phi_menu("checks"), "Select all")
    select_act.setToolTip("Enable every model for this provider")
    select_act.triggered.connect(on_select_all)
    deselect_act = menu.addAction(phi_menu("square"), "Deselect all")
    deselect_act.setToolTip("Disable every model for this provider")
    deselect_act.triggered.connect(on_deselect_all)
    menu.addSeparator()
    remove_act = menu.addAction(phi_menu("trash"), "Remove provider")
    remove_act.setToolTip("Remove this provider and all of its models")
    remove_act.triggered.connect(on_remove)

    btn = QPushButton(wrap)
    btn.setObjectName("aiProviderActionsButton")
    btn.setIcon(phi("gear"))
    btn.setToolTip("Provider actions")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(30, 28)
    btn.clicked.connect(lambda: menu.exec(btn.mapToGlobal(QPoint(0, btn.height()))))
    row.addWidget(btn)
    return wrap


def _apply_enabled_column_width(header: QHeaderView) -> None:
    """Fixed narrow column for left-aligned checkboxes (see enable delegate)."""
    header.setSectionResizeMode(ENABLED_COLUMN, QHeaderView.ResizeMode.Fixed)
    header.resizeSection(ENABLED_COLUMN, _ENABLED_COLUMN_WIDTH)


def _apply_default_column_widths(header: QHeaderView, *, column_count: int) -> None:
    _apply_enabled_column_width(header)
    for offset, width in enumerate(_DEFAULT_DATA_COLUMN_WIDTHS, start=NAME_COLUMN):
        if offset < column_count:
            header.resizeSection(offset, width)


def _apply_header_resize_modes(header: QHeaderView, *, column_count: int) -> None:
    """Enable column fixed; Name through Cost resizable; Capabilities stretches."""
    _apply_enabled_column_width(header)
    for col in range(NAME_COLUMN, min(column_count, CAPABILITIES_COLUMN)):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
    if column_count > CAPABILITIES_COLUMN:
        header.setSectionResizeMode(CAPABILITIES_COLUMN, QHeaderView.ResizeMode.Stretch)


def restore_ai_models_tree_header(header: QHeaderView, *, column_count: int) -> None:
    """Restore saved column widths from QSettings, or apply defaults."""
    settings = QSettings(_ORG, _APP)
    raw = settings.value(_HEADER_SETTINGS_KEY, QByteArray())
    restored = isinstance(raw, QByteArray) and not raw.isEmpty() and header.restoreState(raw)
    if not restored:
        _apply_default_column_widths(header, column_count=column_count)
    else:
        _apply_enabled_column_width(header)


def save_ai_models_tree_header(header: QHeaderView) -> None:
    """Persist header geometry (column widths) to QSettings."""
    settings = QSettings(_ORG, _APP)
    settings.setValue(_HEADER_SETTINGS_KEY, header.saveState())
    settings.sync()


def configure_ai_models_tree_header(tree: QTreeWidget) -> None:
    """Interactive resizable columns with debounced QSettings persistence."""
    header = tree.header()
    header.setStretchLastSection(False)
    header.setCascadingSectionResizes(False)
    header.setSectionsMovable(False)
    header.setMinimumSectionSize(24)
    count = tree.columnCount()
    restore_ai_models_tree_header(header, column_count=count)
    _apply_header_resize_modes(header, column_count=count)
    timer = QTimer(tree)
    timer.setSingleShot(True)
    timer.setInterval(_PERSIST_DEBOUNCE_MS)
    timer.timeout.connect(lambda: save_ai_models_tree_header(header))
    header.sectionResized.connect(lambda *_a: timer.start())


__all__ = [
    "CAPABILITIES_COLUMN",
    "ENABLED_COLUMN",
    "NAME_COLUMN",
    "_MODELS_LIST_BATCH_SIZE",
    "ModelsListPreviewLoader",
    "ai_provider_field_button_strip",
    "ai_provider_form_label",
    "apply_provider_edit_entries",
    "configure_ai_models_tree_header",
    "entries_from_model_specs",
    "make_ollama_default_context_combo",
    "make_provider_gear_button",
    "model_preview_line_for_spec",
    "model_preview_lines_from_entries",
    "model_preview_lines_from_specs",
    "ollama_context_tokens_from_combo",
    "provider_edit_allows_save_without_test",
    "provider_template_entry",
    "restore_ai_models_tree_header",
    "save_ai_models_tree_header",
    "validate_provider_credentials",
]
