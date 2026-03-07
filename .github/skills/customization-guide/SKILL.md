---
name: customization-guide
description: "How to create, update, or debug Copilot instruction files, skills, applyTo patterns, and YAML frontmatter. Use when adding a new instruction file, creating a new skill, updating the customization structure, or troubleshooting why instructions or skills are not loading."
---

# Copilot customization guide

How to create and manage custom instructions (`.instructions.md`) and
agent skills (`SKILL.md`) for the Postmark project.

## When to use instructions vs skills

| Feature | Custom instructions | Agent skills |
|---------|-------------------|--------------|
| **Location** | `.github/instructions/` | `.github/skills/<name>/` |
| **Filename** | `*.instructions.md` | `SKILL.md` |
| **Loading** | Always-on for matching `applyTo` glob | On-demand when description matches prompt |
| **Best for** | Core rules, conventions, hard constraints | Reference material, step-by-step guides, catalogues |
| **Context cost** | Loaded into every matching request | Only loaded when relevant |

**Rule of thumb:** If an LLM needs the information for *every* code change
in a file pattern, it belongs in instructions.  If it only needs it for
*specific tasks* (e.g. "add a new widget", "debug signals"), it belongs in
a skill.

## Creating a new instruction file

1. Create the file in `.github/instructions/`:

   ```
   .github/instructions/my-topic.instructions.md
   ```

2. Add YAML frontmatter with `applyTo` glob:

   ```yaml
   ---
   name: "My Topic"
   description: "Brief description of what rules this covers"
   applyTo: "src/my-module/**/*.py"
   ---
   ```

3. Write concise, imperative rules.  Start with a "Quick rules" section.

4. Register the new file in `copilot-instructions.md`:

   ```markdown
   | [my-topic.instructions.md](./instructions/my-topic.instructions.md) | `src/my-module/**/*.py` |
   ```

5. Run `python scripts/check_md_links.py` to verify links.

### Instruction file guidelines

- Keep instructions lean — they are loaded into *every* request.
- Use imperative tone ("Do X", "Never Y").
- Start with numbered "Quick rules" for the most critical constraints.
- Include code examples for patterns that are easy to get wrong.
- Never duplicate rules across instruction files.

## Creating a new skill

1. Create a directory under `.github/skills/`:

   ```
   .github/skills/my-skill/
   ```

2. Create the `SKILL.md` file with YAML frontmatter:

   ```yaml
   ---
   name: my-skill
   description: >-
     Detailed description of what this skill does and when Copilot should
     use it.  Include trigger phrases like "Use when adding new X" or
     "Use when debugging Y".
   ---
   ```

3. Write the skill body in Markdown.  Include:
   - Step-by-step procedures
   - Code templates and examples
   - Reference tables
   - Checklists

4. Optionally add supplementary files (scripts, examples) in the same
   directory.

### Skill naming conventions

- Directory name: lowercase, hyphens for spaces (e.g. `signal-flow`)
- `name` in frontmatter: must match directory name
- `description`: be specific about when it should trigger — this is what
  Copilot uses to decide whether to load the skill

### Skill description tips

The `description` field is critical — it determines when the skill gets
loaded.  Include:

- **What** the skill does
- **When** to use it (trigger phrases)
- **Keywords** a user might mention in their prompt

**Good:**
```yaml
description: >-
  Complete signal flow diagrams and wiring map for the Postmark codebase.
  Use when wiring new signals, debugging signal connections, adding new
  UI actions, or understanding how data flows between widgets.
```

**Bad:**
```yaml
description: Signal documentation
```

## Existing structure

### Instructions (always-on)

| File | Applies to | Content |
|------|------------|---------|
| `copilot-instructions.md` | All files | Project overview, tree, validation |
| `architecture.instructions.md` | `src/**/*.py` | Core rules, layering, contracts |
| `pyside6.instructions.md` | `src/ui/**/*.py` | Qt conventions, enums, QSS |
| `testing.instructions.md` | `tests/**/*.py` | Fixture patterns, test layers |
| `sqlalchemy.instructions.md` | `src/database/**/*.py` | ORM patterns, sessions |

### Skills (on-demand)

| Skill | Trigger |
|-------|---------|
| `signal-flow` | Wiring signals, debugging connections, understanding data flow |
| `service-repository-reference` | Adding service/repo methods, looking up API |
| `widget-patterns` | Creating widgets, delegates, popups, background workers |
| `test-writing` | Writing new tests for any layer |
| `import-parser` | Adding new import format support |
| `customization-guide` | Adding new instructions or skills |

## Mandatory sync after changes

After modifying any instruction or skill file, follow the checklist in
`copilot-instructions.md` under "CRITICAL — Keeping instructions in sync".

After modifying any `.md` file, run:

```bash
python scripts/check_md_links.py
```
