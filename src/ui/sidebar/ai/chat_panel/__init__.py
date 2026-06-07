"""AI chat panel sub-package — transcript, composer, and streaming controls."""

from ui.sidebar.ai.chat_panel.composer import _COMPOSER_MAX_LINES, _COMPOSER_MIN_LINES
from ui.sidebar.ai.chat_panel.panel import AiChatPanel

__all__ = [
    "_COMPOSER_MAX_LINES",
    "_COMPOSER_MIN_LINES",
    "AiChatPanel",
]
