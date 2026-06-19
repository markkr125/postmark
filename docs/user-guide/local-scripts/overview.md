# Local scripts overview

Author multi-file JavaScript, TypeScript, or Python modules once and reuse them from any request script.

## Open the tree

1. Click the **Local scripts** icon on the **left rail**.
2. Browse folders and script files like a small project tree.

## Create files

1. Click **+ New** on the tree header.
2. Choose **JavaScript**, **TypeScript**, **Python**, **JavaScript (CommonJS)**, or **Folder**.
3. Name the file or folder and confirm.

Double-click or click a script leaf to open a centre tab with the full script editor (Run, Debug, Snippets, Problems).

## Link modules inside local scripts

In a **local script** tab (JS/TS), use ESM imports between siblings:

```javascript
import { formatId } from "../utils/format.js";
```

The editor suggests paths while you type inside the string. **Ctrl+click** a relative path to open the target tab.

## Use local code from a request

Request **Scripts** tabs cannot `import` from the local tree. Load modules with:

```javascript
const fmt = pm.require("local:utils/format.js");
```

Path completion works here too.

## Run and debug as entry

1. Open a local script tab (often a test or main file).
2. Click **Run** to execute that file as the entry point (includes its import closure).
3. Click **Debug** for breakpoints and step-through — same debugger as request scripts.

## Rename and move

Renaming or moving a file updates `import` paths and `pm.require('local:…')` references where Postmark can rewrite them statically.

## CommonJS (.cjs)

**JavaScript (CommonJS)** files use `.cjs` paths. Consume from ESM request scripts with:

```javascript
const helper = pm.require("local:legacy/helper.cjs");
```

## Related

- [Local scripts hub](README.md)
- [External packages (JavaScript)](../scripting/javascript/external-packages.md)
- [Snippets](../scripting/snippets.md)
