"""Settings dialog — History category page."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from database.data_paths import postmark_user_data_dir, project_root
from ui.styling.history_settings_manager import (
    DEFAULT_MAX_ITEMS_PER_DAY,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_RETENTION_DAYS,
    MAX_MAX_ITEMS_PER_DAY,
    MAX_MAX_RESPONSE_BYTES,
    MAX_RETENTION_DAYS,
    MIN_MAX_ITEMS_PER_DAY,
    MIN_RETENTION_DAYS,
    HistorySettingsManager,
)


@dataclass
class HistoryPageWidgets:
    """Widgets on the History settings page."""

    retention_days_spin: QSpinBox
    max_items_spin: QSpinBox
    unlimited_check: QCheckBox
    save_responses_check: QCheckBox
    max_mib_spin: QSpinBox
    storage_path_label: QLabel


def build_history_page(
    history_settings: HistorySettingsManager,
) -> tuple[QWidget, HistoryPageWidgets]:
    """Build the History detail page and return it with widget handles."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    heading = QLabel("History")
    heading.setObjectName("titleLabel")
    layout.addWidget(heading)

    storage_path_label = QLabel(f"Files are stored under:\n{postmark_user_data_dir() / 'history'}")
    storage_path_label.setObjectName("mutedLabel")
    storage_path_label.setWordWrap(True)
    layout.addWidget(storage_path_label)

    db_path = project_root() / "data" / "database" / "main.db"
    privacy = QLabel(
        f"Request metadata (headers, method, URL) is stored in the project database:\n"
        f"{db_path}\n\n"
        "Response bodies and request snapshots (including auth) are saved as "
        "plaintext files under the user-data path above. Worst-case disk use is "
        "roughly retention days x max items per day x max response size."
    )
    privacy.setObjectName("mutedLabel")
    privacy.setWordWrap(True)
    layout.addWidget(privacy)

    retention_row = QHBoxLayout()
    retention_row.addWidget(QLabel("Keep history for (days):"))
    retention_days_spin = QSpinBox()
    retention_days_spin.setRange(MIN_RETENTION_DAYS, MAX_RETENTION_DAYS)
    retention_days_spin.setValue(history_settings.retention_days)
    retention_row.addWidget(retention_days_spin)
    retention_row.addStretch()
    layout.addLayout(retention_row)

    unlimited_check = QCheckBox("Unlimited entries per day")
    unlimited_check.setChecked(history_settings.unlimited_per_day)
    layout.addWidget(unlimited_check)

    max_row = QHBoxLayout()
    max_row.addWidget(QLabel("Max entries per day:"))
    max_items_spin = QSpinBox()
    max_items_spin.setRange(MIN_MAX_ITEMS_PER_DAY, MAX_MAX_ITEMS_PER_DAY)
    max_items_spin.setValue(history_settings.max_items_per_day)
    max_items_spin.setEnabled(not history_settings.unlimited_per_day)
    max_row.addWidget(max_items_spin)
    max_row.addStretch()
    layout.addLayout(max_row)

    save_responses_check = QCheckBox("Save response bodies")
    save_responses_check.setChecked(history_settings.save_responses)
    layout.addWidget(save_responses_check)

    mib_row = QHBoxLayout()
    mib_row.addWidget(QLabel("Max response body size (MiB):"))
    max_mib_spin = QSpinBox()
    max_mib_spin.setRange(1, MAX_MAX_RESPONSE_BYTES // (1024 * 1024))
    max_mib_spin.setValue(max(1, history_settings.max_response_bytes // (1024 * 1024)))
    mib_row.addWidget(max_mib_spin)
    mib_row.addStretch()
    layout.addLayout(mib_row)

    layout.addStretch()

    widgets = HistoryPageWidgets(
        retention_days_spin=retention_days_spin,
        max_items_spin=max_items_spin,
        unlimited_check=unlimited_check,
        save_responses_check=save_responses_check,
        max_mib_spin=max_mib_spin,
        storage_path_label=storage_path_label,
    )
    return page, widgets


def apply_history_page(
    history_settings: HistorySettingsManager,
    widgets: HistoryPageWidgets,
) -> None:
    """Persist widget values into *history_settings*."""
    history_settings.retention_days = widgets.retention_days_spin.value()
    history_settings.unlimited_per_day = widgets.unlimited_check.isChecked()
    history_settings.max_items_per_day = widgets.max_items_spin.value()
    history_settings.save_responses = widgets.save_responses_check.isChecked()
    mib = widgets.max_mib_spin.value()
    history_settings.max_response_bytes = mib * 1024 * 1024


def load_history_page_defaults(widgets: HistoryPageWidgets) -> None:
    """Reset widgets to built-in defaults (for tests)."""
    widgets.retention_days_spin.setValue(DEFAULT_RETENTION_DAYS)
    widgets.max_items_spin.setValue(DEFAULT_MAX_ITEMS_PER_DAY)
    widgets.unlimited_check.setChecked(False)
    widgets.max_items_spin.setEnabled(True)
    widgets.save_responses_check.setChecked(True)
    widgets.max_mib_spin.setValue(DEFAULT_MAX_RESPONSE_BYTES // (1024 * 1024))
