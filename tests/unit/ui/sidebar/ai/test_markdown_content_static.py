"""Unit tests for static MarkdownContent painting and interaction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication, QTextBrowser

from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.styling.theme import current_palette


def test_finalized_body_is_qwidget_not_qtextbrowser(qapp: QApplication, qtbot) -> None:
    """Finalized assistant bodies use MarkdownContent, not QTextBrowser."""
    body = MarkdownContent("**Hello**")
    qtbot.addWidget(body)
    assert isinstance(body, MarkdownContent)
    assert not isinstance(body, QTextBrowser)


def test_link_click_opens_external_url(qapp: QApplication, qtbot) -> None:
    """Clicking a document anchor opens the URL externally."""
    body = MarkdownContent("[Example](https://example.com/test)")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    opened: list[QUrl] = []

    def _open_url(url: QUrl) -> bool:
        opened.append(url)
        return True

    local = QPointF(12, 8)
    with (
        patch.object(
            body._document.documentLayout(),
            "anchorAt",
            return_value="https://example.com/test",
        ),
        patch(
            "ui.sidebar.ai.message_bubble.markdown_content.QDesktopServices.openUrl",
            side_effect=_open_url,
        ),
    ):
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            local,
            local,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        body.mouseReleaseEvent(event)

    assert len(opened) == 1
    assert opened[0].toString() == "https://example.com/test"


def test_context_menu_copy_message_puts_markdown_on_clipboard(qapp: QApplication, qtbot) -> None:
    """Copy message places the markdown source on the clipboard."""
    source = "**Hello** world\n\n```python\nprint(1)\n```"
    body = MarkdownContent(source)
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    with patch.object(body, "mapToGlobal", return_value=body.pos()):
        menu = MagicMock()
        copy_action = MagicMock()
        menu.addAction.return_value = copy_action
        menu.exec.return_value = copy_action
        with patch(
            "ui.sidebar.ai.message_bubble.markdown_content.QMenu",
            return_value=menu,
        ):
            body._show_context_menu(body.rect().center())

    assert QApplication.clipboard().text() == source


def test_text_selection_and_copy_shortcut(qapp: QApplication, qtbot) -> None:
    """Assistant markdown supports drag selection and Ctrl+C."""
    body = MarkdownContent("Hello selectable world")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    body._selection_anchor = 0
    body._selection_cursor = 5
    assert body._selected_text() == "Hello"

    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier,
    )
    body.keyPressEvent(event)
    assert QApplication.clipboard().text() == "Hello"


def test_wheel_forwards_to_ancestor_scroll_area(
    qapp: QApplication, qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wheel events on the static body forward to the transcript scroll area."""
    body = MarkdownContent("line\n" * 20)
    qtbot.addWidget(body)
    body.resize(300, 80)
    body.show()
    qtbot.waitExposed(body)

    forwarded: list[bool] = []

    def _fake_forward(widget, event) -> bool:
        forwarded.append(True)
        return True

    monkeypatch.setattr(
        "ui.sidebar.ai.message_bubble.markdown_content.forward_wheel_to_ancestor_scroll_area",
        _fake_forward,
    )
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent

    local = body.rect().center()
    global_pos = body.mapToGlobal(QPointF(local))
    wheel = QWheelEvent(
        QPointF(local),
        global_pos,
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    assert QApplication.sendEvent(body, wheel)
    assert forwarded == [True]


def test_fenced_code_block_paint_strokes_full_border(qapp: QApplication, qtbot) -> None:
    """Fenced-code tables get a painted 1px frame on all four sides."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    image = QImage(body.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    body.render(image)

    border = QColor(current_palette()["border"])
    width = image.width()
    height = image.height()
    border_pixels = [
        (x, y) for y in range(height) for x in range(width) if QColor(image.pixel(x, y)) == border
    ]
    assert border_pixels, "expected painted border strokes"
    xs = [x for x, _ in border_pixels]
    ys = [y for _, y in border_pixels]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    assert right - left > 50
    assert bottom - top > 20
    assert QColor(image.pixel(left, top)) == border
    assert QColor(image.pixel(right, top)) == border
    assert QColor(image.pixel(left, bottom)) == border


def _border_x_clusters_on_row(image: QImage, y: int, border: QColor) -> list[list[int]]:
    """Group contiguous border-coloured x positions on row *y* into clusters."""
    xs = [x for x in range(image.width()) if QColor(image.pixel(x, y)) == border]
    if not xs:
        return []
    clusters: list[list[int]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > 2:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    return clusters


def test_fenced_code_block_no_inner_border_rectangle(qapp: QApplication, qtbot) -> None:
    """Code area should not paint a second inset border inside the outer frame."""
    body = MarkdownContent("```python\n" + "x = 1\n" * 8 + "```")
    qtbot.addWidget(body)
    body.resize(360, 280)
    body.show()
    qtbot.waitExposed(body)

    image = QImage(body.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    body.render(image)

    border = QColor(current_palette()["border"])
    border_pixels = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if QColor(image.pixel(x, y)) == border
    ]
    assert border_pixels, "expected painted border strokes"
    ys = [y for _, y in border_pixels]
    top, bottom = min(ys), max(ys)
    scan_y = top + (bottom - top) // 2
    clusters = _border_x_clusters_on_row(image, scan_y, border)
    assert len(clusters) == 2, (
        f"expected outer left/right border only on scan line, got {len(clusters)} clusters"
    )
