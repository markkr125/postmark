"""Serialize script test results to JSON and JUnit XML.

Re-exports :mod:`services.test_export` for UI callers.
"""

from __future__ import annotations

from services.test_export import export_test_results_json, export_test_results_junit

__all__ = ["export_test_results_json", "export_test_results_junit"]
