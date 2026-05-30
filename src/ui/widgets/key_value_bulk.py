"""Serialize and parse key-value rows for Postman-style bulk text editing."""

from __future__ import annotations

# Shown when the bulk editor is empty (Postman-style hints).
BULK_PLACEHOLDER = (
    "Rows are separated by new lines\n"
    "Keys and values are separated by :\n"
    "Prepend // to any row you want to add but keep disabled"
)


def serialize_for_bulk(rows: list[dict]) -> str:
    """Build bulk text from row dicts (``key``, ``value``, ``enabled``).

    Disabled rows are written with a ``// `` prefix.  Description is not
    represented in bulk form; round-tripping through bulk clears it.
    """
    lines: list[str] = []
    for row in rows:
        key = str(row.get("key", "")).strip()
        if not key:
            continue
        enabled = bool(row.get("enabled", True))
        prefix = "// " if not enabled else ""
        if row.get("flag"):
            lines.append(f"{prefix}{key}")
            continue
        value = str(row.get("value", ""))
        lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)


def parse_bulk_text(text: str) -> list[dict]:
    """Parse bulk lines into row dicts (``key``, ``value``, ``enabled``).

    Each non-empty line uses the first ``: `` or ``=`` as the separator
    between key and value (same rules as :meth:`KeyValueTableWidget.from_text`).
    Lines starting with ``//`` (after leading whitespace) are disabled.
    Rows with an empty key after trimming are skipped.
    """
    rows: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        enabled = True
        if line.startswith("//"):
            enabled = False
            line = line[2:].lstrip()
            if not line:
                continue
        if ": " in line:
            key, _, value = line.partition(": ")
        elif "=" in line:
            key, _, value = line.partition("=")
        else:
            key, value = line, ""
        key = key.strip()
        if not key:
            continue
        row: dict = {"key": key, "value": value.strip(), "enabled": enabled}
        if ": " not in line and "=" not in line:
            row["flag"] = True
        rows.append(row)
    return rows
