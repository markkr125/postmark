"""Split markdown into prose and fenced code segments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProseSegment:
    """Plain markdown prose between fenced code blocks."""

    text: str


@dataclass(frozen=True, slots=True)
class CodeSegment:
    """Fenced code block body and optional language tag."""

    lang: str
    code: str
    provisional: bool = False


MarkdownSegment = ProseSegment | CodeSegment


def _fence_at_line_start(text: str, start: int) -> int | None:
    """Return the index of a ``` marker at a line boundary at or after *start*."""
    pos = start
    while pos < len(text):
        idx = text.find("```", pos)
        if idx < 0:
            return None
        if idx == 0 or text[idx - 1] == "\n":
            return idx
        pos = idx + 3
    return None


def _fence_line_end(text: str, fence_start: int) -> int:
    """Return the index after the newline following a fence line, or len(text)."""
    line_end = text.find("\n", fence_start)
    if line_end < 0:
        return len(text)
    return line_end + 1


def _parse_fence_lang(fence_line: str) -> str:
    """Extract the language tag from an opening ``` line."""
    body = fence_line.strip()
    if not body.startswith("```"):
        return ""
    info = body[3:].strip()
    return info.split()[0] if info else ""


def split_fenced_blocks(markdown: str) -> list[MarkdownSegment]:
    """Split *markdown* into prose and fenced code segments.

    Unclosed trailing fences yield a ``CodeSegment`` with ``provisional=True``
    (streaming-safe). Indented four-space code blocks are not handled.
    """
    if not markdown:
        return [ProseSegment("")]

    segments: list[MarkdownSegment] = []
    prose_start = 0
    cursor = 0
    length = len(markdown)

    while cursor < length:
        open_fence = _fence_at_line_start(markdown, cursor)
        if open_fence is None:
            break

        if open_fence > prose_start:
            segments.append(ProseSegment(markdown[prose_start:open_fence]))

        open_line_end = markdown.find("\n", open_fence)
        if open_line_end < 0:
            lang = _parse_fence_lang(markdown[open_fence:])
            code = ""
            segments.append(CodeSegment(lang=lang, code=code, provisional=True))
            return segments

        lang = _parse_fence_lang(markdown[open_fence:open_line_end])
        code_start = open_line_end + 1
        close_fence = _fence_at_line_start(markdown, code_start)

        if close_fence is None:
            code = markdown[code_start:]
            segments.append(CodeSegment(lang=lang, code=code, provisional=True))
            return segments

        code = markdown[code_start:close_fence]
        segments.append(CodeSegment(lang=lang, code=code, provisional=False))
        cursor = _fence_line_end(markdown, close_fence)
        prose_start = cursor

    if prose_start < length:
        segments.append(ProseSegment(markdown[prose_start:]))

    return segments if segments else [ProseSegment(markdown)]
