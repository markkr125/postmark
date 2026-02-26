"""Check that relative file links in Markdown documents resolve to real files.

Usage::

    poetry run python scripts/check_md_links.py

Exit code 0 means all links are valid.  Non-zero means at least one target
was not found; each broken link is printed to stderr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Markdown link pattern: [text](target) — ignores URLs with schemes
_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<target>[^)]+)\)")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://")

# Files to check (relative to project root)
_MD_FILES = [
    ".github/copilot-instructions.md",
    ".github/instructions/architecture.instructions.md",
    ".github/instructions/pyside6.instructions.md",
    ".github/instructions/sqlalchemy.instructions.md",
    ".github/instructions/testing.instructions.md",
    "README.md",
]


def _check_file(md_path: Path, root: Path) -> list[str]:
    """Return a list of error messages for broken links in *md_path*."""
    errors: list[str] = []
    base_dir = md_path.parent

    for lineno, line in enumerate(md_path.read_text().splitlines(), start=1):
        for match in _LINK_RE.finditer(line):
            target = match.group("target")

            # Strip optional fragment (#heading)
            target = target.split("#")[0]
            if not target:
                continue

            # Skip external URLs
            if _SCHEME_RE.match(target):
                continue

            resolved = (base_dir / target).resolve()
            if not resolved.exists():
                rel = md_path.relative_to(root)
                errors.append(f"{rel}:{lineno}: broken link -> {target}")

    return errors


def main() -> int:
    """Entry point — returns 0 on success, 1 if any links are broken."""
    root = Path(__file__).resolve().parents[1]
    all_errors: list[str] = []

    for rel in _MD_FILES:
        md_path = root / rel
        if not md_path.exists():
            all_errors.append(f"{rel}: file itself not found")
            continue
        all_errors.extend(_check_file(md_path, root))

    if all_errors:
        print("Broken Markdown links found:", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print(f"All links OK ({len(_MD_FILES)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
