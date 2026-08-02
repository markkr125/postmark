"""Chat attachment storage — copies kept beside the session on disk."""

from __future__ import annotations

from services.ai.chat.attachments.models import (
    ATTACHMENT_DIR_NAME,
    ATTACHMENT_INDEX_NAME,
    StoredAttachment,
    attachment_handle,
    handle_ordinal,
)
from services.ai.chat.attachments.store import (
    attachment_path,
    list_attachments,
    resolve_attachment,
    set_turn_attachments,
    store_attachments,
)

__all__ = [
    "ATTACHMENT_DIR_NAME",
    "ATTACHMENT_INDEX_NAME",
    "StoredAttachment",
    "attachment_handle",
    "attachment_path",
    "handle_ordinal",
    "list_attachments",
    "resolve_attachment",
    "set_turn_attachments",
    "store_attachments",
]
