r"""Snippet loader — read declarative JSON from ``data/snippets/<lang>.json``.

This module is the single entry point for snippet *data*.  The UI popover
(``ui.widgets.snippets.popup``) calls :func:`load_snippets` and
:func:`has_snippets`; editors never read the filesystem directly.

File layout
===========
Each language is one JSON file::

    data/snippets/javascript.json
    data/snippets/python.json
    …

The basename (without ``.json``) must match the string returned by the
``language`` property on :class:`~ui.widgets.code_editor.editor_widget.CodeEditorWidget`
for that editor mode (lowercase, e.g. ``javascript``, ``python``).

Adding a new language
=====================
1. Add ``data/snippets/<language>.json`` where ``<language>`` matches
   ``CodeEditorWidget.language`` (e.g. ``go``).
2. Follow the JSON schema below; keep ``name`` and ``body`` fields for each
   snippet row.
3. Restart the application.  No Python changes are required for the loader
   to discover the new file.

JSON schema (overview)
======================
::

    {
      "language": "<language>",
      "categories": [
        {
          "name": "Category name",
          "snippets": [
            { "name": "Snippet title", "body": "code\\nwith newlines" }
          ]
        }
      ]
    }

Keys whose names start with an underscore (``_``) are **ignored** everywhere
in the document — see ``data/snippets/README.md``.  They exist so JSON files
can carry comments (JSON has no native comment syntax).

Field semantics
---------------
- ``language`` (str, optional): sanity label; not strictly validated in v1.
- ``categories`` (list): ordered groups.  Empty snippet lists are skipped.
- ``categories[].name`` (str): shown as a **non-selectable** bold header row.
- ``categories[].snippets[].name`` (str): visible label for a pickable row.
- ``categories[].snippets[].body`` (str): inserted **verbatim** at the editor
  cursor when the row is activated; newlines are preserved.

Caching
-------
:func:`load_snippets` is wrapped in ``functools.lru_cache`` (per resolved
language key).  Files are read at most once per process lifetime.  Editing a
JSON file on disk requires an app restart to pick up changes.

TypeScript fallback
-------------------
Editor language ``typescript`` resolves to the same file as ``javascript``
(``javascript.json``) because Postmark runs TS through the same Deno/JS
bootstrap as JavaScript at the ``pm.*`` API boundary.  There is no separate
``typescript.json`` in v1.

Worked example — add ``go``
---------------------------
1. Create ``data/snippets/go.json`` with ``categories`` and snippets.
2. Teach the code editor to report ``language == "go"`` when that mode is
   added.
3. The snippets toolbar button enables automatically when the file exists
   and :func:`has_snippets` returns true.

See Also:
---------
``data/snippets/README.md`` — author-facing runbook and acceptance checklist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Snippet:
    """One pickable snippet row (display name plus insertable body)."""

    name: str
    body: str


@dataclass(frozen=True)
class SnippetCategory:
    """A category header and an ordered tuple of snippets.

    ``contexts`` filters where the category appears in the popover:
    ``"pre"`` for pre-request scripts, ``"post"`` for post-response
    scripts. An empty tuple means show in every context (default for
    back-compat when the JSON omits the field).
    """

    name: str
    snippets: tuple[Snippet, ...]
    contexts: tuple[str, ...] = ()


def _data_dir() -> Path:
    """Return ``<repo>/data/snippets``."""
    return Path(__file__).resolve().parents[4] / "data" / "snippets"


def _resolve_language(language: str) -> str:
    """Map editor language codes to snippet file basenames."""
    lang = (language or "").lower().strip()
    if lang == "typescript":
        return "javascript"
    return lang


def _strip_underscore_keys(obj: dict) -> dict:
    """Return a shallow copy of *obj* with all ``_``-prefixed keys removed.

    Underscore-prefixed keys (e.g. ``_comment``) are reserved for inline
    JSON metadata that the loader must ignore. The behaviour is contractual
    — see ``data/snippets/README.md``.
    """
    return {k: v for k, v in obj.items() if not k.startswith("_")}


@lru_cache(maxsize=8)
def load_snippets(language: str) -> tuple[SnippetCategory, ...]:
    """Load and parse snippets for *language*; empty tuple if missing or invalid."""
    fname = _resolve_language(language) + ".json"
    path = _data_dir() / fname
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(raw, dict):
        return ()
    raw = _strip_underscore_keys(raw)
    cats_raw = raw.get("categories") or []
    if not isinstance(cats_raw, list):
        return ()
    out: list[SnippetCategory] = []
    for c_raw in cats_raw:
        if not isinstance(c_raw, dict):
            continue
        c = _strip_underscore_keys(c_raw)
        snips_raw = c.get("snippets") or []
        if not isinstance(snips_raw, list):
            continue
        snips_list: list[Snippet] = []
        for s_raw in snips_raw:
            if not isinstance(s_raw, dict):
                continue
            s = _strip_underscore_keys(s_raw)
            name = str(s.get("name", "") or "")
            body = str(s.get("body", "") or "")
            if not name or not body:
                continue
            snips_list.append(Snippet(name=name, body=body))
        snips = tuple(snips_list)
        if not snips:
            continue
        cat_name = str(c.get("name", "") or "")
        ctx_raw = c.get("contexts") or ()
        if isinstance(ctx_raw, list):
            contexts = tuple(str(x) for x in ctx_raw if isinstance(x, str))
        else:
            contexts = ()
        out.append(SnippetCategory(name=cat_name, snippets=snips, contexts=contexts))
    return tuple(out)


def has_snippets(language: str) -> bool:
    """Return whether any snippet rows exist for *language* (after TS fallback)."""
    return bool(load_snippets(language))


def load_snippets_for(language: str, script_type: str) -> tuple[SnippetCategory, ...]:
    """Filter :func:`load_snippets` by editor *script_type*.

    Maps ``script_type`` (``"pre_request"`` / ``"test"``) to a
    category context tag (``"pre"`` / ``"post"``). Categories without
    a ``contexts`` field are shown in every context (back-compat).
    """
    ctx = "pre" if script_type == "pre_request" else "post"
    return tuple(c for c in load_snippets(language) if not c.contexts or ctx in c.contexts)
