# Updating Documentation

How to keep documentation in sync with code changes.

## When to Update

Update docs whenever you:

- Add, change, or remove a public API method
- Add or modify signals
- Add or change TypedDicts
- Add new widgets or change widget structure
- Add new parsers or auth types
- Change architectural patterns or data flows

## Sync Checklist

After any code change, review and update:

1. **Architecture tree** in `copilot-instructions.md` — add new files,
   remove deleted files
2. **`architecture.instructions.md`** — new signals, data flows,
   TypedDicts, service methods
3. **`pyside6.instructions.md`** — new `objectName` values used in QSS
4. **`testing.instructions.md`** — new test files or directories
5. **`sqlalchemy.instructions.md`** — new models, relationships,
   repository functions
6. **Skills** (`.github/skills/`) — signals, services, TypedDicts,
   widgets, parsers
7. **Instruction files** — stale references to renamed or deleted code
8. **Docs pages** — affected API reference, UI reference, or guide pages

## Which Docs Pages to Update

| Change | Pages to Update |
|--------|-----------------|
| New repository function | `api-reference/database/*.md` |
| New service method | `api-reference/services/*.md` |
| New TypedDict | `api-reference/typedicts.md` |
| New signal | `api-reference/signals.md` |
| New widget | `ui-reference/*.md` |
| New parser | `api-reference/services/import-parsers.md`, `guides/adding-import-parser.md` |
| New auth type | `api-reference/services/auth-handler.md`, `guides/adding-auth-type.md` |
| Architecture change | `architecture/*.md` |
| New test pattern | `guides/writing-tests.md`, `contributing/testing-guide.md` |

## Doc Authoring Rules

Full rules are in `.github/instructions/documentation.instructions.md`.
Key points:

- **Plain text diagrams** — use ASCII box/arrow diagrams, never
  Mermaid or PlantUML
- **Relative links** — link between docs pages with relative paths
- **No inline colours** — reference `theme.py` palette slots by name
- **Audience** — write for both human developers and AI agents

## Link Checking

After any documentation change, run:

```bash
python scripts/check_md_links.py
```

This verifies all internal cross-references between docs pages.

## File Naming

- Use kebab-case: `adding-import-parser.md`, not `addingImportParser.md`
- Match the source module name where practical
- Group by topic area under the appropriate subdirectory

## Template for New Pages

```markdown
# Page Title

One-paragraph summary of what this page covers.

Source: `src/path/to/module/`

## Section

Content with tables, code blocks, and text diagrams as needed.
```
