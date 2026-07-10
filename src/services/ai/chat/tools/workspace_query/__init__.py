"""OpenHands tool — read-only workspace queries for AI chat."""

from __future__ import annotations

from .constants import (
    REDACTED_PLACEHOLDER,
    SECRET_PLACEHOLDER,
    _MAX_OUTPUT_CHARS,
    _VALID_SCOPES,
)
from .executor import (
    WORKSPACE_QUERY_DESCRIPTION,
    PostmarkWorkspaceQueryTool,
    WorkspaceQueryAction,
    WorkspaceQueryExecutor,
    WorkspaceQueryObservation,
    execute_workspace_query,
    register_workspace_query_tool,
)
from .helpers import (
    _cap_rows,
    _link,
    _truncate_url,
)

__all__ = [
    "REDACTED_PLACEHOLDER",
    "SECRET_PLACEHOLDER",
    "WORKSPACE_QUERY_DESCRIPTION",
    "_MAX_OUTPUT_CHARS",
    "_VALID_SCOPES",
    "PostmarkWorkspaceQueryTool",
    "WorkspaceQueryAction",
    "WorkspaceQueryExecutor",
    "WorkspaceQueryObservation",
    "_cap_rows",
    "_link",
    "_truncate_url",
    "execute_workspace_query",
    "register_workspace_query_tool",
]
