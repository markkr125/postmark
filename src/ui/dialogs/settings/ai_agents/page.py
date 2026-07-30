"""Settings dialog — AI Agents page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services.ai.chat.chat_run_limits import (
    MAX_MAX_CONCURRENT_CHAT_RUNS,
    MIN_MAX_CONCURRENT_CHAT_RUNS,
    max_concurrent_chat_runs,
    set_max_concurrent_chat_runs,
)
from services.ai.chat.mutation.auto_approve import (
    CATALOG,
    add_rule,
    clear_rules,
    kind_label,
    list_rules,
    remove_rule,
)
from services.ai.chat.subagent_limits import (
    MAX_MAX_PARALLEL_SUBAGENTS,
    MIN_MAX_PARALLEL_SUBAGENTS,
    max_parallel_subagents,
    set_max_parallel_subagents,
)
from services.ai.chat.tools.collection_draft.config import (
    draft_script_language,
    set_draft_script_language,
)


@dataclass
class AiAgentsPageWidgets:
    """Widgets on the Agents settings page."""

    max_concurrent_spin: QSpinBox
    max_parallel_subagents_spin: QSpinBox
    draft_script_language_combo: QComboBox
    auto_approve_list: QListWidget
    auto_approve_add: QPushButton
    auto_approve_remove: QPushButton
    auto_approve_remove_all: QPushButton


class AiAgentsPageController:
    """Owns agent behaviour settings and persistence."""

    def __init__(self, widgets: AiAgentsPageWidgets, on_changed: Callable[[], None]) -> None:
        """Wire widgets and load persisted values."""
        self._widgets = widgets
        self._on_changed = on_changed
        widgets.max_concurrent_spin.valueChanged.connect(on_changed)
        widgets.max_parallel_subagents_spin.valueChanged.connect(on_changed)
        widgets.draft_script_language_combo.currentIndexChanged.connect(on_changed)
        widgets.auto_approve_add.clicked.connect(self._on_add_rule)
        widgets.auto_approve_remove.clicked.connect(self._on_remove_selected)
        widgets.auto_approve_remove_all.clicked.connect(self._on_remove_all)
        widgets.auto_approve_list.itemSelectionChanged.connect(self._sync_remove_enabled)
        self.reload()

    def reload(self) -> None:
        """Refresh widgets from QSettings."""
        spin = self._widgets.max_concurrent_spin
        spin.blockSignals(True)
        spin.setValue(max_concurrent_chat_runs())
        spin.blockSignals(False)
        parallel = self._widgets.max_parallel_subagents_spin
        parallel.blockSignals(True)
        parallel.setValue(max_parallel_subagents())
        parallel.blockSignals(False)
        combo = self._widgets.draft_script_language_combo
        combo.blockSignals(True)
        code = draft_script_language()
        index = combo.findData(code)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)
        self._reload_auto_approve_list()

    def apply(self) -> None:
        """Persist current widget state."""
        set_max_concurrent_chat_runs(self._widgets.max_concurrent_spin.value())
        set_max_parallel_subagents(self._widgets.max_parallel_subagents_spin.value())
        language = self._widgets.draft_script_language_combo.currentData()
        if isinstance(language, str) and language:
            set_draft_script_language(language)
        # Auto-approve rules are written immediately on Add/Remove.

    def _reload_auto_approve_list(self) -> None:
        """Populate the auto-approve list from persisted rules."""
        lst = self._widgets.auto_approve_list
        lst.blockSignals(True)
        lst.clear()
        for kind in list_rules():
            item = QListWidgetItem(kind_label(kind))
            item.setData(Qt.ItemDataRole.UserRole, kind)
            lst.addItem(item)
        lst.blockSignals(False)
        self._sync_remove_enabled()

    def _sync_remove_enabled(self) -> None:
        """Enable Remove when a row is selected; Remove all when any rules exist."""
        has_selection = self._widgets.auto_approve_list.currentItem() is not None
        self._widgets.auto_approve_remove.setEnabled(has_selection)
        has_any = self._widgets.auto_approve_list.count() > 0
        self._widgets.auto_approve_remove_all.setEnabled(has_any)

    def _on_add_rule(self) -> None:
        """Offer catalog kinds not already listed and persist the choice."""
        existing = set(list_rules())
        choices = sorted(
            ((label, kind) for kind, label in CATALOG.items() if kind not in existing),
            key=lambda pair: pair[0].lower(),
        )
        if not choices:
            return
        labels = [label for label, _kind in choices]
        picked, ok = QInputDialog.getItem(
            self._widgets.auto_approve_list,
            "Auto-approve action",
            "Action kind to auto-approve:",
            labels,
            0,
            False,
        )
        if not ok or not picked:
            return
        kind = next(k for label, k in choices if label == picked)
        if add_rule(kind):
            self._reload_auto_approve_list()
            self._on_changed()

    def _on_remove_selected(self) -> None:
        """Remove the selected auto-approve rule."""
        item = self._widgets.auto_approve_list.currentItem()
        if item is None:
            return
        kind = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(kind, str) and kind:
            remove_rule(kind)
            self._reload_auto_approve_list()
            self._on_changed()

    def _on_remove_all(self) -> None:
        """Clear the entire auto-approve whitelist."""
        clear_rules()
        self._reload_auto_approve_list()
        self._on_changed()


def build_ai_agents_page(
    on_changed: Callable[[], None],
) -> tuple[QWidget, AiAgentsPageController]:
    """Build the Agents detail page and return it with a controller."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)

    heading = QLabel("Agents")
    heading.setObjectName("titleLabel")
    layout.addWidget(heading)

    intro = QLabel(
        "Control how Postmark runs AI chat agents in parallel. Background runs "
        "continue when you switch sessions or start a new chat. In Agent mode, "
        "workspace edits and sends are always available — risky kinds pause for "
        "Approve unless listed under auto-approve below."
    )
    intro.setObjectName("mutedLabel")
    intro.setWordWrap(True)
    layout.addWidget(intro)

    concurrent_row = QHBoxLayout()
    concurrent_label = QLabel("Advisory concurrent chat runs:")
    concurrent_label.setObjectName("aiAgentsConcurrentRunsLabel")
    concurrent_row.addWidget(concurrent_label)
    concurrent_spin = QSpinBox()
    concurrent_spin.setObjectName("aiAgentsConcurrentRunsSpin")
    concurrent_spin.setRange(MIN_MAX_CONCURRENT_CHAT_RUNS, MAX_MAX_CONCURRENT_CHAT_RUNS)
    concurrent_spin.setToolTip(
        "When this many chats are already running, Postmark shows a warning "
        "before starting another. Sends are not blocked."
    )
    concurrent_row.addWidget(concurrent_spin)
    concurrent_row.addStretch()
    layout.addLayout(concurrent_row)

    concurrent_help = QLabel(
        "The limit is advisory only — you can still run more agents if needed. "
        "Adjust this when you routinely run many parallel sessions."
    )
    concurrent_help.setObjectName("mutedLabel")
    concurrent_help.setWordWrap(True)
    layout.addWidget(concurrent_help)

    parallel_row = QHBoxLayout()
    parallel_label = QLabel("Max parallel subagents per turn:")
    parallel_label.setObjectName("aiAgentsMaxParallelSubagentsLabel")
    parallel_row.addWidget(parallel_label)
    parallel_spin = QSpinBox()
    parallel_spin.setObjectName("aiAgentsMaxParallelSubagentsSpin")
    parallel_spin.setRange(MIN_MAX_PARALLEL_SUBAGENTS, MAX_MAX_PARALLEL_SUBAGENTS)
    parallel_spin.setToolTip(
        "Hard cap on delegate fan-out within one assistant turn. "
        "Sequential task tool runs are not affected."
    )
    parallel_row.addWidget(parallel_spin)
    parallel_row.addStretch()
    layout.addLayout(parallel_row)

    parallel_help = QLabel(
        "Applies to parallel delegate subagents in a single turn. "
        "The task tool still runs one subagent at a time."
    )
    parallel_help.setObjectName("mutedLabel")
    parallel_help.setWordWrap(True)
    layout.addWidget(parallel_help)

    language_row = QHBoxLayout()
    language_label = QLabel("Draft import script language:")
    language_label.setObjectName("aiAgentsDraftScriptLanguageLabel")
    language_row.addWidget(language_label)
    language_combo = QComboBox()
    language_combo.setObjectName("aiAgentsDraftScriptLanguageCombo")
    language_combo.addItem("Python", "python")
    language_combo.addItem("JavaScript", "javascript")
    language_combo.addItem("TypeScript", "typescript")
    language_combo.setToolTip(
        "Language used for pre-request and post-response scripts the AI generates "
        "when importing a document into a collection."
    )
    language_row.addWidget(language_combo)
    language_row.addStretch()
    layout.addLayout(language_row)

    language_help = QLabel(
        "Applies to scripts generated during PDF/DOCX (and similar) collection "
        "drafts. Defaults to Python. Change only if you prefer JavaScript or "
        "TypeScript for those scripts."
    )
    language_help.setObjectName("mutedLabel")
    language_help.setWordWrap(True)
    layout.addWidget(language_help)

    auto_heading = QLabel("Auto-approved Agent actions")
    auto_heading.setObjectName("sectionLabel")
    layout.addWidget(auto_heading)

    auto_help = QLabel(
        "In Agent mode, write/send actions pause for Approve unless listed here. "
        "An empty list means ask every time."
    )
    auto_help.setObjectName("mutedLabel")
    auto_help.setWordWrap(True)
    layout.addWidget(auto_help)

    auto_list = QListWidget()
    auto_list.setObjectName("aiAgentsAutoApproveList")
    auto_list.setMinimumHeight(120)
    layout.addWidget(auto_list)

    auto_btns = QHBoxLayout()
    add_btn = QPushButton("Add…")
    add_btn.setObjectName("aiAgentsAutoApproveAdd")
    add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    remove_btn = QPushButton("Remove")
    remove_btn.setObjectName("aiAgentsAutoApproveRemove")
    remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    remove_btn.setEnabled(False)
    remove_all_btn = QPushButton("Remove all")
    remove_all_btn.setObjectName("aiAgentsAutoApproveRemoveAll")
    remove_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    remove_all_btn.setEnabled(False)
    auto_btns.addWidget(add_btn)
    auto_btns.addWidget(remove_btn)
    auto_btns.addWidget(remove_all_btn)
    auto_btns.addStretch()
    layout.addLayout(auto_btns)

    layout.addStretch()

    widgets = AiAgentsPageWidgets(
        max_concurrent_spin=concurrent_spin,
        max_parallel_subagents_spin=parallel_spin,
        draft_script_language_combo=language_combo,
        auto_approve_list=auto_list,
        auto_approve_add=add_btn,
        auto_approve_remove=remove_btn,
        auto_approve_remove_all=remove_all_btn,
    )
    controller = AiAgentsPageController(widgets, on_changed)
    return page, controller


__all__ = ["AiAgentsPageController", "AiAgentsPageWidgets", "build_ai_agents_page"]
