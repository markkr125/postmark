"""Operation dispatch for the incremental collection draft tool.

Public surface matches the former ``ops.py`` module so
``from services.ai.chat.tools.collection_draft import ops`` keeps working.
"""

from __future__ import annotations

from services.ai.chat.tools.collection_draft.ops.dispatch import (
    op_add_requests,
    op_discard,
    op_finish,
    op_start,
    op_status,
)
from services.ai.chat.tools.collection_draft.ops.limits import (
    MAX_AUTH_CHARS,
    MAX_BODY_CHARS,
    MAX_DEFAULT_HEADERS,
    MAX_DESCRIPTION_CHARS,
    MAX_PARAM_DESCRIPTION_CHARS,
    MAX_PARAMS_PER_REQUEST,
    MAX_SCRIPT_CHARS,
    MAX_SIGNATURE_CHARS,
    MAX_VARIABLES,
)
from services.ai.chat.tools.collection_draft.state import (
    MAX_SAVED_RESPONSE_BODY,
    MAX_SAVED_RESPONSES,
)

__all__ = [
    "MAX_AUTH_CHARS",
    "MAX_BODY_CHARS",
    "MAX_DEFAULT_HEADERS",
    "MAX_DESCRIPTION_CHARS",
    "MAX_PARAMS_PER_REQUEST",
    "MAX_PARAM_DESCRIPTION_CHARS",
    "MAX_SAVED_RESPONSES",
    "MAX_SAVED_RESPONSE_BODY",
    "MAX_SCRIPT_CHARS",
    "MAX_SIGNATURE_CHARS",
    "MAX_VARIABLES",
    "op_add_requests",
    "op_discard",
    "op_finish",
    "op_start",
    "op_status",
]
