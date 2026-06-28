"""Sticky overlay hosting for inline message edit on :class:`AiChatPanel`."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.sidebar.ai import AiChatPanel
from ui.sidebar.ai.chat_panel.composer import AiChatComposer
from ui.sidebar.ai.message_bubble.user_message.overlay import StickyUserPromptOverlay


def _sticky_overlay(panel: AiChatPanel) -> StickyUserPromptOverlay | None:
    """Return the sticky overlay on the transcript viewport, if any."""
    viewport = panel._scroll.viewport()
    for child in viewport.children():
        if isinstance(child, StickyUserPromptOverlay):
            return child
    return None


def _scroll_until_sticky_hosts_composer(
    panel: AiChatPanel,
    qapp: QApplication,
) -> StickyUserPromptOverlay:
    """Scroll down until the sticky overlay hosts the inline edit composer."""
    bar = panel._scroll.verticalScrollBar()
    for _ in range(400):
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_overlay(panel)
        if sticky is not None and sticky.isVisible() and sticky.hosts_inline_composer():
            return sticky
        if bar.value() >= bar.maximum():
            break
        bar.setValue(min(bar.maximum(), bar.value() + 28))
        qapp.processEvents()
    sticky = _sticky_overlay(panel)
    assert sticky is not None, "sticky overlay was never created"
    assert sticky.isVisible(), "sticky overlay stayed hidden"
    assert sticky.hosts_inline_composer(), "sticky overlay did not host composer"
    return sticky


def _scroll_until_composer_in_bubble(
    panel: AiChatPanel,
    qapp: QApplication,
) -> None:
    """Scroll up until the inline composer is reattached to the transcript bubble."""
    state = panel._inline_edit
    assert state is not None
    bubble = state.bubble
    bar = panel._scroll.verticalScrollBar()
    for _ in range(400):
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_overlay(panel)
        if bubble._inline_composer is not None and (
            sticky is None or not sticky.isVisible() or not sticky.hosts_inline_composer()
        ):
            return
        bar.setValue(max(0, bar.value() - 28))
        qapp.processEvents()
    assert bubble._inline_composer is not None, "composer was not reattached to bubble"


def _inline_composer_count(panel: AiChatPanel) -> int:
    """Count inline composers (everything except the docked panel composer)."""
    return sum(
        1
        for composer in panel.findChildren(AiChatComposer)
        if composer is not panel._docked_composer
    )


def _scroll_until_sticky_shows_prompt(
    panel: AiChatPanel,
    qapp: QApplication,
    *,
    prompt: str,
) -> tuple[StickyUserPromptOverlay, int]:
    """Scroll down until the sticky overlay shows *prompt*; return sticky and scroll value."""
    bar = panel._scroll.verticalScrollBar()
    for _ in range(400):
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_overlay(panel)
        if sticky is not None and sticky.isVisible() and sticky.text() == prompt:
            return sticky, bar.value()
        if bar.value() >= bar.maximum():
            break
        bar.setValue(min(bar.maximum(), bar.value() + 28))
        qapp.processEvents()
    sticky = _sticky_overlay(panel)
    assert sticky is not None, "sticky overlay was never created"
    assert sticky.isVisible(), "sticky overlay stayed hidden"
    assert sticky.text() == prompt
    return sticky, bar.value()


def test_edit_from_sticky_opens_composer_in_place(qapp: QApplication, qtbot) -> None:
    """Edit on the sticky clone opens the composer in sticky without scrolling."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 280)
    panel.show()
    qtbot.waitExposed(panel)
    prompt = "sticky edit me"
    user_bubble = panel.add_message("user", prompt, message_id=10)
    panel.add_message("assistant", "reply\n" * 50, message_id=11)
    panel._scroll_to_bottom(force=True)
    qtbot.wait(50)
    sticky, scroll_before = _scroll_until_sticky_shows_prompt(panel, qapp, prompt=prompt)
    panel._edit_sticky_prompt(user_bubble)
    qtbot.wait(50)
    state = panel._inline_edit
    assert state is not None
    assert sticky.hosts_inline_composer()
    assert state.composer.parent() is sticky._frame
    assert abs(panel._scroll.verticalScrollBar().value() - scroll_before) <= 2
    assert _inline_composer_count(panel) == 1
    panel.end_inline_edit(restore_bubble=True)


def test_inline_edit_allows_readonly_sticky_for_earlier_turn_when_scrolled_up(
    qapp: QApplication, qtbot
) -> None:
    """While editing a later turn, scrolling up still pins earlier user prompts."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 280)
    panel.show()
    qtbot.waitExposed(panel)
    first_prompt = "first user turn"
    second_prompt = "second user turn edit me"
    panel.add_message("user", first_prompt, message_id=1)
    panel.add_message("assistant", "a1\n" * 40, message_id=2)
    second_bubble = panel.add_message("user", second_prompt, message_id=3)
    panel.add_message("assistant", "a2\n" * 50, message_id=4)
    panel._scroll_to_bottom(force=True)
    qtbot.wait(50)
    _scroll_until_sticky_shows_prompt(panel, qapp, prompt=second_prompt)
    panel._edit_sticky_prompt(second_bubble)
    qtbot.wait(50)
    assert panel._inline_edit is not None

    # The earlier-turn read-only sticky is only selectable in a narrow scroll
    # window (first user row above the viewport top while the edited turn's user
    # row is not yet visible). Under offscreen Qt the transcript geometry is
    # compressed, so step in small increments to avoid jumping over that window.
    bar = panel._scroll.verticalScrollBar()
    found = False
    for _ in range(400):
        panel._sync_sticky_turn_prompt()
        sticky = _sticky_overlay(panel)
        if (
            sticky is not None
            and sticky.isVisible()
            and sticky.text() == first_prompt
            and not sticky.hosts_inline_composer()
        ):
            found = True
            break
        if bar.value() <= 0:
            break
        bar.setValue(max(0, bar.value() - 8))
        qapp.processEvents()
    assert found, "read-only sticky for the earlier turn never appeared"
    panel.end_inline_edit(restore_bubble=True)


def test_inline_edit_reparents_composer_into_sticky_when_scrolled(
    qapp: QApplication, qtbot
) -> None:
    """Scrolling past the edited user bubble hosts the live composer in sticky."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 280)
    panel.show()
    qtbot.waitExposed(panel)
    panel.add_message("user", "edit me while reading a long reply", message_id=1)
    panel.add_message("assistant", "reply\n" * 50, message_id=2)
    panel._scroll_to_bottom(force=True)
    qtbot.wait(50)
    assert panel.begin_inline_edit(1) is True
    state = panel._inline_edit
    assert state is not None
    sticky = _scroll_until_sticky_hosts_composer(panel, qapp)
    assert state.composer.parent() is sticky._frame
    assert _inline_composer_count(panel) == 1
    panel.end_inline_edit(restore_bubble=True)


def test_inline_edit_scroll_back_reattaches_composer_to_bubble(qapp: QApplication, qtbot) -> None:
    """Scrolling back to the edited bubble moves the composer out of sticky."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 280)
    panel.show()
    qtbot.waitExposed(panel)
    panel.add_message("user", "edit target prompt", message_id=3)
    panel.add_message("assistant", "long answer\n" * 50, message_id=4)
    panel._scroll_to_bottom(force=True)
    qtbot.wait(50)
    assert panel.begin_inline_edit(3) is True
    state = panel._inline_edit
    assert state is not None
    _scroll_until_sticky_hosts_composer(panel, qapp)
    _scroll_until_composer_in_bubble(panel, qapp)
    assert state.bubble._inline_composer is state.composer
    sticky = _sticky_overlay(panel)
    assert sticky is None or not sticky.isVisible() or not sticky.hosts_inline_composer()
    panel.end_inline_edit(restore_bubble=True)


def test_cancel_from_sticky_hosted_composer_ends_edit(qapp: QApplication, qtbot) -> None:
    """Cancel on a sticky-hosted inline composer tears down edit cleanly."""
    panel = AiChatPanel()
    qtbot.addWidget(panel)
    panel.resize(400, 280)
    panel.show()
    qtbot.waitExposed(panel)
    bubble = panel.add_message("user", "cancel from sticky", message_id=5)
    panel.add_message("assistant", "tail\n" * 50, message_id=6)
    panel._scroll_to_bottom(force=True)
    qtbot.wait(50)
    assert panel.begin_inline_edit(5) is True
    _scroll_until_sticky_hosts_composer(panel, qapp)
    state = panel._inline_edit
    assert state is not None
    state.composer.cancel_requested.emit()
    qapp.processEvents()
    assert panel._inline_edit is None
    assert bubble.user_message_text() == "cancel from sticky"
    assert _inline_composer_count(panel) == 0
