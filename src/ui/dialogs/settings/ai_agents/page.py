"""Settings dialog — AI Agents page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from services.ai.chat.chat_run_limits import (
    MAX_MAX_CONCURRENT_CHAT_RUNS,
    MIN_MAX_CONCURRENT_CHAT_RUNS,
    max_concurrent_chat_runs,
    set_max_concurrent_chat_runs,
)
from services.ai.chat.subagent_limits import (
    MAX_MAX_PARALLEL_SUBAGENTS,
    MIN_MAX_PARALLEL_SUBAGENTS,
    max_parallel_subagents,
    set_max_parallel_subagents,
)


@dataclass
class AiAgentsPageWidgets:
    """Widgets on the Agents settings page."""

    max_concurrent_spin: QSpinBox
    max_parallel_subagents_spin: QSpinBox


class AiAgentsPageController:
    """Owns agent behaviour settings and persistence."""

    def __init__(self, widgets: AiAgentsPageWidgets, on_changed: Callable[[], None]) -> None:
        """Wire widgets and load persisted values."""
        self._widgets = widgets
        self._on_changed = on_changed
        widgets.max_concurrent_spin.valueChanged.connect(on_changed)
        widgets.max_parallel_subagents_spin.valueChanged.connect(on_changed)
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

    def apply(self) -> None:
        """Persist current widget state."""
        set_max_concurrent_chat_runs(self._widgets.max_concurrent_spin.value())
        set_max_parallel_subagents(self._widgets.max_parallel_subagents_spin.value())


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
        "continue when you switch sessions or start a new chat."
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

    layout.addStretch()

    widgets = AiAgentsPageWidgets(
        max_concurrent_spin=concurrent_spin,
        max_parallel_subagents_spin=parallel_spin,
    )
    controller = AiAgentsPageController(widgets, on_changed)
    return page, controller


__all__ = ["AiAgentsPageController", "AiAgentsPageWidgets", "build_ai_agents_page"]
