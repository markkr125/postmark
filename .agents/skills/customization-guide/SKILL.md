---
name: customization-guide
description: "How to create, update, or debug root and nested AGENTS.md files, .agents/skills, and project agent conventions. Use when adding a new agent instruction file, creating a new skill, or troubleshooting how instructions are discovered."
---

# Agent customization guide

How to create and manage **nested `AGENTS.md` files** and **on-demand skills**
(`.agents/skills/<name>/SKILL.md`) for the Postmark project.

## When to use nested AGENTS.md vs skills

| Feature | Nested `AGENTS.md` | Agent skills |
|---------|-------------------|--------------|
| **Location** | Repo root (`AGENTS.md`) or under a subtree (e.g. `src/ui/AGENTS.md`) | `.agents/skills/<name>/` |
| **Filename** | `AGENTS.md` | `SKILL.md` |
| **Loading** | Agents merge root + nearest nested files along the path to edited files | Read when the task matches the skill `description` (listed in root `AGENTS.md`) |
| **Best for** | Core rules per directory tree | Reference material, step-by-step guides, catalogues |
| **Context cost** | Included whenever working under that subtree | Only when relevant |

**Rule of thumb:** If an agent needs the information for *every* change under a
directory (e.g. all UI code), put it in `src/ui/AGENTS.md`. If it only applies
to *specific tasks* (e.g. "add a widget", "debug signals"), put it in a skill.

## Creating nested agent instructions

1. Add or extend **`AGENTS.md`** in the directory whose code the rules belong to:

   ```
   src/ui/AGENTS.md       # UI / PySide6 conventions
   src/database/AGENTS.md # SQLAlchemy / repository conventions
   src/AGENTS.md          # Cross-cutting architecture under src/
   tests/AGENTS.md        # Pytest / fixture conventions
   docs/AGENTS.md         # Documentation authoring rules
   ```

2. Plain Markdown is enough — no glob metadata. Scope is defined by **where the file lives**
   (nested files merge with the root `AGENTS.md`).

3. Write concise, imperative rules. Start with a "Quick rules" section.

4. Register the file in **root [`AGENTS.md`](../../../AGENTS.md)** (nested files + sync checklist tables).

5. Run `poetry run python scripts/check_md_links.py` to verify links.

### Nested file guidelines

- Keep files lean — they apply whenever editing under that tree.
- Use imperative tone ("Do X", "Never Y").
- Start with numbered "Quick rules" for the most critical constraints.
- Never duplicate rules across files — link to the canonical nested file instead.

## Creating a new skill

1. Create a directory under `.agents/skills/`:

   ```
   .agents/skills/my-skill/
   ```

2. Create `SKILL.md` with YAML frontmatter:

   ```yaml
   ---
   name: my-skill
   description: >-
     Detailed description of what this skill does and when an agent should
     read it. Include trigger phrases like "Use when adding new X" or
     "Use when debugging Y".
   ---
   ```

3. Write the skill body in Markdown — procedures, templates, tables, checklists.

4. Add the skill to the **skills table** in root [`AGENTS.md`](../../../AGENTS.md).

### Skill naming conventions

- Directory name: lowercase, hyphens (e.g. `signal-flow`).
- `name` in frontmatter: matches folder name.
- `description`: tells humans and agents **when** to open this file.

## Existing structure

### Nested `AGENTS.md` (merged by path)

| File | Scope |
|------|-------|
| [`AGENTS.md`](../../../AGENTS.md) | Project-wide — overview, architecture tree, validation gate |
| [`src/AGENTS.md`](../../../src/AGENTS.md) | Architecture & data flow for `src/` |
| [`src/ui/AGENTS.md`](../../../src/ui/AGENTS.md) | PySide6 / UI |
| [`src/database/AGENTS.md`](../../../src/database/AGENTS.md) | SQLAlchemy / DB |
| [`tests/AGENTS.md`](../../../tests/AGENTS.md) | Testing |
| [`docs/AGENTS.md`](../../../docs/AGENTS.md) | Docs authoring |

### Skills (on-demand)

| Skill | Trigger |
|-------|---------|
| `signal-flow` | Signals, wiring, data flow |
| `service-repository-reference` | Repository/service APIs, TypedDicts |
| `widget-patterns` | Widgets, delegates, workers |
| `test-writing` | New tests |
| `import-parser` | New import format |
| `customization-guide` | Changing agent layout |

## Mandatory sync after changes

After modifying any `AGENTS.md`, skill, or linked doc, follow the checklist in
root [`AGENTS.md`](../../../AGENTS.md) under **CRITICAL — Keeping instructions in sync**.

After modifying any `.md` file, run:

```bash
poetry run python scripts/check_md_links.py
```
