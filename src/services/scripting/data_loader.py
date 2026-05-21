"""Load CSV/JSON data files for data-driven script and collection runs."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any


def parse_data_file(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV or JSON file into a list of row dicts.

    CSV files use :class:`csv.DictReader`. JSON files must be a top-level
    array of objects; non-dict entries are skipped.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            return [dict(row) for row in data if isinstance(row, dict)]
        return []
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]
