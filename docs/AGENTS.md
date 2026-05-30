# Documentation Authoring Rules

## Quick rules

1. **Plain text diagrams only** — use ASCII box-and-arrow art or indented
   trees.  No Mermaid, PlantUML, or image dependencies.
2. **Relative links** — all cross-references use relative paths
   (`../architecture/overview.md`).  Never absolute filesystem paths.
3. **One heading-1 per file** — the `# Title` at the top is the page title.
   Use `##` and below for sections.
4. **Code blocks specify a language** — always use fenced blocks with a
   language tag (` ```python `, ` ```bash `, ` ```text `).
5. **Function signatures use Python style** — show full type annotations,
   default values, and return types.
6. **No duplicated rules** — if a rule lives in a project `AGENTS.md` file,
   link to it instead of repeating it.  Docs are *descriptive*, agent
   instructions are *prescriptive*.
7. **Keep files under 400 lines** — split large pages into sub-pages and
   link from a parent page.

## Audience

Every documentation page must be useful for **both** audiences:

- **Human developers** — clear prose, examples, motivation/context.
- **AI agents** — structured headings, complete function signatures,
  grep-friendly identifiers, explicit cross-references.

## When to update docs

Update the relevant `docs/` pages whenever you:

- Add, rename, or remove a public function, class, or method.
- Add, rename, or remove a signal declaration.
- Add, rename, or remove a TypedDict.
- Change the architecture (new layer, new sub-package, moved files).
- Add a new widget, dialog, panel, or popup.
- Add or change an import parser, auth type, or snippet language.
- Change data flow or signal wiring.

## Diagram conventions

Use indented text trees for hierarchies:

```text
MainWindow
  +-- LeftSidebar      (left rail + stacked flyout: collections / environments | local scripts)
  +-- RequestEditor   (centre-left)
  +-- ResponseViewer   (centre-right)
  +-- RightSidebar     (right rail)
```

Use ASCII arrows for sequences:

```text
User clicks Send
  --> MainWindow._on_send()
    --> HttpSendWorker.run()  [QThread]
      --> HttpService.send_request()
        --> httpx.Client.request()
      <-- HttpResponseDict
    <-- finished signal(dict)
  --> ResponseViewer.display_response()
```

## Link conventions

Relative paths must be computed from the *current file*, not from
`docs/`. Count the directories between the doc and its target:

- Top-level page (`docs/foo.md`) → target
  ``../src/services/collection_service.py`` from `docs/foo.md`.
- Sub-directory page (`docs/architecture/foo.md`,
  `docs/scripting/foo.md`, `docs/guides/foo.md`) → target
  ``../../src/services/collection_service.py``.
- Sibling doc page from a sub-directory → use one `..` segment per
  directory (e.g. ``../architecture/overview.md``).
- Same-directory doc page → bare filename (e.g. ``overview.md`` in the
  same folder).
- Architecture agent instructions: ``../src/AGENTS.md`` from a
  top-level `docs/` page, or ``../../src/AGENTS.md`` from a nested
  `docs/` sub-page.

## Script runtime docs

- [architecture/script-runtime.md](architecture/script-runtime.md) — script subprocess lifecycle, IPC, permissions.
- [guides/adding-script-language.md](guides/adding-script-language.md) — recipe for adding a third scripting language.
- [scripting/external-packages.md](scripting/external-packages.md) — `pm.require` for npm / jsr / PyPI; vendored allowlist.
