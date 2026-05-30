# Local script modules (ESM project)

Local script tabs (centre pane) behave like a small Deno/TypeScript project:

- Use standard `import` / `export` between files under the **Local scripts** tree.
- **Run** and **Debug** execute the open file as the **entry module** and load its static import graph (plus any `pm.require("local:…")` dependencies).
- **LSP** uses mirrored `file://` paths under the JS workspace `local/` directory (not ephemeral `_buffer_<uuid>` buffers).
- On **first open** of a local script tab, mirror/index/closure prep runs on a background thread so the editor appears immediately; `did_open` and Problems/completions settle shortly after (when prep and the Deno LSP bucket are ready). Later opens reuse warm caches.
- **Problems** on the entry tab aggregates diagnostics for unopened files in the import closure (path label prefix).

Request and folder scripts are unchanged: they still use `pm.require("local:…")` only (no relative `import` into `local/`).

## Prefer `import` between local scripts

```javascript
import { mapUser } from "./mapper.js";

pm.test("maps", () => {
  pm.expect(mapUser({ id: 1 })).to.eql({ id: 1, label: "1" });
});
```

`pm.require("local:folder/script")` remains valid inside local scripts when you need the Postman-style path string.

## Mirror and workspace

On startup and after DB mutations, JS/TS scripts are mirrored to:

`<deno-workspace>/local/<virtual-path>`

`sync_all` prunes orphan mirror files. Ambient `pm` / `postman` types come from `ambient_pm.d.ts` (generated from `stubs/pm.d.ts`) and `compilerOptions.types` in the workspace `deno.json` — no per-buffer triple-slash preamble when that file is present.

## Rename / move

Renaming or moving a script or folder rewrites:

- `pm.require("local:…")` literals (all persisted scripts and request/folder script JSON)
- Static relative `import` / `export … from` specifiers in local script bodies

Non-literal dynamic `import("…")` and bare CommonJS `require("./…")` calls are **not** rewritten; fix those manually (another reason to prefer static `import` for cross-script links).

## Navigating between modules

- **Ctrl+click** (or go-to-definition) on a relative `import` path opens the sibling local script in a centre-pane tab. Resolution uses the static import graph (`navigation.resolve_esm_import_target_script_id`).
- While typing a relative import path (`import { x } from './`), the editor offers **auto-suggest** of sibling `.js` / `.ts` / `.cjs` files (same deterministic source as the path list, not Deno LSP module completion). Auto-suggest covers static `import` / `export … from '…'` and side-effect `import '…'` on one line only — not dynamic `import("…")` or multi-line specifiers.

## npm / jsr imports

Local scripts may use Deno-native specifiers:

```javascript
import { assertEquals } from "jsr:@std/assert";
import lodash from "npm:lodash";
```

`pm.require("npm:…")` and `pm.require("jsr:…")` remain valid. Both styles feed the **union** closure scan used for Run/Debug, Problems aggregation, and type indexing.

## `.cjs` files (CommonJS)

CommonJS local scripts (`.cjs` virtual paths) are **leaf modules** in the supported graph: define their exports with `module.exports` and consume them from an ESM sibling with `import`.

`mathHelpers.cjs`:

```javascript
function add(a, b) {
  return a + b;
}
module.exports = { add };
```

Entry script (`.js` / `.ts`) that imports it:

```javascript
import helpers from "./mathHelpers.cjs";

pm.test("adds", () => {
  pm.expect(helpers.add(2, 3)).to.equal(5);
});
```

**Linking rules for `.cjs`:**

- `pm.require("local:…")` inside a `.cjs` is **rejected** (raises at resolve time) — use `module.exports` and import the module from an ESM script instead.
- Bare CommonJS `require("./sibling.cjs")` **executes at runtime** (Deno's CommonJS compatibility resolves it, and every local script is mirrored to disk), but it is **not a supported linking mechanism**: it is not tracked in the Run/Debug import closure and gets no editor tooling — no go-to-definition / Ctrl+click, no import auto-suggest, and it is **not** rewritten when you rename or move the target, so the link silently breaks. Prefer ESM `import` for cross-script links.
- Do not put ESM `import` / `export` inside a `.cjs` file: Deno treats `.cjs` as CommonJS, so that syntax fails at runtime.

## Cycles and limits

- **ESM `import` closure:** circular relative imports are **allowed** — each module is included once in the closure and not re-walked; Deno runs the cycle at runtime.
- **`pm.require("local:…")`:** import cycles **raise** at resolve time.
- **Both:** the reachable closure is capped at `MAX_LOCAL_MODULES` (= 500).

## Python local scripts

Python locals are not part of the JS mirror. Use `pm.require("local:…py")` from request/folder hosts only.
