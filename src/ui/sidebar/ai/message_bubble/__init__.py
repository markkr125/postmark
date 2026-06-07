"""Chat message row widgets for the AI assistant panel."""

from ui.sidebar.ai.message_bubble.bubble import ChatMessageBubble, ChatRole
from ui.sidebar.ai.message_bubble.markdown_content import (
    MarkdownContent,
    _MarkdownContent,
    rerender_all_markdown_browsers,
)

# Back-compat for tests and theme hook callers.
_rerender_all_markdown_browsers = rerender_all_markdown_browsers

__all__ = [
    "ChatMessageBubble",
    "ChatRole",
    "MarkdownContent",
    "_MarkdownContent",
    "_rerender_all_markdown_browsers",
    "rerender_all_markdown_browsers",
]
