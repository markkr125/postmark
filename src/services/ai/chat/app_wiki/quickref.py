"""Generate compact scripting API quickref pages from LSP stubs."""

from __future__ import annotations

import re
from pathlib import Path

from database.data_paths import project_root
from services.ai.chat.app_wiki.config import app_wiki_root
from services.ai.chat.app_wiki.sandbox_globals import globals_for_language

_PM_DTS = Path("data/lsp/stubs/pm.d.ts")
_PM_PYI = Path("data/lsp/stubs/pm.pyi")


def _parse_pm_dts(text: str) -> list[str]:
    """Extract dotted member paths from ``pm.d.ts``."""
    members: list[str] = []
    namespace_stack: list[str] = ["pm"]
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("namespace "):
            name = line.split()[1].rstrip(" {")
            members.append(".".join([*namespace_stack, name]))
            namespace_stack.append(name)
            continue
        if line == "}":
            if len(namespace_stack) > 1:
                namespace_stack.pop()
            continue
        fn = re.match(r"function (\w+)", line)
        if fn:
            members.append(".".join([*namespace_stack, fn.group(1)]))
        const = re.match(r"const (\w+)", line)
        if const:
            members.append(".".join([*namespace_stack, const.group(1)]))
    return sorted(set(members))


def _parse_pm_pyi(text: str) -> list[str]:
    """Extract ``pm.*`` member paths from ``pm.pyi`` (flat ``_Pm`` class)."""
    members: list[str] = []
    in_pm_class = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("class _Pm"):
            in_pm_class = True
            members.append("pm")
            continue
        if in_pm_class and line.startswith("class "):
            in_pm_class = False
        if not in_pm_class:
            continue
        fn = re.match(r"def (\w+)", line)
        if fn:
            members.append(f"pm.{fn.group(1)}")
            continue
        attr = re.match(r"(\w+):\s*Any", line)
        if attr and attr.group(1) not in {"args", "kwargs"}:
            members.append(f"pm.{attr.group(1)}")
    return sorted(set(members))


def _quickref_body(language: str, members: list[str], note: str = "") -> str:
    """Format a quickref markdown page."""
    lines = [
        f"# {language.title()} `pm` API quick reference",
        "",
        "Generated from LSP stubs by ``scripts/build_app_wiki.py``. "
        "For narratives and examples see "
        "[JavaScript API](../../../docs/scripting/javascript-api.md) or "
        "[Python API](../../../docs/scripting/python-api.md).",
        "",
    ]
    if note:
        lines.append(note)
        lines.append("")
    lines.append("## `pm` members")
    lines.append("")
    for member in members:
        lines.append(f"- `{member}`")
    lines.append("")

    helpers = globals_for_language(language)
    if helpers:
        lines.append("## Global helpers (call WITHOUT a `pm.` prefix)")
        lines.append("")
        lines.append(
            "These are top-level builtins in the script sandbox — e.g. "
            "`datetime_now()`, not `pm.datetime_now()`."
        )
        lines.append("")
        for name, signature, doc in helpers:
            lines.append(f"- `{name}{signature}` — {doc}")
        lines.append("")
    return "\n".join(lines)


def write_scripting_quickrefs(root: Path | None = None) -> list[Path]:
    """Write javascript and python quickref files; return paths written."""
    repo = root or project_root()
    out_dir = app_wiki_root(repo) / "scripting-api"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    dts_path = repo / _PM_DTS
    if dts_path.is_file():
        js_members = _parse_pm_dts(dts_path.read_text(encoding="utf-8"))
        js_out = out_dir / "javascript-quickref.md"
        js_out.write_text(
            _quickref_body(
                "javascript",
                js_members,
                "TypeScript uses the same `pm` surface; types are stripped at run time.",
            ),
            encoding="utf-8",
        )
        written.append(js_out)
        ts_out = out_dir / "typescript-quickref.md"
        ts_out.write_text(
            _quickref_body(
                "typescript",
                js_members,
                "Identical to JavaScript — optional type annotations only.",
            ),
            encoding="utf-8",
        )
        written.append(ts_out)

    pyi_path = repo / _PM_PYI
    if pyi_path.is_file():
        py_members = _parse_pm_pyi(pyi_path.read_text(encoding="utf-8"))
        py_out = out_dir / "python-quickref.md"
        py_out.write_text(
            _quickref_body(
                "python",
                py_members,
                "Python scripts also accept camelCase aliases (e.g. `pm.collectionVariables`).",
            ),
            encoding="utf-8",
        )
        written.append(py_out)

    return written
