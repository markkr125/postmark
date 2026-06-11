"""Copy-link chrome state for fenced code blocks in assistant markdown."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodeCopyChrome:
    """Hover and confirmation state for fenced-code header Copy links."""

    confirmed_index: int | None = None
    hover_index: int | None = None

    def for_block(self, block_index: int) -> tuple[bool, bool]:
        """Return ``(copied, hovered)`` flags for *block_index*."""
        copied = self.confirmed_index == block_index
        hovered = not copied and self.hover_index == block_index
        return copied, hovered
