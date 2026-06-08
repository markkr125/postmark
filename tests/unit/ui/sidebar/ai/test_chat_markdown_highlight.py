"""Tests for chat markdown code highlighting."""

from __future__ import annotations

from ui.sidebar.ai.markdown.highlight_code import highlight_code_to_html, normalize_language
from ui.styling.theme import DARK_PALETTE


class TestNormalizeLanguage:
    """Tests for :func:`normalize_language`."""

    def test_alias_py(self) -> None:
        assert normalize_language("py") == "python"


class TestHighlightCodeToHtml:
    """Tests for :func:`highlight_code_to_html`."""

    def test_escapes_html_literals(self) -> None:
        html = highlight_code_to_html("if a < b & c:", "python", palette=DARK_PALETTE)
        assert "&lt;" in html
        assert "&amp;" in html
        assert "< b" not in html

    def test_token_colour_spans(self) -> None:
        html = highlight_code_to_html("import os", "python", palette=DARK_PALETTE)
        assert 'style="color:' in html
        assert "import" in html

    def test_line_numbers(self) -> None:
        html = highlight_code_to_html("a\nb", "python", palette=DARK_PALETTE)
        assert ">1<" in html or "> 1<" in html or "1</td>" in html
        assert ">2<" in html or "> 2<" in html or "2</td>" in html

    def test_language_label(self) -> None:
        html = highlight_code_to_html("pass", "py", palette=DARK_PALETTE)
        assert ">python<" in html

    def test_sharp_bordered_table_chrome(self) -> None:
        html = highlight_code_to_html("pass", "python", palette=DARK_PALETTE)
        assert "border:1px solid" in html
        assert "border-radius" not in html
        assert html.startswith("<table")

    def test_long_one_liner_wrap_styles(self) -> None:
        long_line = "x = " + '"' + ("a" * 120) + '"'
        html = highlight_code_to_html(long_line, "python", palette=DARK_PALETTE)
        assert "pre-wrap" in html
        assert "break-all" in html
