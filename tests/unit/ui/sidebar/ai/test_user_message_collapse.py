"""Unit tests for long user prompt collapse in AI chat rows."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.sidebar.ai.message_bubble import ChatMessageBubble
from ui.sidebar.ai.message_bubble.user_message.overlay import StickyUserPromptOverlay


def _user_toggle(bubble: ChatMessageBubble) -> QPushButton | None:
    """Return the user prompt Show more/less toggle when present."""
    if bubble._user_section is None:
        return None
    return bubble._user_section.findChild(QPushButton, "aiChatUserMessageToggle")


def _sticky_label_column_bottom(overlay: StickyUserPromptOverlay) -> int:
    """Return the bottom edge of the visible sticky prompt column."""
    scroll = overlay.findChild(QScrollArea, "aiChatStickyScroll")
    host = overlay.findChild(QWidget, "aiChatStickyLabelHost")
    if scroll is not None and scroll.isVisible():
        return scroll.y() + scroll.height()
    assert host is not None
    return host.y() + host.height()


def _long_prompt() -> str:
    """Return a wrapped prompt that exceeds the collapsed preview threshold."""
    return "user prompt line\n" * 24


def test_short_user_message_has_no_toggle(qapp: QApplication, qtbot) -> None:
    """Short prompts render at full height without collapse chrome."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("user", "Hi there")
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 480)
    host.show()
    qtbot.waitExposed(host)

    assert bubble._user_section is not None
    assert not bubble._user_section.is_collapsible()
    toggle = _user_toggle(bubble)
    assert toggle is None or not toggle.isVisible()
    assert bubble.is_user_message_expanded()
    assert bubble.user_message_collapsed_cap_height() is None


def test_long_user_message_collapsed_by_default(qapp: QApplication, qtbot) -> None:
    """Long prompts start collapsed with a fade and Show more control."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("user", _long_prompt())
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 480)
    host.show()
    qtbot.waitExposed(host)

    toggle = _user_toggle(bubble)
    assert toggle is not None
    assert toggle.isVisible()
    assert toggle.text() == "Show more"
    assert toggle.width() <= toggle.sizeHint().width() + 2
    assert not bubble.is_user_message_expanded()
    assert bubble._user_section is not None
    assert bubble._user_section._fade.isVisible()
    label = bubble._user_section.label_widget()
    collapsed_h = label.height()
    toggle.click()
    qapp.processEvents()
    assert label.height() > collapsed_h


def test_user_message_toggle_emits_layout_height_changed(qapp: QApplication, qtbot) -> None:
    """Expand/collapse notifies the transcript via layout-height signals."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("user", _long_prompt())
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 480)
    host.show()
    qtbot.waitExposed(host)

    signals: list[object] = []
    bubble.layout_height_changed.connect(lambda: signals.append(object()))

    toggle = _user_toggle(bubble)
    assert toggle is not None
    toggle.click()
    qapp.processEvents()
    toggle.click()
    qapp.processEvents()

    assert len(signals) == 2


def _bubble_with_width(
    qapp: QApplication,
    qtbot,
    *,
    text: str,
    width: int = 360,
    sent_at: datetime | None = None,
) -> tuple[QWidget, ChatMessageBubble]:
    """Create a sized user bubble for sticky-metrics tests."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("user", text, sent_at=sent_at)
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(width, 800)
    host.show()
    qtbot.waitExposed(host)
    qapp.processEvents()
    return host, bubble


def test_user_message_sticky_metrics_short_prompt_with_timestamp(
    qapp: QApplication,
    qtbot,
) -> None:
    """Short prompts include label, timestamp, and frame chrome in total height."""
    _host, bubble = _bubble_with_width(
        qapp,
        qtbot,
        text="Hi there",
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
    )
    metrics = bubble.user_message_sticky_metrics(bubble_max_h=400, content_width=360)
    assert metrics.label_height >= 10
    assert metrics.chrome_height >= 10
    assert metrics.total_height == metrics.label_height + metrics.chrome_height
    assert metrics.total_height >= metrics.label_height + 10


def test_user_message_sticky_metrics_long_collapsed_prompt(
    qapp: QApplication,
    qtbot,
) -> None:
    """Collapsed long prompts cap label height to the preview line budget."""
    _host, bubble = _bubble_with_width(qapp, qtbot, text=_long_prompt())
    width = 360
    label_width = bubble._user_message_label_width(width)
    section = bubble._user_section
    assert section is not None
    collapsed_cap = section.collapsed_label_height_for_width(label_width)
    assert collapsed_cap is not None
    metrics = bubble.user_message_sticky_metrics(bubble_max_h=400, content_width=width)
    assert metrics.label_height <= collapsed_cap
    assert metrics.total_height <= 400


def test_user_message_sticky_metrics_expanded_long_prompt_respects_cap(
    qapp: QApplication,
    qtbot,
) -> None:
    """Expanded long prompts clamp total height to the provided bubble cap."""
    _host, bubble = _bubble_with_width(qapp, qtbot, text=_long_prompt())
    section = bubble._user_section
    assert section is not None
    section.set_expanded(True)
    cap = 180
    metrics = bubble.user_message_sticky_metrics(
        bubble_max_h=cap,
        content_width=360,
        force_expanded=True,
    )
    assert metrics.total_height <= cap
    assert metrics.clamped


def test_user_message_sticky_metrics_tiny_cap_never_returns_zero(
    qapp: QApplication,
    qtbot,
) -> None:
    """Tiny bubble caps still yield a positive label budget and total height."""
    _host, bubble = _bubble_with_width(
        qapp,
        qtbot,
        text=_long_prompt(),
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
    )
    metrics = bubble.user_message_sticky_metrics(bubble_max_h=30, content_width=360)
    assert metrics.label_height >= 1
    assert metrics.total_height >= 1


def test_sticky_overlay_metrics_short_prompt_with_timestamp(
    qapp: QApplication,
    qtbot,
) -> None:
    """Sticky overlay measurement includes label, timestamp, and frame chrome."""
    host = QWidget()
    qtbot.addWidget(host)
    overlay = StickyUserPromptOverlay(host)
    overlay.set_anchor_state(
        text="Hi there",
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
        collapsible=False,
    )
    metrics = overlay.measure_for_width(360, 400)
    assert metrics.label_height >= 10
    assert metrics.chrome_height >= 10
    assert metrics.total_height == metrics.label_height + metrics.chrome_height


def test_sticky_overlay_metrics_long_collapsed_prompt(
    qapp: QApplication,
    qtbot,
) -> None:
    """Collapsed long sticky overlays cap label height to the preview budget."""
    host = QWidget()
    qtbot.addWidget(host)
    overlay = StickyUserPromptOverlay(host)
    overlay.set_anchor_state(
        text=_long_prompt(),
        sent_at=None,
        collapsible=True,
    )
    width = 360
    inner_w = overlay._inner_label_width(width)
    collapsed_cap = overlay._collapsed_cap_height(inner_w)
    metrics = overlay.measure_for_width(width, 400)
    assert metrics.label_height <= collapsed_cap
    assert metrics.total_height <= 400
    assert metrics.content_height >= metrics.label_height


def test_sticky_overlay_metrics_expanded_long_prompt_respects_cap(
    qapp: QApplication,
    qtbot,
) -> None:
    """Expanded long sticky overlays clamp total height to the provided cap."""
    host = QWidget()
    qtbot.addWidget(host)
    overlay = StickyUserPromptOverlay(host)
    overlay.set_anchor_state(
        text=_long_prompt(),
        sent_at=None,
        collapsible=True,
    )
    overlay._expanded = True
    cap = 180
    metrics = overlay.measure_for_width(360, cap)
    assert metrics.total_height <= cap
    assert metrics.clamped


def test_sticky_overlay_metrics_tiny_cap_never_returns_zero(
    qapp: QApplication,
    qtbot,
) -> None:
    """Tiny sticky caps still yield positive label and total heights."""
    host = QWidget()
    qtbot.addWidget(host)
    overlay = StickyUserPromptOverlay(host)
    overlay.set_anchor_state(
        text=_long_prompt(),
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
        collapsible=True,
    )
    metrics = overlay.measure_for_width(360, 30)
    assert metrics.label_height >= 1
    assert metrics.total_height >= 1


def test_sticky_overlay_toggle_stays_below_label_after_state_resync(
    qapp: QApplication,
    qtbot,
) -> None:
    """Re-syncing anchor state must not leave Show more at the frame origin."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(360, 480)
    sent_at = datetime(2026, 6, 11, 18, 41, tzinfo=UTC)
    overlay = StickyUserPromptOverlay(host)
    overlay.set_anchor_state(
        text=_long_prompt(),
        sent_at=sent_at,
        collapsible=True,
    )
    width = 320
    metrics = overlay.measure_for_width(width, 400)
    overlay.apply_geometry(width, metrics.total_height, metrics)
    host.show()
    overlay.show()
    qtbot.waitExposed(host)
    qapp.processEvents()

    scroll_area = overlay.findChild(QScrollArea, "aiChatStickyScroll")
    label_host = overlay.findChild(QWidget, "aiChatStickyLabelHost")
    toggle = overlay.findChild(QPushButton, "aiChatUserMessageToggle")
    footer = overlay.findChild(QWidget, "aiChatUserMessageFooter")
    timestamp = overlay.findChild(QLabel, "aiChatUserMessageTime")
    assert scroll_area is not None and not scroll_area.isVisible()
    assert label_host is not None and label_host.isVisible()
    assert toggle is not None and toggle.isVisible()
    assert toggle.width() < width - 24
    assert footer is not None and footer.isVisible()
    assert timestamp is not None and timestamp.isVisible()

    overlay.set_anchor_state(
        text=_long_prompt(),
        sent_at=sent_at,
        collapsible=True,
    )
    overlay.apply_geometry(width, metrics.total_height, metrics)
    qapp.processEvents()

    label_bottom = _sticky_label_column_bottom(overlay)
    assert toggle.y() >= label_bottom - 1
    toggle_bottom = toggle.y() + toggle.height()
    assert footer.y() >= toggle_bottom - 1


def test_user_message_has_config_button(qapp: QApplication, qtbot) -> None:
    """User bubbles expose a config menu button in the footer row."""
    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("user", "Hi there")
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 200)
    host.show()
    qtbot.waitExposed(host)

    frame = bubble.findChild(QFrame, "aiChatMessageUser")
    assert frame is not None
    config = frame.findChild(QPushButton, "aiChatUserMessageConfig")
    assert config is not None
    assert config.isVisible()


def test_user_message_config_opens_actions_popover(qapp: QApplication, qtbot) -> None:
    """Clicking the config button toggles the display-only actions flyout."""
    from ui.sidebar.ai.message_bubble.user_message.actions_popup import AiUserMessageActionsPopup

    host = QWidget()
    layout = QVBoxLayout(host)
    bubble = ChatMessageBubble("user", "Hi there")
    layout.addWidget(bubble)
    qtbot.addWidget(host)
    host.resize(360, 200)
    host.show()
    qtbot.waitExposed(host)

    frame = bubble.findChild(QFrame, "aiChatMessageUser")
    assert frame is not None
    config = frame.findChild(QPushButton, "aiChatUserMessageConfig")
    assert config is not None
    popup = AiUserMessageActionsPopup.instance()

    qtbot.mouseClick(config, Qt.MouseButton.LeftButton)
    assert popup.isVisible()
    labels = popup.findChildren(QLabel, "aiUserMessageActionLabel")
    assert {label.text() for label in labels} == {"Copy message", "Fork chat"}
    rows = popup.findChildren(QWidget, "aiUserMessageActionRow")
    assert len(rows) == 2
    assert all(row.cursor().shape() == Qt.CursorShape.PointingHandCursor for row in rows)

    qtbot.mouseClick(config, Qt.MouseButton.LeftButton)
    assert not popup.isVisible()


def test_sticky_overlay_has_config_button(qapp: QApplication, qtbot) -> None:
    """Sticky user prompt overlay mirrors the config footer button."""
    host = QWidget()
    qtbot.addWidget(host)
    overlay = StickyUserPromptOverlay(host)
    overlay.set_anchor_state(
        text="Sticky prompt",
        sent_at=datetime(2026, 6, 11, 18, 41, tzinfo=UTC),
        collapsible=False,
    )
    config = overlay.findChild(QPushButton, "aiChatUserMessageConfig")
    assert config is not None
