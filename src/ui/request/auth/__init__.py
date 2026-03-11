"""Auth sub-package — shared auth UI, serialisation, and type definitions.

Re-exports the public API used by :class:`RequestEditorWidget`,
:class:`FolderEditorWidget`, and other consumers.
"""

from __future__ import annotations

from ui.request.auth.auth_field_specs import AUTH_FIELD_SPECS
from ui.request.auth.auth_mixin import _AuthMixin
from ui.request.auth.auth_pages import (
    AUTH_FIELD_ORDER,
    AUTH_KEY_TO_DISPLAY,
    AUTH_PAGE_INDEX,
    AUTH_TYPE_DESCRIPTIONS,
    AUTH_TYPE_KEYS,
    AUTH_TYPE_LABELS,
    AUTH_TYPES,
)
from ui.request.auth.oauth2_page import OAuth2Page

__all__ = [
    "AUTH_FIELD_ORDER",
    "AUTH_FIELD_SPECS",
    "AUTH_KEY_TO_DISPLAY",
    "AUTH_PAGE_INDEX",
    "AUTH_TYPES",
    "AUTH_TYPE_DESCRIPTIONS",
    "AUTH_TYPE_KEYS",
    "AUTH_TYPE_LABELS",
    "OAuth2Page",
    "_AuthMixin",
]
