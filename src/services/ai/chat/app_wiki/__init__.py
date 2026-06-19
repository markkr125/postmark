"""In-app user knowledge base — paths, index build, and query helpers."""

from services.ai.chat.app_wiki.config import WIKI_CHAR_CAP
from services.ai.chat.app_wiki.query import execute_wiki_query

__all__ = ["WIKI_CHAR_CAP", "execute_wiki_query"]
