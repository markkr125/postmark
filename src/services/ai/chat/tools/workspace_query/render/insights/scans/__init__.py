"""Workspace health scan helpers for scope=insights."""

from __future__ import annotations

from .common import _collect_dup_groups, _walk_request_nodes
from .drift import scan_request_drift, scan_response_drift
from .hygiene import (
    scan_auth_gaps,
    scan_dead_requests,
    scan_local_deps,
    scan_secret_hygiene,
    scan_token_expiry,
)
from .tests import scan_duplicates, scan_missing_tests, scan_script_regressions
from .variables import scan_variable_issues

__all__ = [
    "_collect_dup_groups",
    "_walk_request_nodes",
    "scan_auth_gaps",
    "scan_dead_requests",
    "scan_duplicates",
    "scan_local_deps",
    "scan_missing_tests",
    "scan_request_drift",
    "scan_response_drift",
    "scan_script_regressions",
    "scan_secret_hygiene",
    "scan_token_expiry",
    "scan_variable_issues",
]
