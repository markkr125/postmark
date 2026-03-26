---
applyTo: "docs/**/*.md"
---
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
6. **No duplicated rules** — if a rule lives in a Copilot instruction file,
   link to it instead of repeating it.  Docs are *descriptive*, instructions
   are *prescriptive*.
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
  +-- CollectionWidget (left sidebar)
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

- Link to source files as relative paths from `docs/`:
  `[collection_service.py](../../src/services/collection_service.py)`.
- Link to other doc pages: `[Architecture Overview](../../docs/architecture/overview.md)`.
- Link to Copilot instructions:
  `[architecture.instructions.md](architecture.instructions.md)`.
