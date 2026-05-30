"""Serialize script test results to JSON and JUnit XML."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any


def export_test_results_json(results: list[dict[str, Any]]) -> str:
    """Return a JSON document for *results* (``TestResult``-shaped dicts)."""
    return json.dumps(results, indent=2, ensure_ascii=False)


def export_test_results_junit(
    results: list[dict[str, Any]],
    *,
    suite_name: str,
) -> str:
    """Build JUnit XML for CI integrations."""
    suite = ET.Element("testsuite", name=suite_name)
    for row in results:
        name = str(row.get("name", "unnamed"))
        if name == "(runtime error)":
            continue
        classname = str(row.get("source_name") or suite_name)
        duration_ms = float(row.get("duration_ms", 0.0))
        time_s = f"{duration_ms / 1000:.3f}"
        case = ET.SubElement(
            suite,
            "testcase",
            classname=classname,
            name=name,
            time=time_s,
        )
        if row.get("skipped"):
            ET.SubElement(case, "skipped")
        elif not row.get("passed", False):
            msg = str(row.get("error") or "failed")
            fail = ET.SubElement(case, "failure", message=msg)
            fail.text = msg
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)
