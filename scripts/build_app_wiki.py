#!/usr/bin/env python3
"""Build generated app-wiki artifacts under ``data/app-wiki/``."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as ``python scripts/build_app_wiki.py`` from repo root.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from database.data_paths import project_root  # noqa: E402
from services.ai.chat.app_wiki.build_index import write_index  # noqa: E402
from services.ai.chat.app_wiki.quickref import write_scripting_quickrefs  # noqa: E402
from services.ai.chat.app_wiki.schema import WIKI_SCHEMA_TEXT  # noqa: E402


def main() -> int:
    """Generate quickref pages, index, and WIKI.md schema."""
    root = project_root()
    quickrefs = write_scripting_quickrefs(root)
    index_path = write_index(root)
    schema_path = root / "data" / "app-wiki" / "WIKI.md"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(WIKI_SCHEMA_TEXT, encoding="utf-8")
    print(f"Wrote {schema_path.relative_to(root)}")
    for path in quickrefs:
        print(f"Wrote {path.relative_to(root)}")
    print(f"Wrote {index_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
