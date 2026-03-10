"""Authorization tab mixin re-export.

This module re-exports :class:`_AuthMixin` from the shared
``ui.request.auth`` sub-package so that existing imports
continue to work.
"""

from __future__ import annotations

from ui.request.auth.auth_mixin import _AuthMixin

__all__ = ["_AuthMixin"]
