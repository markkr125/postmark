# User Guide — Agent Instructions

Prescriptive rules for editing [`docs/user-guide/`](README.md). Read this file
before changing any page in this tree.

## Audience

- **End users** of the Postmark desktop app — not contributors or codebase maintainers.
- Write **numbered steps** with exact UI labels: **New (+)**, **Send**, **Scripts** tab,
  **File → Settings…** (`Ctrl+,`), **View → Toggle Console** (`Ctrl+J`).
- **Do not** cite `src/` paths, Python class names, signals, `objectName`, or
  repository functions unless the string appears in the UI.

## Scripting split

| Content | Location |
|---------|----------|
| Tutorials and UI workflows | `user-guide/scripting/` |
| `pm.*` API member reference | [`docs/scripting/`](../scripting/) (prose API pages) |
| Generated API quickref | [`data/app-wiki/scripting-api/`](../../data/app-wiki/scripting-api/) (run `build_app_wiki.py`) |

Link both tutorials and API pages from each language `README.md`.

## Where to put new content

| Change | Update |
|--------|--------|
| New button/menu in an existing area | The **leaf page** for that workflow |
| New user-facing sidebar section | New **subfolder** + `README.md` + leaf page(s); add row to root [`README.md`](README.md) |
| Settings control added/changed | `settings/` — match the Settings dialog tree (see [`settings/README.md`](settings/README.md)) |
| New `pm.*` member | [`pm_api_schema.py`](../../src/services/scripting/pm_api_schema.py), prose [`docs/scripting/*-api.md`](../scripting/), run `build_app_wiki.py` |
| JS-only scripting behavior | `scripting/javascript/` |
| Python-only behavior | `scripting/python/` |
| TypeScript typing tips | `scripting/typescript/` (same runtime as JS) |
| Applies to all languages | Shared page under `scripting/` |

## Tidiness checklist (every edit)

1. File lives in the correct **section subfolder** (not `user-guide/` root except `README.md` and this file).
2. Parent **`README.md`** lists every leaf with a one-line blurb.
3. Root [`README.md`](README.md) lists every section hub in app-navigation order.
4. Remove orphans when features are removed.
5. Merge overlapping pages; leave a redirect link on the hub.
6. Use **relative links** only.
7. Run `poetry run python scripts/build_app_wiki.py` and commit `data/app-wiki/`.
8. Run `python scripts/check_md_links.py`.

## Page template

```markdown
# Short task title

One paragraph: what the user can accomplish.

## Steps

1. Click **…** in …

## Related

- [Sibling task](environments/variables.md)
```

Use plain-text indented trees for layout diagrams — **no Mermaid** in user-guide pages.
