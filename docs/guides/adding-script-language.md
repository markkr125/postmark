# Adding a script language

This guide is for contributors (or AI agents) adding a third scripting
language to Postmark on top of the existing JavaScript and Python paths.

## Decision tree

| If you need...                              | Do this                                                                |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| Exact Postman parity                        | Use the existing JS path. Don't fork it.                               |
| Python with PyPI                            | Already done. See [Pyodide path](../architecture/script-runtime.md).   |
| A different language (Ruby, Lua, Tcl, ...)  | Follow the recipe below.                                               |
| Native code with arbitrary syscalls         | Don't. Pick a host that sandboxes (Deno + WASM, container, ...).       |

## Required surface for a new language runtime

Every runtime must satisfy this contract:

1. A static method
   `XRuntime.execute(script: str, context: ScriptInput) -> ScriptOutput`
   that the engine can call.
2. A subprocess that consumes `pm.*` context (bundle interpolation OR
   stdin JSON), runs the user script, and emits one `__done__` JSON
   envelope on stdout.
3. A sandbox boundary enforced by the host (Deno permissions, WASM,
   container, ...).
4. A bundle / preamble exposing the standard `pm.*` API:
   - `pm.variables`, `pm.environment`, `pm.collectionVariables`,
     `pm.globals`
   - `pm.request`, `pm.response`, `pm.cookies`, `pm.iterationData`,
     `pm.execution`
   - `pm.test`, `pm.expect`, `pm.sendRequest`, `pm.require`
   - `console.log` / `.warn` / `.error` / `.info`

   Names match across languages; method shapes use idiomatic casing for
   the target language.

## Step-by-step recipe

1. **Pick a runtime host.** Deno (good for any WASM-shippable language),
   a system interpreter, or a container. Inherit a manager file shape:
   [src/services/scripting/deno_manager.py](../../src/services/scripting/deno_manager.py)
   is the template for download-on-first-use hosts.

2. **Write the bundle / preamble.** Mirror
   [data/scripts/pm_bootstrap.js](../../data/scripts/pm_bootstrap.js)
   (or [data/scripts/pm_bootstrap.py](../../data/scripts/pm_bootstrap.py)
   for a Python-shaped target).

3. **Write the runtime caller.** Mirror
   [src/services/scripting/deno_runtime.py](../../src/services/scripting/deno_runtime.py)
   or
   [src/services/scripting/pyodide_runtime.py](../../src/services/scripting/pyodide_runtime.py):
   `XRuntime.execute`, `_build_bundle_text`, `_ipc_subprocess`,
   `_apply_done_line`, error helpers. Reuse the JSON-serialisable
   `pm.*` context shape.

4. **Wire `pm.require`** (if external packages apply). Add a detector
   regex over `pm.require('...')` literals, build a bundle-time package
   list, widen permissions to exactly the registry hosts the language
   needs, set up a cache directory, and provide a runtime shim that
   consults a registry the host injected (e.g.
   `globalThis.__pm_require_modules` in JS).

5. **Lock down permissions.** Default-deny network. Open exactly the
   registry hosts the language needs. `--no-prompt` (or equivalent)
   always on. Never grant blanket fs writes outside the cache.

6. **Hook into the engine.** Add a dispatch branch in
   [src/services/scripting/engine.py](../../src/services/scripting/engine.py)
   keyed off `language`.

7. **Add a debug variant** if the language has a debugger.
   [src/services/scripting/debug/deno_debug.py](../../src/services/scripting/debug/deno_debug.py)
   is the template (V8 inspector via `--inspect-brk`).

8. **Update [src/services/scripting/runtime_settings.py](../../src/services/scripting/runtime_settings.py)**
   with `validate_<language>` and path discovery helpers.

## Worked example: Ruby via mruby in a sandboxed subprocess

Files a contributor would create (names match the JS / Python pattern):

```text
data/scripts/pm_bootstrap.rb              # ruby pm.* preamble
data/scripts/mruby_run.sh                 # spawn helper, JSON IPC bridge
src/services/scripting/mruby_runtime.py   # MRubyRuntime.execute
src/services/scripting/mruby_manager.py   # download / cache mruby binary
tests/unit/services/test_mruby_runtime.py
src/ui/widgets/code_editor/completion/schema/rb.py
```

Touch points:

- Add `"ruby"` dispatch in `engine.py`.
- Add `validate_mruby` in `runtime_settings.py`.
- Register the language in
  [src/ui/request/request_editor/scripts/scripts_mixin.py](../../src/ui/request/request_editor/scripts/scripts_mixin.py).
- Wire `set_language("ruby")` in
  [src/ui/widgets/code_editor/completion/engine.py](../../src/ui/widgets/code_editor/completion/engine.py)
  to load `RB_SCHEMA`.

## Autocomplete schema

Each language has a `<LANG>_SCHEMA` dict in
[src/ui/widgets/code_editor/completion/schema/](../../src/ui/widgets/code_editor/completion/schema/)
consumed by [completion/engine.py](../../src/ui/widgets/code_editor/completion/engine.py)
`CompletionEngine.set_language`.

To add a language:

1. Create `src/ui/widgets/code_editor/completion/schema/<lang>.py`.
2. Define `<LANG>_SCHEMA`, `<LANG>_GLOBALS`, `<LANG>_KEYWORDS`, and the
   full `pm.*` tree (mirror `js.py` and `py.py`).
3. Wire `CompletionEngine.set_language(lang)` to load the new schema.

## UI integration

The language menu is in
[src/ui/request/request_editor/scripts/scripts_mixin.py](../../src/ui/request/request_editor/scripts/scripts_mixin.py).
Add a new entry; ensure `set_language` cascades to the highlighter, the
validator, and the completion engine.

## Testing checklist

- Bundle build is deterministic (no embedded timestamps; sorted lists
  where order doesn't matter).
- Subprocess exits cleanly on every error path.
- `__done__` is always emitted (even on uncaught exceptions).
- Cache directory is reused across runs.
- First run with network and second run offline both succeed.
- Existing JS and Python tests still pass.
- Autocomplete schema test enforces presence of new top-level entries.

## Common pitfalls

- Forgetting to add new permission flags conditionally — either
  over-grants or breaks offline runs.
- Letting the bundle include unsanitised user input that breaks the
  JSON context. Use `json.dumps(default=str)` (existing escape hatch).
- Wrong cache directory on Windows. `LOCALAPPDATA` is the right base.
- Hard-coding a CDN URL. Vendor locally instead — see how Pyodide is
  bundled under [data/scripts/vendor_pyodide/](../../data/scripts/vendor_pyodide/).
- Missing `--no-prompt`. Deno will block on a permission prompt with no
  way to answer.
