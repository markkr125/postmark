"""Unit tests for static MarkdownContent painting and interaction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QEnterEvent, QImage, QMouseEvent, QTextCursor
from PySide6.QtWidgets import QApplication, QTextBrowser

from ui.sidebar.ai.markdown.highlight_code import COPY_LINK_FONT_PX, copy_anchor_spans
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


def test_code_block_copy_link_puts_source_on_clipboard(qapp: QApplication, qtbot) -> None:
    """Clicking a fenced-code Copy link places the raw block source on the clipboard."""
    source = "```python\nprint(1)\n```"
    body = MarkdownContent(source)
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    local = QPointF(300, 24)
    with patch.object(
        body._document.documentLayout(),
        "anchorAt",
        return_value="postmark-code-copy:0",
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

    assert QApplication.clipboard().text() == "print(1)"


def test_code_block_copy_link_shows_copied_feedback(qapp: QApplication, qtbot) -> None:
    """After copying, the painted chrome switches to Copied briefly."""
    source = "```python\nprint(1)\n```"
    body = MarkdownContent(source)
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    local = QPointF(300, 24)
    with patch.object(
        body._document.documentLayout(),
        "anchorAt",
        return_value="postmark-code-copy:0",
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

    assert body._copy_confirmed_index == 0
    start, _end = copy_anchor_spans(body._document)[0]
    cursor = QTextCursor(body._document)
    cursor.setPosition(start)
    cursor.setPosition(start + len("Copied"), QTextCursor.MoveMode.KeepAnchor)
    assert cursor.selectedText() == "Copied"
    assert cursor.charFormat().font().pixelSize() == COPY_LINK_FONT_PX
    qtbot.waitUntil(lambda: body._copy_confirmed_index is None, timeout=3000)


def _copy_link_hover_point(body: MarkdownContent) -> QPointF | None:
    """Return a widget-local point over the first fenced-code Copy anchor."""
    layout = body._document.documentLayout()
    size = layout.documentSize()
    for y in range(0, int(size.height()) + 1):
        for x in range(int(size.width()) - 1, -1, -1):
            if layout.anchorAt(QPointF(x, y)) == "postmark-code-copy:0":
                return QPointF(x, y)
    return None


def test_markdown_content_enables_mouse_tracking(qapp: QApplication, qtbot) -> None:
    """Copy-link hover requires mouse tracking on the markdown body."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    assert body.hasMouseTracking()


def test_markdown_content_default_cursor_is_ibeam(qapp: QApplication, qtbot) -> None:
    """Assistant markdown bodies default to a text-selection cursor."""
    body = MarkdownContent("Plain assistant answer text.")
    qtbot.addWidget(body)
    assert body.cursor().shape() == Qt.CursorShape.IBeamCursor


def test_plain_text_hover_uses_ibeam_cursor(qapp: QApplication, qtbot) -> None:
    """Hovering prose keeps the text cursor."""
    body = MarkdownContent("Plain assistant answer text.")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    local = QPointF(body.width() / 2, body.height() / 2)
    with patch.object(body._document.documentLayout(), "anchorAt", return_value=""):
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            local,
            local,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        body.mouseMoveEvent(move)

    assert body.cursor().shape() == Qt.CursorShape.IBeamCursor


def test_markdown_link_hover_uses_pointing_hand_cursor(qapp: QApplication, qtbot) -> None:
    """Hovering a markdown link shows a pointing-hand cursor."""
    body = MarkdownContent("[Example](https://example.com/test)")
    qtbot.addWidget(body)
    body.resize(360, 120)
    body.show()
    qtbot.waitExposed(body)

    local = QPointF(24, 12)
    with patch.object(
        body._document.documentLayout(),
        "anchorAt",
        return_value="https://example.com/test",
    ):
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            local,
            local,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        body.mouseMoveEvent(move)

    assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_copy_link_hover_sets_pointing_hand_cursor(qapp: QApplication, qtbot) -> None:
    """Hovering a Copy link shows a pointing-hand cursor."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    hover_point = _copy_link_hover_point(body)
    assert hover_point is not None

    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        hover_point,
        hover_point,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    body.mouseMoveEvent(move)

    assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert body._copy_hover_index == 0


def test_copy_link_cursor_stable_after_repaint(qapp: QApplication, qtbot) -> None:
    """Copy hover keeps a pointing-hand cursor after a repaint."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    hover_point = _copy_link_hover_point(body)
    assert hover_point is not None

    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        hover_point,
        hover_point,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    body.mouseMoveEvent(move)
    assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor

    body.update()
    body._update_copy_hover(hover_point)

    assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert body._copy_hover_index == 0

    for _ in range(6):
        body.mouseMoveEvent(move)
        assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_copy_hover_on_first_body_does_not_affect_second(qapp: QApplication, qtbot) -> None:
    """Hover chrome is per MarkdownContent; HTML stays static across assistant turns."""
    source = "```python\nprint(1)\n```"
    body1 = MarkdownContent(f"First answer\n\n{source}")
    body2 = MarkdownContent(f"Second answer\n\n{source}")
    qtbot.addWidget(body1)
    qtbot.addWidget(body2)
    for body in (body1, body2):
        body.resize(360, 400)
        body.show()
        qtbot.waitExposed(body)

    hover1 = _copy_link_hover_point(body1)
    hover2 = _copy_link_hover_point(body2)
    assert hover1 is not None
    assert hover2 is not None

    move1 = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        hover1,
        hover1,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    body1.mouseMoveEvent(move1)
    assert body1._copy_hover_index == 0
    assert body1.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert body2._copy_hover_index is None

    move2 = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        hover2,
        hover2,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    body2.mouseMoveEvent(move2)
    assert body2._copy_hover_index == 0
    assert body2.cursor().shape() == Qt.CursorShape.PointingHandCursor

    from PySide6.QtCore import QEvent

    body1.leaveEvent(QEvent(QEvent.Type.Leave))
    assert body1._copy_hover_index is None
    assert body1.cursor().shape() == Qt.CursorShape.IBeamCursor
    assert "text-decoration:underline" not in body1.toHtml()
    assert body2._copy_hover_index == 0


def test_copy_link_hover_on_enter_without_mouse_move(qapp: QApplication, qtbot) -> None:
    """Entering the body over Copy applies hover without a mouse-move event."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    hover_point = _copy_link_hover_point(body)
    assert hover_point is not None
    global_point = body.mapToGlobal(hover_point.toPoint())
    enter = QEnterEvent(
        hover_point,
        hover_point,
        QPoint(global_point),
    )
    body.enterEvent(enter)

    assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor
    assert body._copy_hover_index == 0


def test_copy_link_geometry_hit_near_label(qapp: QApplication, qtbot) -> None:
    """Padded geometry hit-testing reaches Copy when anchorAt misses by a few pixels."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    anchor_point = _copy_link_hover_point(body)
    assert anchor_point is not None
    near_point = QPointF(anchor_point.x() + 6, anchor_point.y() + 4)
    layout = body._document.documentLayout()
    assert layout.anchorAt(near_point) != "postmark-code-copy:0"

    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        near_point,
        near_point,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    body.mouseMoveEvent(move)

    assert body._copy_hover_index == 0
    assert body.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_copy_link_anchor_is_on_header_right_edge(qapp: QApplication, qtbot) -> None:
    """Copy link hit-testing aligns with the right edge of the code block."""
    body = MarkdownContent("```python\nprint(1)\n```")
    qtbot.addWidget(body)
    body.resize(360, 200)
    body.show()
    qtbot.waitExposed(body)

    hover_point = _copy_link_hover_point(body)
    assert hover_point is not None
    layout = body._document.documentLayout()
    assert hover_point.x() >= layout.documentSize().width() * 0.75


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


_MULTILINE_BASH_SAMPLE = (
    "```bash\n"
    "# Initialise a module (only needed once)\n"
    "go mod init example.com/httpclient\n"
    "# Run\n"
    "go run HTTPClientWithValidation.go\n"
    "```"
)


def test_multiline_code_selection_preserves_newlines(qapp: QApplication, qtbot) -> None:
    """Selecting across fenced-code table rows keeps line breaks in plain text."""
    body = MarkdownContent(_MULTILINE_BASH_SAMPLE)
    qtbot.addWidget(body)
    body.resize(360, 400)
    body.show()
    qtbot.waitExposed(body)

    doc = body._document
    start = doc.find("# Initialise").selectionStart()
    end = doc.find("go run HTTPClientWithValidation.go").selectionEnd()
    body._selection_anchor = start
    body._selection_cursor = end

    selected = body._selected_text()
    assert "\n" in selected
    assert "go mod init example.com/httpclient" in selected
    assert ")go mod init" not in selected

    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier,
    )
    body.keyPressEvent(event)
    copied = QApplication.clipboard().text()
    assert "\n" in copied
    assert ")go mod init" not in copied


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
