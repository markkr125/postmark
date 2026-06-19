# Scripting runtimes

Configure Deno and Python paths, language servers, and editor behaviour for all script editors.

## Steps

1. Open **File → Settings…** → **Scripting**.

## Deno (JavaScript and TypeScript)

| Control | Purpose |
|---------|---------|
| Path field | Custom `deno` executable, or leave empty for auto-detect |
| **Download Deno** | Install a managed copy when none is found |
| Status line | Shows whether the current path is valid |

Deno is required for JavaScript, TypeScript, and the preferred Python (Pyodide) path.

## Python

| Control | Purpose |
|---------|---------|
| Path field | Optional custom Python for fallback subprocess runtime |
| Status line | Validation message |

When Pyodide assets are present, Python scripts prefer the Deno+WASM runtime.

## Editor options

| Option | Effect |
|--------|--------|
| **Enable language servers (LSP)** | Completions, diagnostics, go-to-definition in script editors |
| **Format on save** | Auto-format script source when saving local scripts or requests |

## Reset LSP caches

Use **Reset LSP workspace caches** if completions or npm/jsr types look stale after changing registries or `pm.require` specs.

## Open from script banner

When a script editor shows a Deno missing banner, click **Open Scripting settings** to jump here directly.

## Related

- [Choosing a language](../scripting/choosing-a-language.md)
- [Private packages](private-packages/README.md)
