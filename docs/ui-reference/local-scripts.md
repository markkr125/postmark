# Local scripts (UI)

The **Local scripts** left flyout hosts a collection tree for reusable script modules. Centre-pane tabs edit one script at a time with the same advanced editor stack as request **Scripts** (Run, Debug, Problems, output panel).

Source: `src/ui/collections/collection_widget.py` (`variant="local_scripts"`), `src/ui/local_scripts/local_script_editor_widget.py`, `src/ui/request/request_editor/scripts/script_editor_pane/`.

## What is local-only vs shared with request scripts

Not everything in Postmark scripting is limited to local script tabs. This page focuses on the **Local scripts** UI, but several editor features are shared:

| Feature | Local script tab | Request / folder Scripts tab |
|---------|------------------|------------------------------|
| Sidebar tree + `local_script` centre tabs | Yes | No (collections/requests tree instead) |
| **Run** / **Debug** open file as ESM **entry** + import closure | Yes | No (inline run / send pipeline for that request) |
| Relative `import './sibling.js'` between tree files | Yes (JS/TS) | No |
| Auto-suggest inside `import '…'` / `export … from '…'` | Yes (JS/TS) | No |
| Ctrl+click relative `import` path → open sibling tab | Yes | No |
| **`pm.require('local:…')` path auto-suggest** | Yes | **Yes** |
| **`pm.require('npm:…')` / `jsr:` / PyPI** | Yes | Yes |
| LSP, snippets, breakpoints, Problems tab (per editor) | Yes | Yes |

**Consuming** local modules from a request always uses `pm.require('local:path')` — request scripts cannot `import` from the local tree. **Authoring** a multi-file local project uses `import` (and optionally `pm.require`) inside **local script** tabs only.

```javascript
// Request → Tests tab: load local code by path (completion works here too)
const fmt = pm.require('local:utils/format.js');

// Local script tab: link siblings with import (completion + Ctrl+click here only)
import { formatId } from '../utils/format.js';
```

## Sidebar tree

Open the left rail **code** icon to show the local-scripts tree. `MainWindow` installs `CollectionWidget(variant="local_scripts")` on that flyout page.

| Action | How |
|--------|-----|
| New script or folder | **+ New** on the tree header (JavaScript, TypeScript, Python, CommonJS, folder) |
| Open script | Click a script leaf — opens a `local_script` tab |
| Rename / move | Context menu or inline rename (paths and `import` / `pm.require` refs rewrite on save) |

Example tree layout (virtual paths mirror folder/script names):

```text
Local scripts
├── utils/
│   ├── format.js          →  utils/format.js
│   └── ids.ts             →  utils/ids.ts
├── auth/
│   └── token.js           →  auth/token.js
└── main.test.js           →  main.test.js   ← open this tab to Run/Debug as entry
```

See also [Sidebar](sidebar.md) for flyout layout.

## Editor pane

`LocalScriptEditorWidget` wraps `ScriptEditorPane` with syntax highlighting, folding, LSP (when enabled), snippets, **Run**, **Debug**, and **Problems**.

### Linking modules with `import`

In a **local script** tab (JS/TS), use relative paths between siblings. The editor auto-suggests paths while you type inside the string:

```javascript
// main.js — cursor after './' triggers sibling list (mapper.js, ../utils/format.js, …)
import { mapUser } from './mapper.js';
import { formatId } from '../utils/format.js';

export function runChecks() {
  return { user: mapUser({ id: 1 }), id: formatId(1) };
}
```

```javascript
// mapper.js — library module (no pm.test required)
export function mapUser(row) {
  return { id: row.id, label: String(row.id) };
}
```

Most local files are **shared libraries** like `mapper.js`. Request **Tests** tabs are where you usually assert on a live `pm.response` after **Send**; see [Request editor](request-editor.md).

**Ctrl+click** (or go-to-definition) on `'./mapper.js'` opens `mapper.js` in a new centre tab.

Auto-suggest applies to one-line forms only, for example:

```javascript
import { x } from './partial…'   // suggests ./mapper.js, ./other.ts, …
export { y } from '../utils/…'
import './side-effect.js'
```

It does **not** apply to dynamic or multi-line specifiers:

```javascript
const mod = await import('./lazy.js');  // no path popup
```

### `pm.require("local:…")` inside local scripts

Postman-style paths still work when you prefer a string path over `import`:

```javascript
const { mapUser } = pm.require('local:mapper.js');
// Typing inside pm.require('local:…') uses the same path completion as request scripts
```

### Request scripts vs local script tabs

**Request** and **folder** script editors do **not** get ESM `import` auto-suggest. They load local code via `pm.require` only:

```javascript
// Pre-request script on a request tab (not a local script tab)
const helpers = pm.require('local:utils/format.js');
pm.variables.set('formatted', helpers.formatId(42));
```

| Where you edit | Relative `import` + auto-suggest | `pm.require("local:…")` |
|----------------|-----------------------------------|-------------------------|
| Local script tab | Yes (JS/TS) | Yes |
| Request / folder Scripts tab | No | Yes |

### `pm.test` in local scripts (optional)

`pm.test` / `pm.expect` **do run** when you click **Run** on a local script tab — the same `pm` bootstrap as request scripts. Pass/fail rows appear in the output panel under **Output** (not a separate request **Test Results** tab on a response).

| | Local script tab | Request **Tests** tab |
|--|------------------|------------------------|
| `pm.test` executes on **Run** | Yes | Yes (inline run or after **Send**) |
| Assert on `pm.response` from last **Send** | Only if you **Send** from a request tab or use `pm.sendRequest` | Yes (typical) |
| Test gutter icons in editor | No (`enable_test_gutter=False`) | Yes |
| Data-driven **Iterations** matrix | No | Yes (post-response + data file) |

Example — smoke-test a local module in isolation (no HTTP response unless you add `pm.sendRequest`):

```javascript
// smoke.test.js — open this tab, click Run
import { mapUser } from './mapper.js';

pm.test('mapUser shape', () => {
  pm.expect(mapUser({ id: 1 })).to.eql({ id: 1, label: '1' });
});
```

Use **Snippets → Tests** for assertion templates. For production checks on a real API response, keep `pm.test` on the request **Tests** tab and call shared logic via `pm.require('local:…')`.

### Run and Debug (entry module)

**Run** and **Debug** always treat the **currently open** local file as the entry module. Postmark loads its static `import` graph and any `pm.require` dependencies, then executes that file.

```javascript
// main.js — with this tab focused, Run executes THIS file first
import { mapUser } from './mapper.js';
console.log(mapUser({ id: 1 }));
```

```javascript
// mapper.js alone — open only this tab and Run → mapper.js is the entry (main.js is not run)
export function mapUser(row) {
  return { id: row.id, label: String(row.id) };
}
```

Use **Debug** the same way: breakpoints in the open file and in imported modules are honored for that entry run.

### Problems tab

**Problems** lists LSP diagnostics for the entry file and for other files in the import closure, even if those tabs are not open. Rows for dependency files are prefixed with the virtual path:

```text
[utils/format.js] 'foo' is declared but never used.
main.test.js:3:10 — Cannot find module './typo.js'.
```

Click a row to jump to the script tab and line when the file is in the closure.

### npm / jsr (same editor, union closure)

From a local script tab you can also use Deno-style specifiers; **Run** / **Problems** include them in the union scan:

```javascript
import { assertEquals } from 'jsr:@std/assert@0.224.0';
import lodash from 'npm:lodash@4.17.21';

pm.test('uses npm', () => {
  assertEquals(lodash.clone({ a: 1 }).a, 1);
});
```

Details: [Local script modules](../scripting/local-modules.md), [External packages](../scripting/external-packages.md).

## Related docs

- [Local script modules](../scripting/local-modules.md) — ESM project model, mirror, cycles, limits
- [External packages](../scripting/external-packages.md) — `pm.require` npm/jsr/PyPI
