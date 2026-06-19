# App wiki (in-app user knowledge base)

Maintainer guide for the Postmark user KB consumed by `postmark_wiki_query`.

## Layers

| Layer | Path | Role |
|-------|------|------|
| User source | [`user-guide/`](../user-guide/) | Canonical end-user how-to (step-by-step UI language) |
| Scripting prose | Allowlisted [`scripting/`](../scripting/) pages | `pm.*` API reference read live by the tool |
| Generated | [`data/app-wiki/`](../../data/app-wiki/) | `index.md`, `WIKI.md`, `scripting-api/*-quickref.md` |

There is **no `raw/` byte-copy**. Sources are clean markdown; the tool reads them in place.

## Rebuild

```bash
poetry run python scripts/build_app_wiki.py
python scripts/check_md_links.py
```

Commit updated `data/app-wiki/` with user-guide or allowlisted scripting changes.

## API quickref source

Quickref pages are generated from `data/lsp/stubs/pm.d.ts` and `pm.pyi` — **not**
from `pm_api_schema.py` (that schema is shallow for the linter). Prose API pages
remain the deep narrative.

## Editing rules

See [`user-guide/AGENTS.md`](../user-guide/AGENTS.md) for tone, grouping, and tidiness.
