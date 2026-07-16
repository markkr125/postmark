"""Serialize collection-runner results to CSV / JSON (UI-independent)."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any


def export_run_results_csv(results: list[dict[str, Any]]) -> str:
    """Serialize run result rows to CSV text."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Method", "Status", "Time (ms)", "Tests", "Result"])
    for r in results:
        tests = r.get("test_results", [])
        if not isinstance(tests, list):
            tests = []
        passed = sum(1 for t in tests if isinstance(t, dict) and t.get("passed"))
        total = len(tests)
        test_str = f"{passed}/{total}" if total else "-"
        status = "SKIP" if r.get("_skipped") else str(r.get("status_code", 0))
        writer.writerow(
            [
                r.get("name", ""),
                r.get("method", ""),
                status,
                f"{float(r.get('elapsed_ms', 0) or 0):.0f}",
                test_str,
                r.get("error", "") or "OK",
            ]
        )
    return output.getvalue()


def export_run_results_json(results: list[dict[str, Any]]) -> str:
    """Serialize run result rows to JSON text."""
    export: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        export.append(
            {
                "name": r.get("name", ""),
                "method": r.get("method", ""),
                "status_code": r.get("status_code", 0),
                "elapsed_ms": r.get("elapsed_ms", 0),
                "error": r.get("error", "") or "",
                "test_results": r.get("test_results", []),
                "_skipped": bool(r.get("_skipped")),
            }
        )
    return json.dumps(export, indent=2, ensure_ascii=False)
