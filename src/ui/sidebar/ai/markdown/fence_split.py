"""Split markdown into prose and fenced code segments."""

from __future__ import annotations

import re
from dataclasses import dataclass

_LIST_LINE_RE = re.compile(r"^(\d+\.|[-*+])\s")
_BULLET_LINE_RE = re.compile(r"^(\s*)(?:[◦•]|\d+\.|[-*+])\s+(.*)$")
_INDENTED_FENCE_OPEN_RE = re.compile(r"^(\s+)```([\w+-]*)\s*$")
_INDENTED_FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")
_MIN_INDENT_SPACES = 2
_EXECUTABLE_PREFIXES = (
    "pm.",
    "import ",
    "from ",
    "export ",
    "console.",
    "print(",
    "const ",
    "let ",
    "var ",
    "async ",
    "await ",
    "def ",
    "class ",
    "if ",
    "for ",
    "while ",
    "return ",
)
_PROSE_HINT_RE = re.compile(
    r"\b(?:that|can|be|used|without|the|and|with|helpers|global|into|scripts|prefix)\b",
    re.IGNORECASE,
)


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


def _leading_indent_width(line: str) -> int:
    """Return the number of leading space/tab columns on *line*."""
    width = 0
    for char in line:
        if char in (" ", "\t"):
            width += 1
        else:
            break
    return width


def _deindent_line(line: str, width: int) -> str:
    """Remove up to *width* leading space/tab columns from *line*."""
    if not line.strip():
        return ""
    remaining = width
    index = 0
    while index < len(line) and remaining > 0:
        if line[index] in (" ", "\t"):
            remaining -= 1
            index += 1
        else:
            break
    return line[index:]


def _is_bullet_line_code_body(body: str) -> bool:
    """Return whether a list-marker suffix reads like a scripting example row."""
    if not body.strip():
        return False
    if _is_executable_code_line(body) or _is_code_comment_line(body):
        return True
    stripped = body.strip()
    if re.match(r'^["\'(\+)]+', stripped):
        return True
    if stripped in {")", "};", "],"}:
        return True
    return bool(re.match(r"^[)\]},;+\s]", stripped))


def _unwrap_bullet_code_lines(lines: list[str]) -> list[str]:
    """Strip list markers from bullet rows that wrap bare scripting examples."""
    out: list[str] = []
    in_code_run = False
    open_balance = 0
    for line in lines:
        match = _BULLET_LINE_RE.match(line)
        if match is None:
            stripped = line.strip()
            if in_code_run and stripped and _is_code_continuation(line, open_balance=open_balance):
                out.append(line)
                open_balance += _delimiter_balance(line)
                continue
            in_code_run = False
            open_balance = 0
            out.append(line)
            continue
        indent, body = match.group(1), match.group(2)
        if _is_bullet_line_code_body(body) or (
            in_code_run and _is_code_continuation(body, open_balance=open_balance)
        ):
            unwrapped = f"{indent}{body.rstrip()}"
            out.append(unwrapped)
            in_code_run = True
            open_balance += _delimiter_balance(unwrapped)
            continue
        in_code_run = False
        open_balance = 0
        out.append(line)
    return out


def _promote_indented_fence_lines(lines: list[str]) -> list[str]:
    """Promote list-nested `` ``` `` rows to column 0 for Pygments splitting."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        open_match = _INDENTED_FENCE_OPEN_RE.match(lines[index])
        if open_match is None:
            out.append(lines[index])
            index += 1
            continue
        indent_width = len(open_match.group(1))
        lang = open_match.group(2) or ""
        index += 1
        code_lines: list[str] = []
        while index < len(lines):
            if _INDENTED_FENCE_CLOSE_RE.match(lines[index]):
                index += 1
                break
            row = lines[index]
            if not row.strip():
                code_lines.append("")
            elif _leading_indent_width(row) >= indent_width:
                code_lines.append(_deindent_line(row, indent_width).rstrip())
            else:
                code_lines.append(row.strip())
            index += 1
        sample = "\n".join(code_lines)
        _append_code_fence(out, code_lines, lang or _infer_code_lang(sample))
    return out


def _append_code_fence(out: list[str], code_lines: list[str], lang: str) -> None:
    """Append a fenced code block, inserting a blank line when needed for GFM."""
    if out and out[-1].strip():
        out.append("")
    out.append(f"```{lang}")
    out.extend(code_lines)
    out.append("```")


def _infer_code_lang(code: str) -> str:
    """Guess a Pygments lexer id for a Postmark scripting snippet."""
    sample = code.strip()
    if any(token in sample for token in ("const ", "let ", "var ", "=>", "interface ", "type ")):
        return "javascript"
    return "python"


def _looks_like_prose(line: str) -> bool:
    """Return whether *line* reads like documentation prose, not a code row."""
    stripped = line.strip()
    if not stripped:
        return False
    if any(stripped.startswith(prefix) for prefix in _EXECUTABLE_PREFIXES):
        return False
    space_words = [word for word in re.split(r"\s+", stripped) if word]
    if len(space_words) >= 8:
        return True
    if _PROSE_HINT_RE.search(stripped) and len(space_words) >= 4:
        return True
    return (
        stripped.endswith(".")
        and "pm." not in stripped.split(".")[0]
        and not any(stripped.startswith(prefix) for prefix in _EXECUTABLE_PREFIXES)
    )


def _delimiter_balance(line: str) -> int:
    """Return net open ``(``/``[`` count on one line (ignores strings roughly)."""
    return line.count("(") - line.count(")") + line.count("[") - line.count("]")


def _is_executable_code_line(line: str) -> bool:
    """Return whether *line* is an executable scripting example row."""
    stripped = line.strip()
    if not stripped or _looks_like_prose(line):
        return False
    if _LIST_LINE_RE.match(stripped):
        return False
    if stripped.startswith(("##", "**", "|", "◦", "•")):
        return False
    return any(stripped.startswith(prefix) for prefix in _EXECUTABLE_PREFIXES)


def _is_code_comment_line(line: str) -> bool:
    """Return whether *line* is a short ``#`` comment that heads an example block."""
    stripped = line.strip()
    if not stripped.startswith("#") or stripped.startswith("##"):
        return False
    if _looks_like_prose(line):
        return False
    return len(stripped) <= 96


def _can_start_code_run(lines: list[str], start: int) -> bool:
    """Return whether a bare code run may begin at *start*."""
    if _is_executable_code_line(lines[start]):
        return True
    if not _is_code_comment_line(lines[start]):
        return False
    for index in range(start + 1, min(start + 4, len(lines))):
        row = lines[index]
        if not row.strip():
            continue
        return _is_executable_code_line(row) or (
            row.startswith(("    ", "\t")) and _delimiter_balance(lines[start]) >= 0
        )
    return False


def _is_code_continuation(line: str, *, open_balance: int) -> bool:
    """Return whether *line* continues an in-progress bare code run."""
    if open_balance > 0:
        return not _looks_like_prose(line)
    stripped = line.strip()
    if not stripped:
        return True
    if _is_executable_code_line(line) or _is_code_comment_line(line):
        return True
    if line.startswith(("    ", "\t")):
        return True
    if re.match(r'^["\'(\+)]+', stripped):
        return True
    if stripped in {")", "};", "],"}:
        return True
    return bool(re.match(r"^[)\]},;+\s]", stripped))


def _block_has_executable_code(block: list[str]) -> bool:
    """Return whether *block* contains at least one executable example line."""
    return any(_is_executable_code_line(line) for line in block)


def _take_bare_code_run(lines: list[str], start: int) -> tuple[list[str], int] | None:
    """Return a contiguous bare code run and the index after it."""
    if not _can_start_code_run(lines, start):
        return None
    block: list[str] = []
    index = start
    open_balance = 0
    while index < len(lines):
        row = lines[index]
        if not row.strip():
            if index + 1 < len(lines) and _is_code_continuation(
                lines[index + 1],
                open_balance=open_balance,
            ):
                block.append("")
                index += 1
                continue
            break
        if block and not _is_code_continuation(row, open_balance=open_balance):
            break
        if not block and not (_is_executable_code_line(row) or _is_code_comment_line(row)):
            break
        block.append(row.rstrip())
        open_balance += _delimiter_balance(row)
        index += 1
    if not _block_has_executable_code(block):
        return None
    return block, index


def _take_indented_code_block(lines: list[str], start: int) -> tuple[list[str], int] | None:
    """Return de-indented code lines and the index after an indented block."""
    if not lines[start].strip():
        return None
    base_width = _leading_indent_width(lines[start])
    if base_width < _MIN_INDENT_SPACES and not lines[start].startswith("\t"):
        return None
    if _BULLET_LINE_RE.match(lines[start]):
        return None

    block: list[str] = []
    index = start
    open_balance = 0
    while index < len(lines):
        row = lines[index]
        if not row.strip():
            if index + 1 < len(lines) and _is_code_continuation(
                lines[index + 1],
                open_balance=open_balance,
            ):
                block.append("")
                index += 1
                continue
            break
        row_indent = _leading_indent_width(row)
        if (
            block
            and row_indent < base_width
            and not _is_code_continuation(
                row,
                open_balance=open_balance,
            )
        ):
            break
        if row_indent >= base_width:
            block.append(_deindent_line(row, base_width).rstrip())
        elif _is_code_continuation(row, open_balance=open_balance):
            block.append(row.strip())
        else:
            break
        open_balance += _delimiter_balance(block[-1])
        index += 1
    if not _block_has_executable_code(block):
        return None
    return block, index


def normalize_markdown_code_blocks(markdown: str) -> str:
    """Wrap bare scripting lines and indented blocks in ``` fences for Pygments rendering."""
    if not markdown.strip():
        return markdown

    lines = _promote_indented_fence_lines(_unwrap_bullet_code_lines(markdown.split("\n")))
    out: list[str] = []
    index = 0
    in_fence = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            index += 1
            continue
        if in_fence:
            out.append(line)
            index += 1
            continue

        indented = _take_indented_code_block(lines, index)
        if indented is not None:
            code_lines, next_index = indented
            lang = _infer_code_lang("\n".join(code_lines))
            _append_code_fence(out, code_lines, lang)
            index = next_index
            continue

        bare = _take_bare_code_run(lines, index)
        if bare is not None:
            code_lines, next_index = bare
            lang = _infer_code_lang("\n".join(code_lines))
            _append_code_fence(out, code_lines, lang)
            index = next_index
            continue

        out.append(line)
        index += 1

    return "\n".join(out)


def _fence_at_line_start(text: str, start: int) -> int | None:
    """Return the index of a ``` marker at a line boundary at or after *start*."""
    pos = start
    while pos < len(text):
        line_end = text.find("\n", pos)
        if line_end < 0:
            line_end = len(text)
        line = text[pos:line_end]
        stripped = line.lstrip(" \t")
        if stripped.startswith("```"):
            return pos + len(line) - len(stripped)
        if line_end >= len(text):
            return None
        pos = line_end + 1
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
    (streaming-safe). Bare ``pm.`` example lines and four-space indents are
    normalized into fences before splitting.
    """
    markdown = normalize_markdown_code_blocks(markdown)
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

        code = markdown[code_start:close_fence].removesuffix("\n")
        segments.append(CodeSegment(lang=lang, code=code, provisional=False))
        cursor = _fence_line_end(markdown, close_fence)
        prose_start = cursor

    if prose_start < length:
        segments.append(ProseSegment(markdown[prose_start:]))

    return segments if segments else [ProseSegment(markdown)]


def fenced_code_sources(markdown: str) -> list[str]:
    """Return raw fenced code bodies in document order."""
    return [
        segment.code
        for segment in split_fenced_blocks(markdown)
        if isinstance(segment, CodeSegment)
    ]


__all__ = [
    "CodeSegment",
    "MarkdownSegment",
    "ProseSegment",
    "fenced_code_sources",
    "normalize_markdown_code_blocks",
    "split_fenced_blocks",
]
