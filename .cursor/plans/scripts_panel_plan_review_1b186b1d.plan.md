---
name: Scripts panel plan review
overview: "Superseded — use the canonical merged plan at [.cursor/plans/local-script-modules-full-plan.md](local-script-modules-full-plan.md) (full multi-PR spec + amendments)."
todos: []
isProject: false
---

# Superseded

This short review has been **folded into** the adopted Cursor plan:

**[local-script-modules-full-plan.md](local-script-modules-full-plan.md)**

That file contains the **entire** original specification (resolver, JS/Python runtimes, left pane, Scripts panel, module tabs, tests, verification) plus inline amendments:

- Collections-parity Scripts header (+ New, Refresh, search) and folder tree (§5.0–§5.0b).
- `NewScriptModulePopup` mirroring `NewItemPopup` (§5.0b).
- Full pre/post script editor surface reuse for module tabs, including Output, Problems, LSP, undo/redo (§6.0); §6.1 sample marked illustrative-only.

Use the YAML `todos` in that file’s frontmatter as the PR checklist.
