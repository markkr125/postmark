"""Extract npm ``@types`` member names for editor completion fallback.

Deno LSP often leaves ``pm.require('npm:…')`` values as ``any`` in ``.js`` buffers,
so ``textDocument/completion`` returns nothing on ``variable.``. After ``deno cache``
we read the cached ``@types`` tree and offer members directly.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from services.lsp.pm_require_resolve import npm_types_specifier
from services.scripting.js_runtime import PmRequireSpec

logger = logging.getLogger(__name__)

# Method-like members in DefinitelyTyped packages (indented declarations in .d.ts).
_DTS_MEMBER_RE = re.compile(r"^\s{4,}(\w+)\s*[<(]", re.MULTILINE)

_SKIP_MEMBER_NAMES = frozenset(
    {
        "interface",
        "type",
        "export",
        "import",
        "declare",
        "readonly",
        "extends",
        "implements",
        "constructor",
        "get",
        "set",
        "static",
        "async",
        "await",
        "from",
        "of",
        "keyof",
        "infer",
        "const",
        "let",
        "var",
        "namespace",
        "module",
    }
)

_PM_REQUIRE_VAR_RE = re.compile(
    r"""(?:let|const|var)\s+(?P<var>\w+)\s*=\s*pm\s*\.\s*require\s*\(\s*"""
    r"""(?P<q>['"])(?P<spec>npm:[^'"]+)(?P=q)\s*\)""",
)


def scan_npm_require_variables(script: str) -> dict[str, str]:
    """Map variable names to ``npm:…`` specifiers from ``pm.require`` assignments."""
    out: dict[str, str] = {}
    for m in _PM_REQUIRE_VAR_RE.finditer(script):
        out[m.group("var")] = m.group("spec")
    return out


def types_dir_for_specifier(workspace: Path, types_spec: str) -> Path | None:
    """Return the cached ``@types`` package directory under *workspace*, if present."""
    body = types_spec.removeprefix("npm:")
    if "@" not in body:
        return None
    pkg = body.rsplit("@", 1)[0]
    deno_root = workspace / "node_modules" / ".deno"
    if not deno_root.is_dir():
        return None
    matches = sorted(deno_root.glob(f"**/node_modules/{pkg}"))
    for candidate in matches:
        if candidate.is_dir():
            return candidate
    return None


def extract_members_from_types_dir(types_dir: Path) -> list[str]:
    """Collect plausible method/property names from all ``.d.ts`` files under *types_dir*."""
    members: set[str] = set()
    for path in types_dir.rglob("*.d.ts"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.debug("read %s: %s", path, exc)
            continue
        for m in _DTS_MEMBER_RE.finditer(text):
            name = m.group(1)
            if name not in _SKIP_MEMBER_NAMES and not name.startswith("_"):
                members.add(name)
    return sorted(members)


def members_for_pm_require_spec(
    workspace: Path,
    spec: PmRequireSpec,
    *,
    prefix: str = "",
) -> list[str]:
    """Return member labels for *spec* from cached ``@types``, filtered by *prefix*."""
    types_spec = npm_types_specifier(spec)
    if not types_spec:
        return []
    types_dir = types_dir_for_specifier(workspace, types_spec)
    if types_dir is None:
        return []
    labels = extract_members_from_types_dir(types_dir)
    if prefix:
        lower = prefix.lower()
        labels = [label for label in labels if label.lower().startswith(lower)]
    return labels


def members_for_npm_specifier(
    workspace: Path,
    npm_spec: str,
    *,
    prefix: str = "",
) -> list[str]:
    """Parse *npm_spec* (``npm:lodash`` or ``npm:lodash@1.2.3``) and return member labels."""
    body = npm_spec.removeprefix("npm:")
    if "@" in body:
        name, _, ver = body.partition("@")
    else:
        name, ver = body, ""
    spec = PmRequireSpec("npm", name, ver)
    return members_for_pm_require_spec(workspace, spec, prefix=prefix)


__all__ = [
    "extract_members_from_types_dir",
    "members_for_npm_specifier",
    "members_for_pm_require_spec",
    "scan_npm_require_variables",
    "types_dir_for_specifier",
]
