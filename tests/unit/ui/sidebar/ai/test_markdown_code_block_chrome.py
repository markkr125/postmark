"""Widget-level tests for fenced-code table chrome in MarkdownContent."""

from __future__ import annotations

import re

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from ui.sidebar.ai.markdown.highlight_code import copy_anchor_spans
from ui.sidebar.ai.markdown.render import render_markdown_body_html
from ui.sidebar.ai.message_bubble.markdown_content import MarkdownContent
from ui.styling.theme import DARK_PALETTE


def _count_html_tables(fragment: str) -> int:
    """Return how many ``<table`` tags appear in *fragment*."""
    return fragment.lower().count("<table")


class TestMarkdownCodeBlockChrome:
    """Tests for single-table fenced code rendering in assistant bodies."""

    def test_rendered_document_one_table_per_fence(self, qapp: QApplication, qtbot) -> None:
        """Each fenced block contributes exactly one HTML table."""
        body = MarkdownContent("```python\nimport os\n```")
        qtbot.addWidget(body)
        fragment = body.toHtml()
        assert _count_html_tables(fragment) == 1

    def test_multi_fence_one_table_each(self, qapp: QApplication, qtbot) -> None:
        """Multiple fences each add one table without nesting."""
        source = "```py\na=1\n```\n\n```bash\necho hi\n```"
        body = MarkdownContent(source)
        qtbot.addWidget(body)
        fragment = body.toHtml()
        assert _count_html_tables(fragment) == 2

    def test_copied_feedback_preserves_other_fence_headers(
        self,
        qapp: QApplication,
        qtbot,
    ) -> None:
        """Changing one Copy label must not shift and erase later fence headers."""
        source = (
            '```typescript\nconst a = 1;\n```\n\n```python\nprint(1)\n```\n\n```json\n{"a": 1}\n```'
        )
        body = MarkdownContent(source)
        qtbot.addWidget(body)

        body._copy_confirmed_index = 0
        body._sync_copy_link_appearance()

        text = body.document().toPlainText()
        assert "typescript" in text
        assert "python" in text
        assert "json" in text

        spans = copy_anchor_spans(body.document())
        cursor = QTextCursor(body.document())
        cursor.setPosition(spans[0][0])
        cursor.setPosition(spans[0][1], QTextCursor.MoveMode.KeepAnchor)
        assert cursor.selectedText() == "Copied"
        assert len(spans) == 3

    def test_markdown_data_table_and_fence_coexist(self, qapp: QApplication, qtbot) -> None:
        """Prose pipe tables and fenced code blocks both render as separate tables."""
        source = "| A | B |\n|---|---|\n| 1 | 2 |\n\n```py\nx=1\n```"
        body = MarkdownContent(source)
        qtbot.addWidget(body)
        fragment = body.toHtml()
        assert _count_html_tables(fragment) == 2
        assert "x=1" in fragment or "x" in fragment

    def test_body_fragment_no_nested_code_tables(self) -> None:
        """Rendered body HTML uses one flat table per fenced block."""
        fragment = render_markdown_body_html(
            "```python\nimport os\nprint(1)\n```",
            palette=DARK_PALETTE,
        )
        assert fragment.count("<table") == 1
        nested = re.search(r"<table[^>]*>.*<table", fragment, re.IGNORECASE | re.DOTALL)
        assert nested is None

    @pytest.mark.parametrize("line_count", [1, 2, 12])
    def test_screenshot_fixture_line_counts(self, line_count: int) -> None:
        """Multi-line blocks stay single-table for common line counts."""
        code = "\n".join(f"line_{index}" for index in range(1, line_count + 1))
        fragment = render_markdown_body_html(
            f"```python\n{code}\n```",
            palette=DARK_PALETTE,
        )
        assert fragment.count("<table") == 1
