"""Size caps for collection-draft soft-normalization."""

from __future__ import annotations

from services.ai.chat.tools.collection_draft.state import (
    MAX_SAVED_RESPONSE_BODY,
    MAX_SAVED_RESPONSES,
)

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"})
MAX_REQUESTS_PER_BATCH = 20

# Request body = the doc's request example. Soft-truncate oversize bodies so sibling
# requests still land; hard ``ok: false`` is for structural failures (not empty
# ``requests: []``, which is a soft no-op). 16_000 fits realistic nested request
# examples; the old 4_000 cap truncated common hotel / booking payloads and
# produced red or confusing tool cards.
MAX_BODY_CHARS = 16_000
MAX_PARAMS_PER_REQUEST = 40
MAX_PARAM_DESCRIPTION_CHARS = 500
MAX_DESCRIPTION_CHARS = 8000
MAX_SCRIPT_CHARS = 8000
MAX_VARIABLES = 80
MAX_DEFAULT_HEADERS = 40
MAX_AUTH_CHARS = 4000
MAX_SIGNATURE_CHARS = 2000

__all__ = [
    "MAX_AUTH_CHARS",
    "MAX_BODY_CHARS",
    "MAX_DEFAULT_HEADERS",
    "MAX_DESCRIPTION_CHARS",
    "MAX_PARAMS_PER_REQUEST",
    "MAX_PARAM_DESCRIPTION_CHARS",
    "MAX_REQUESTS_PER_BATCH",
    "MAX_SAVED_RESPONSES",
    "MAX_SAVED_RESPONSE_BODY",
    "MAX_SCRIPT_CHARS",
    "MAX_SIGNATURE_CHARS",
    "MAX_VARIABLES",
    "_HTTP_METHODS",
]
