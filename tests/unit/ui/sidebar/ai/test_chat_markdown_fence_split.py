"""Tests for chat markdown fence splitting."""

from __future__ import annotations

from ui.sidebar.ai.markdown.fence_split import CodeSegment, ProseSegment, split_fenced_blocks


class TestSplitFencedBlocks:
    """Tests for :func:`split_fenced_blocks`."""

    def test_closed_fence(self) -> None:
        source = "Before\n\n```python\nprint(1)\n```\n\nAfter"
        segments = split_fenced_blocks(source)
        assert len(segments) == 3
        assert isinstance(segments[0], ProseSegment)
        assert segments[0].text == "Before\n\n"
        assert isinstance(segments[1], CodeSegment)
        assert segments[1].lang == "python"
        assert segments[1].code == "print(1)"
        assert segments[1].provisional is False
        assert isinstance(segments[2], ProseSegment)
        assert segments[2].text == "\nAfter"

    def test_open_streaming_tail(self) -> None:
        source = "```py\nimport os\npartial"
        segments = split_fenced_blocks(source)
        assert len(segments) == 1
        assert isinstance(segments[0], CodeSegment)
        assert segments[0].lang == "py"
        assert segments[0].code == "import os\npartial"
        assert segments[0].provisional is True

    def test_inline_backticks_not_fences(self) -> None:
        source = "Use `inline` and not a fence."
        segments = split_fenced_blocks(source)
        assert len(segments) == 1
        assert isinstance(segments[0], ProseSegment)
        assert segments[0].text == source

    def test_empty_string(self) -> None:
        segments = split_fenced_blocks("")
        assert len(segments) == 1
        assert isinstance(segments[0], ProseSegment)

    def test_bare_pm_lines_become_fenced_python(self) -> None:
        """Subagent-style bare pm examples render as Pygments code segments."""
        source = (
            "Example snippets:\n\n"
            'pm.request.headers["Authorization"] = f"Bearer {token}"\n\n'
            'pm.request.url.getHost()  # "127.0.0.1"\n'
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 1
        assert code_segments[0].lang == "python"
        assert "pm.request.headers" in code_segments[0].code
        assert "pm.request.url.getHost()" in code_segments[0].code

    def test_indented_block_becomes_fenced(self) -> None:
        source = (
            "Before\n\n    pm.test('ok', () => {})\n    pm.response.to.have.status(200)\n\nAfter"
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 1
        assert "pm.test" in code_segments[0].code

    def test_closing_fence_newline_not_in_code_body(self) -> None:
        """The newline before a closing fence is not an extra code line."""
        source = "```python\nline_a\nline_b\n```"
        segments = split_fenced_blocks(source)
        assert isinstance(segments[0], CodeSegment)
        assert segments[0].code == "line_a\nline_b"

    def test_intentional_blank_line_before_close(self) -> None:
        """A blank line immediately before the closing fence is preserved."""
        source = "```python\nline_a\n\n```"
        segments = split_fenced_blocks(source)
        assert isinstance(segments[0], CodeSegment)
        assert segments[0].code == "line_a\n"

    def test_comment_header_with_multiline_pm_block(self) -> None:
        """``# Pre-request`` headings plus wrapped assignments become one fence."""
        source = (
            "# Pre-request: set auth header\n"
            'pm.request.headers["Authorization"] = (\n'
            '    "Bearer " + pm.variables.get("token")\n'
            ")\n"
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 1
        assert "Pre-request" in code_segments[0].code
        assert "Bearer " in code_segments[0].code

    def test_prose_mentioning_pm_is_not_fenced(self) -> None:
        """Documentation prose that mentions ``pm.`` inline stays prose."""
        source = (
            "Global helpers that can be used without a pm. prefix "
            "(e.g. datetime_now(), hashlib_sha256(), uuid_v4())."
        )
        segments = split_fenced_blocks(source)
        assert len(segments) == 1
        assert isinstance(segments[0], ProseSegment)

    def test_comment_only_prose_line_is_not_fenced(self) -> None:
        source = "# quick copy-paste into scripts."
        segments = split_fenced_blocks(source)
        assert len(segments) == 1
        assert isinstance(segments[0], ProseSegment)

    def test_url_inspection_block_with_comment_header(self) -> None:
        source = (
            "# URL inspection / mutation\n"
            "print(pm.request.url.getHost())\n"
            'pm.request.url.query.add({"key": "page", "value": "2"})\n'
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 1
        assert "getHost" in code_segments[0].code
        assert "query.add" in code_segments[0].code

    def test_two_space_indented_code_under_list(self) -> None:
        """List-nested wiki examples with two-space indents become fenced code."""
        source = (
            "◦ Request headers\n"
            "  # Pre-request: set auth header\n"
            '  pm.request.headers["Authorization"] = (\n'
            '      "Bearer " + pm.variables.get("token")\n'
            "  )\n"
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 1
        assert "Pre-request" in code_segments[0].code
        assert "Bearer " in code_segments[0].code

    def test_bullet_prefixed_code_lines(self) -> None:
        """Subagent replies that prefix each code row with a list marker still fence."""
        source = (
            "◦ # Pre-request: set auth header\n"
            '◦ pm.request.headers["Authorization"] = (\n'
            '◦     "Bearer " + pm.variables.get("token")\n'
            "◦ )\n"
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 1
        assert "Pre-request" in code_segments[0].code
        assert "Bearer " in code_segments[0].code

    def test_indented_fences_inside_list_items(self) -> None:
        """Wiki-style ``` blocks indented under list markers become Pygments segments."""
        source = (
            "## Python scripting docs\n\n"
            "- **Request helpers**\n"
            "  - Auth header\n"
            "    ```python\n"
            "    # Pre-request: set auth header\n"
            '    pm.request.headers["Authorization"] = (\n'
            '        "Bearer " + pm.variables.get("token")\n'
            "    )\n"
            "    ```\n"
            "  - URL inspection\n"
            "    ```python\n"
            "    # URL inspection / mutation\n"
            "    print(pm.request.url.getHost())\n"
            '    pm.request.url.query.add({"key": "page", "value": "2"})\n'
            "    ```\n"
        )
        segments = split_fenced_blocks(source)
        code_segments = [segment for segment in segments if isinstance(segment, CodeSegment)]
        assert len(code_segments) == 2
        assert "Pre-request" in code_segments[0].code
        assert "getHost" in code_segments[1].code
