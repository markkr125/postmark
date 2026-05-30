# Local script modules (`pm.require("local:…")`) + left-pane toggle row

This document is the **complete** implementation plan: it is a verbatim copy of the original multi-PR specification (historically `we-need-a-much-fluffy-glade.md`, 2046 lines) with **inline amendments** merged so nothing was removed. Amendments fix internal contradictions and add UI/editor requirements agreed in review (Collections-parity Scripts header, `NewItemPopup`-style **Create New** for modules, full script surface reuse clarified in §6.0). If a paragraph below is labeled **(Amended)** or a subsection **5.0a**, it **supersedes** any conflicting sentence in the same section that was left for traceability.

## Context

Postman ships **Package Library** (cloud-only, JS-only, no composition, owner-locked, no Newman, no git, no PyPI). We beat it by making reusable scripts **local files on disk**.

A user drops a file like `auth-helpers.js` under one workspace folder. From any request pre/post script they call `pm.require("local:auth-helpers.js")` and get the module. Files are git-friendly, diffable, editable with LSP. Local modules can also import each other and import `npm:` / `jsr:` / PyPI packages.

**UI shape**: the **existing left sidebar pane gets a horizontal icon toggle row added at its top**. Two compact icon buttons sit in that row: **Collections** (active by default — shows the existing tree) and **Scripts** (shows the **folder-grouped module tree** described in §5.-1 — not a flat list). Clicking swaps the content below via a `QStackedWidget`. This is the Cursor IDE pattern (per Cursor community docs: "Cursor has a distinctive design where the row of icons on the primary sidebar are arranged **horizontally** rather than vertically like VS Code").

**What is and isn't changing in the left pane slot:**
- The main `QSplitter` keeps the **same slot** for the left sidebar that `collection_widget` occupies today. **Width, position, and behavior unchanged.**
- The slot's content widget becomes a tiny new wrapper (`LeftSidebarPane`) that owns: (a) the horizontal toggle row, and (b) a `QStackedWidget` holding the existing `CollectionWidget` (page 0) and a new `ScriptsPanel` (page 1).
- `CollectionWidget` is **untouched** — same class, same tree, same header buttons. It just becomes page 0 of the stack.

### UI anti-patterns (a prior implementation attempt failed by violating these)

- **NO new splitter pane / column / section.** The left sidebar slot count stays the same as today.
- **NO `QDockWidget`** anywhere for the Scripts panel. Scripts is a page inside the same left sidebar pane.
- **NO vertical activity rail** on the far-left edge of the window. The toggle row is **horizontal** and lives **inside** the existing left pane.
- **NO separate top-level menu items / shortcuts** that bypass the toggle row. `Ctrl+1` / `Ctrl+2` call the toggle row's `set_active_panel(name)` method like the icons do.
- **NO modifications to `CollectionWidget`'s internal layout.** It enters the stack as-is.
- **NO read-only ScriptsPanel.** The panel must let users create / rename / delete modules from inside the app (**primary header actions + context menu** — see §5.0a; a compact secondary toolbar remains acceptable for power actions). Without that the feature is unusable; a prior implementation made exactly this mistake.
- **NO iconless toggle row.** Both toggle buttons in §4 must have an icon (Phosphor font via `phi()`). Icon-only or icon+text — pick one, but never label-only.
- **NO new code editor for script-module tabs.** Script-module tabs use the **same entire script editor surface** as pre/post-request scripts (not only `CodeEditorWidget`): toolbar with Find/Replace/Go to line, **Undo/Redo**, Save, status bar, vertical splitter, `ScriptOutputPanel` with **Output + Problems**, LSP wiring — see §6.0. The bare `CodeEditorWidget`-only sample in §6.1 is **illustrative** of persistence hooks; the shipped tab must call the extracted `build_script_editor_surface(..., script_type="module")` from §6.0.

**Out of scope** (do not implement, even if related): per-collection-scoped modules; "Extract to module" refactor; where-used panel; snippet palette integration for `local:` (defer until shape stabilises); hot reload; TypeScript `.d.ts` autogen; in-app test runner for modules; cross-language imports (JS calling Python or vice versa); **RestrictedPython subprocess support for `local:` Python modules** (Pyodide-only — RestrictedPython path explicitly errors out); **standalone "Run" button for module files** (modules are imported by request scripts; they have no entry point on their own — Output panel exists for chrome parity but stays inactive). LSP **is in scope** — wired via the same auto-attach path the scripts editor uses today.

**Scope expansion vs prior plan revisions**: **subdirectories are now supported** under the local-modules root. Specifier accepts a relative path (e.g. `pm.require("local:utils/jwt.js")`). The Scripts panel displays a tree grouped by folder, matching the visual pattern of the collections tree.

---

## Composition story (resolver + bundle)

**Critical**: a local module can call `pm.require("npm:...")`, `pm.require("jsr:...")`, `pm.require("local:other")` (JS) or `pm.require("pkg==X.Y.Z")`, `pm.require("local:other")` (Python). The user script's static scan would miss specifiers that only appear inside reachable local modules.

**Rule**: registry/PyPI specifier detection runs as a **union scan over the user source PLUS the source of every transitively reachable local module**.

Order of operations for each runtime path:
1. `LocalModuleResolver.resolve_required(user_source, language=...)` → builds `{name: LocalModule}` map (transitive closure with cycle detection).
2. Collect specifiers via `_detect_pm_require_specs(user_source + "\n" + "\n".join(local_sources))` (JS) or the Python equivalent.
3. Build bundle / IPC payload with the union of specifiers + the resolved local modules.

This is the only design that makes the composition example in Verification step 7 actually pass.

## Specifier rules

Form: **extension is mandatory; relative path is allowed**. Accepted shapes:

- JS: `pm.require("local:<path>.js")` or `pm.require("local:<path>.ts")`
- Python: `pm.require("local:<path>.py")`

Where `<path>` is one or more `/`-separated segments. Examples:
```
pm.require("local:jwt.js")              // top-level file
pm.require("local:utils/jwt.js")        // one subfolder deep
pm.require("local:auth/oauth/google.ts") // nested
pm.require("local:helpers/shout.py")    // Python under helpers/
```

Rules:
- Each segment matches `^[A-Za-z0-9_][\w.-]*$` (JS) / `^[A-Za-z_][A-Za-z0-9_]*$` (Python — segments are Python identifiers so the loader can register dotted names like `utils.jwt`).
- **No `..`, no leading `/`, no `@scope/`, no version, no Windows backslashes.** Reject these at parse time.
- The extension **must match a file on disk** at the resolved path. If only `utils/jwt.ts` exists, `pm.require("local:utils/jwt.js")` is a "not found" error.
- Path **must resolve under the configured local-modules root** — resolver enforces `resolve(strict=True)` + `relative_to(root)` (same traversal guard as before).
- The same file may be referenced by exactly one path; there's no implicit barrel/index resolution.

Why extension-mandatory:
- Matches Deno / ESM / Python import convention — fewer surprises.
- No silent-ambiguity class possible at the call site.

Why allow subdirectories:
- Users with many modules want logical grouping (`auth/`, `utils/`, `validators/`) like collections.
- The Scripts panel (§5) renders the tree visually, matching the collections-tree pattern.

The `local:` prefix cannot collide with `npm:` / `jsr:` / bare PyPI names.

---

## File system layout

- Root folder, default: `<user_data_dir>/postmark/scripts/`
  - Linux: `~/.local/share/postmark/scripts/`
  - macOS: `~/Library/Application Support/postmark/scripts/`
  - Windows: `%LOCALAPPDATA%\postmark\scripts\`
- Use the same per-OS resolver as [DenoManager.runtime_dir()](../../src/services/scripting/deno_manager.py) (see lines around 80-90 of that file).
- **(Amended)** The tree and resolver **recurse into subdirectories** under this root (see §1.1 `LocalModuleResolver.discover()`, specifier rules above, and §5.-1). Ignore the older “top-level only” MVP sentence — it contradicted the rest of this document.
- Auto-create the folder when read for the first time (`mkdir(parents=True, exist_ok=True)`).

---

## Section 1 — Resolver and settings (PR 1)

### 1.1 — New file `src/services/scripting/local_modules.py`

Create this file. Add the constants, dataclass, and class below verbatim.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal

MAX_LOCAL_MODULES = 500
ALLOWED_EXTS = {".js", ".ts", ".py"}
EXT_TO_LANGUAGE: dict[str, Literal["javascript", "typescript", "python"]] = {
    ".js": "javascript",
    ".ts": "typescript",
    ".py": "python",
}

ScanFn = Callable[[str], Iterable[str]]


@dataclass(frozen=True)
class LocalModule:
    name: str
    language: Literal["javascript", "typescript", "python"]
    path: Path
    source: str = ""  # populated by resolve_required(); empty after discover()


class LocalModuleResolver:
    """Discovers and validates local script modules under a root.

    Walks subdirectories recursively. Modules are keyed by their relative
    POSIX path (e.g. ``"utils/jwt.js"``, not just ``"jwt"``).
    """

    def __init__(self, root: Path | None = None) -> None:
        from services.scripting.runtime_settings import RuntimeSettings
        self._root = (root or RuntimeSettings.local_modules_dir()).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def discover(self) -> dict[str, LocalModule]:
        """Recursive scan. Returns ``{rel_posix_path: LocalModule(source="")}``.

        Keys look like ``"jwt.js"`` for top-level files or
        ``"utils/jwt.js"`` for nested ones (forward-slash separator, always).
        Raises ValueError on cap exceeded or unsafe paths.
        """
        modules: dict[str, LocalModule] = {}
        for entry in sorted(self._root.rglob("*")):
            if not entry.is_file():
                continue
            if entry.suffix not in ALLOWED_EXTS:
                continue
            if not self._is_safe(entry):
                continue
            rel = entry.relative_to(self._root)
            # Reject hidden dirs / files anywhere in the path (e.g. ``.git/``).
            if any(part.startswith(".") for part in rel.parts):
                continue
            key = rel.as_posix()
            modules[key] = LocalModule(
                name=key,
                language=EXT_TO_LANGUAGE[entry.suffix],
                path=entry,
                source="",
            )
            if len(modules) > MAX_LOCAL_MODULES:
                raise ValueError(f"too many local modules (> {MAX_LOCAL_MODULES})")
        return modules

    def resolve_required(
        self,
        user_source: str,
        scan_specs: ScanFn,
        language: Literal["javascript", "python"],
    ) -> dict[str, LocalModule]:
        """Transitive closure of ``local:`` requires.

        ``scan_specs(source)`` yields **relative POSIX paths with extension**
        (e.g. ``"utils/jwt.js"``). Returns ``{rel_path: LocalModule}`` with
        ``source`` populated. Raises ValueError on cycles, missing modules,
        unsafe paths, or cross-language imports.
        """
        available = self.discover()
        same_lang = {
            "javascript": {"javascript", "typescript"},
            "python": {"python"},
        }[language]
        reachable: dict[str, LocalModule] = {}

        def visit(rel: str, chain: tuple[str, ...]) -> None:
            # Cheap path-shape rejection before any disk lookup.
            if (".." in rel.split("/")) or rel.startswith("/") or "\\" in rel:
                raise ValueError(f"pm.require: unsafe local path {rel!r}")
            if rel in chain:
                raise ValueError(f"local module cycle: {' -> '.join((*chain, rel))}")
            if rel in reachable:
                return
            mod = available.get(rel)
            if mod is None:
                raise ValueError(
                    f"pm.require: local module {rel!r} not found in {self._root}"
                )
            if mod.language not in same_lang:
                raise ValueError(
                    f"pm.require: local module {rel!r} is {mod.language}; "
                    f"cannot be imported from {language}"
                )
            src = mod.path.read_text(encoding="utf-8")
            reachable[rel] = mod.with_source(src)
            for inner in scan_specs(src):
                visit(inner, (*chain, rel))

        for n in scan_specs(user_source):
            visit(n, ())
        return reachable

    def _is_safe(self, p: Path) -> bool:
        """Rejects anything whose resolved real path escapes root.

        ``self._root`` is already ``resolve()``d in ``__init__`` so both
        sides of ``relative_to`` are canonical (no symlink-in-the-root
        edge case). ``p.resolve(strict=True)`` follows symlinks; if the
        target lives outside the canonical root, ``relative_to`` raises.
        """
        try:
            resolved = p.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError):
            return False
        try:
            resolved.relative_to(self._root)
        except ValueError:
            return False
        return True
```

Acceptance criteria:
- `discover()` lists only top-level `.js`/`.ts`/`.py` files.
- Two files `foo.js` + `foo.ts` → raises.
- > 500 files → raises.
- Symlink whose target is outside root → not included.
- File named `../escape.js` (via os call, not panel) → not included.

### 1.2 — Modify `src/services/scripting/runtime_settings.py`

Use the module's existing `_get_settings()` helper (line 128) — **do not** call `QSettings()` directly: that would write to a different namespace and break test isolation.

Find the block of `_KEY_*` constants. Add:

```python
_KEY_LOCAL_MODULES_DIR = "scripting/local_modules_dir"
```

Add these methods to `RuntimeSettings` (style copied from `deno_path()` / `set_deno_path()`):

```python
@staticmethod
def local_modules_dir() -> Path:
    s = _get_settings()
    raw = str(s.value(_KEY_LOCAL_MODULES_DIR, "") or "")
    p = Path(raw).expanduser() if raw else _default_local_modules_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p

@staticmethod
def set_local_modules_dir(p: Path) -> None:
    s = _get_settings()
    s.setValue(_KEY_LOCAL_MODULES_DIR, str(p))
```

For the default path, **reuse the existing per-OS helper used by `DenoManager.runtime_dir()`** (see [src/services/scripting/deno_manager.py](../../src/services/scripting/deno_manager.py) around lines 80-90). Either:
- Extract that helper into a shared module function (`_user_data_dir() -> Path`) and call it from both, or
- Make `_default_local_modules_dir()` import `DenoManager` and use its base dir.

Preferred: extract a small `_postmark_user_data_dir() -> Path` shared helper to avoid Windows/Linux drift. Add it in `runtime_settings.py`:

```python
def _postmark_user_data_dir() -> Path:
    """Returns the OS data dir base used across the scripting layer.
    Single source of truth; DenoManager.runtime_dir() should delegate here too.
    """
    import os, sys
    if sys.platform.startswith("linux"):
        base = Path(os.environ.get("XDG_DATA_HOME") or "~/.local/share").expanduser()
    elif sys.platform == "darwin":
        base = Path("~/Library/Application Support").expanduser()
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or "~/AppData/Local").expanduser()
    else:
        base = Path("~/.local/share").expanduser()
    return base / "postmark"


def _default_local_modules_dir() -> Path:
    return _postmark_user_data_dir() / "scripts"
```

If `DenoManager.runtime_dir()` already inlines this logic, also refactor it to call `_postmark_user_data_dir()` in the same PR — single source of truth.

Acceptance:
- `RuntimeSettings.local_modules_dir()` returns a `Path` that exists on disk.
- Setting a custom path persists across app restarts (verified by writing, dropping the `_get_settings()` reference, re-reading via a fresh `_get_settings()` instance).

### 1.3 — Tests `tests/unit/services/test_local_modules_resolver.py`

New file. Cases:
1. `test_default_dir_created` — `RuntimeSettings.local_modules_dir()` exists after call.
2. `test_discover_returns_js_ts_py_only` — drop `.txt`, `.md` files: not included.
3. `test_discover_skips_subdirs` — file inside a subfolder is not returned.
4. `test_discover_ambiguous_name_raises` — both `foo.js` and `foo.ts` → ValueError.
5. `test_discover_cap_raises` — create 501 files → ValueError.
6. `test_discover_rejects_symlink_outside_root` — symlink `link.js → /etc/passwd` not in result.
7. `test_resolve_required_transitive_js` — file A requires B; user script requires A → both in result.
8. `test_resolve_required_cycle_raises` — A requires B, B requires A → ValueError with cycle message.
9. `test_resolve_required_missing_raises` — user requires `local:missing` → ValueError naming missing.
10. `test_resolve_required_cross_language_raises` — Python user requires JS module → ValueError.

### 1.4 — Tests `tests/unit/services/test_runtime_settings.py` (extend)

Add:
- `test_local_modules_dir_default` — unset → returns default per-OS path under `postmark/scripts/`.
- `test_local_modules_dir_roundtrip` — set then get returns the same path.
- `test_local_modules_dir_autocreates` — getter creates the folder.

PR 1 ships once the resolver tests and settings tests pass. No UI, no runtime change.

---

## Section 2 — JS runtime `local:` support (PR 2)

### 2.1 — Modify `src/services/scripting/js_runtime.py`

**Specifier shape (extension mandatory)**: `pm.require("local:<stem>.js")` or `pm.require("local:<stem>.ts")`. Two regexes — keep registry detection clean:

```python
_PM_REQUIRE_REGISTRY_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]"""
    r"""(?P<reg>npm|jsr):(?P<name>@?[\w./-]+?)"""
    r"""(?:@(?P<ver>[^'"]+))?['"]\s*\)""",
)
# Local: accepts one or more segments separated by ``/``. Each segment must
# start with a letter/underscore/digit and contain only word chars / dots / dashes.
# No ``..``, no leading ``/``, no backslashes.
_PM_REQUIRE_LOCAL_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]local:"""
    r"""(?P<path>[A-Za-z0-9_][\w.-]*(?:/[A-Za-z0-9_][\w.-]*)*)\.(?P<ext>js|ts)"""
    r"""['"]\s*\)""",
)
_NPM_NAME_RE = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*(/[\w./-]+)?$", re.IGNORECASE)
_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-+][\w.\-+]+)?$")
```

`PmRequireSpec` keeps three fields. For `local:` entries: `name` holds the **relative POSIX path without extension** (e.g. `"utils/jwt"`); `version` holds the suffix (`.js` / `.ts`). For registry entries: same as before (package name + version).

```python
class PmRequireSpec(NamedTuple):
    registry: str       # "npm" | "jsr" | "local"
    name: str           # package (npm/jsr) or stem path "utils/jwt" (local)
    version: str        # version (npm/jsr) or ".js"/".ts" suffix (local)

    @property
    def rel_path(self) -> str:
        """Relative POSIX path with extension (``local:`` only)."""
        assert self.registry == "local"
        return f"{self.name}{self.version}"

    @property
    def specifier(self) -> str:
        if self.registry == "local":
            return f"local:{self.rel_path}"
        if self.version:
            return f"{self.registry}:{self.name}@{self.version}"
        return f"{self.registry}:{self.name}"

    @property
    def ident(self) -> str:
        """Safe identifier suffix for generated ``__pm_req_*`` symbols.

        Slashes and dots collapse to underscores so ``utils/jwt.js`` becomes
        ``utils_jwt_js``.
        """
        if self.registry == "local":
            raw = f"local_{self.name}_{self.version.lstrip('.')}"
        else:
            raw = f"{self.registry}_{self.name}_{self.version or 'latest'}"
        return re.sub(r"[^A-Za-z0-9_]", "_", raw)
```

`_detect_pm_require_specs` runs both regexes:

```python
def _detect_pm_require_specs(script: str) -> list[PmRequireSpec]:
    seen: dict[tuple[str, str, str], PmRequireSpec] = {}
    for m in _PM_REQUIRE_REGISTRY_RE.finditer(script):
        reg, name, ver = m.group("reg"), m.group("name"), m.group("ver") or ""
        if not _NPM_NAME_RE.match(name):
            raise ValueError(f"pm.require: invalid {reg} package name {name!r}")
        if ver and not _EXACT_VERSION_RE.match(ver):
            raise ValueError(
                f"pm.require: version must be exact (got {ver!r}). "
                "Ranges and tags like '^1.0' or 'latest' are not supported."
            )
        seen[(reg, name, ver)] = PmRequireSpec(reg, name, ver)
    for m in _PM_REQUIRE_LOCAL_RE.finditer(script):
        path, ext = m.group("path"), m.group("ext")
        suf = f".{ext}"
        seen[("local", path, suf)] = PmRequireSpec("local", path, suf)
    return list(seen.values())


def _iter_pm_require_local_paths(source: str) -> Iterable[str]:
    """Yield unique local **relative paths with extension** for the resolver.

    e.g. ``"jwt.js"``, ``"utils/jwt.js"``.
    """
    seen: set[str] = set()
    for m in _PM_REQUIRE_LOCAL_RE.finditer(source):
        rel = f"{m.group('path')}.{m.group('ext')}"
        if rel not in seen:
            seen.add(rel)
            yield rel
```

**Modify** `_pm_require_imports_block` (currently around line 148). Local file layout in the bundle workdir mirrors the disk tree under a `local/` subfolder so relative imports resolve naturally:

```
workdir/
├── bundle.mjs                  ← the user-script bundle
├── local/
│   ├── jwt.js                  ← copied from <root>/jwt.js
│   ├── utils/
│   │   └── jwt.js              ← copied from <root>/utils/jwt.js
│   └── auth/
│       └── oauth/
│           └── google.ts
```

So the emitted static import is `from "./local/utils/jwt.js"`. No file-renaming, no name flattening — disk path === bundle path.

```python
def _pm_require_imports_block(
    specs: list[PmRequireSpec],
    local_paths: set[str] | None = None,
) -> str:
    """Emit static ESM imports plus globalThis.__pm_require_modules registration.

    For ``local:`` specs, the caller MUST have written the source file to
    ``<workdir>/local/<rel_path>`` before invoking Deno (see ``deno_runtime``).
    ``local_paths`` is the resolved closure (set of rel POSIX paths with
    extension) — used to validate that every emitted import has a backing file.
    """
    if not specs:
        return ""
    lines: list[str] = []
    entries: list[str] = []
    local_paths = local_paths or set()
    for s in specs:
        var = f"__pm_req_{s.ident}"
        if s.registry == "local":
            rel = s.rel_path
            if rel not in local_paths:
                raise ValueError(
                    f"pm.require: local module {rel!r} is not in the resolved closure"
                )
            lines.append(f"import * as {var} from \"./local/{rel}\";")
            entries.append(f"  {json.dumps(s.specifier)}: {var}.default ?? {var}")
        else:
            lines.append(f"import * as {var} from {json.dumps(s.specifier)};")
            entries.append(f"  {json.dumps(s.specifier)}: {var}.default ?? {var}")
            bare = f"{s.registry}:{s.name}"
            if s.version and bare != s.specifier:
                entries.append(f"  {json.dumps(bare)}: {var}.default ?? {var}")
    lines.append("globalThis.__pm_require_modules = Object.assign(")
    lines.append("  globalThis.__pm_require_modules || {}, {")
    lines.append(",\n".join(entries))
    lines.append("});")
    return "\n".join(lines) + "\n"
```

### 2.2 — Modify `src/services/scripting/deno_runtime.py`

**Critical algorithm change**: registry specifier detection must scan the union of user source + every reachable local module source. Otherwise `local:auth` calling `pm.require("npm:jose@5.2.0")` would never appear in the bundle.

**Find** `_build_bundle_text` (around line 281) and `build_debug_bundle_text` (around line 321). Replace the specifier-detection step with this two-pass algorithm:

```python
from services.scripting.local_modules import LocalModuleResolver
from services.scripting.js_runtime import _iter_pm_require_local_paths

# Step 1: resolve local closure (yields paths with extension).
resolver = LocalModuleResolver()
local_mods = resolver.resolve_required(
    user_source, _iter_pm_require_local_paths, language="javascript"
)

# Step 2: union scan for registry/jsr specifiers (user + all local sources).
union_source = user_source + "\n" + "\n".join(m.source for m in local_mods.values())
specs = _detect_pm_require_specs(union_source)

# Split for emission: locals get relative file imports; npm/jsr get static imports.
registry_specs = [s for s in specs if s.registry in ("npm", "jsr")]
local_paths_set = set(local_mods.keys())
local_specs_for_emit = []
for rel in local_mods:
    # Split rel "utils/jwt.js" → name="utils/jwt", version=".js"
    base, _, ext = rel.rpartition(".")
    local_specs_for_emit.append(PmRequireSpec("local", base, f".{ext}"))

imports_block = _pm_require_imports_block(
    registry_specs + local_specs_for_emit, local_paths=local_paths_set
)

# `needs_net` derives from the SAME union-scanned specs so .npmrc + --allow-net
# stay in sync with what the bundle actually imports.
needs_net = any(s.registry in ("npm", "jsr") for s in specs)

# Canonical 3-tuple return contract.
return bundle_text, local_mods, needs_net
```

**Error policy for `_build_bundle_text`.** All failures (invalid specifier, missing local, cycle, cross-language) propagate as `ValueError` from `_build_bundle_text`. The caller (`_run_bundle`) catches and converts to `_error_output(str(exc))`. **Do not** mix `ValueError` raises with `_error_output(...)` returns inside `_build_bundle_text`.

**Find** `_run_bundle` (around line 471). Unpack the new 3-tuple; convert errors here; mirror the disk layout under `tdir/local/`:

```python
try:
    bundle_text, local_mods, needs_net = _build_bundle_text(...)
except ValueError as exc:
    return _error_output(str(exc))

with tempfile.TemporaryDirectory(prefix="postmark-deno-") as tdir:
    tdir_path = Path(tdir)
    local_root = tdir_path / "local"
    for rel, mod in local_mods.items():
        # rel is POSIX-style "utils/jwt.js" — preserves the original tree
        # so the bundle's `import "./local/utils/jwt.js"` resolves.
        dest = local_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(mod.source, encoding="utf-8")
    argv, env = deno_ipc_argv_and_env(..., needs_net=needs_net, ...)
    # ... existing bundle.mjs write, Deno spawn, etc.
```

**Verify** the `--allow-read=` argument already covers `tdir`. Look at `deno_ipc_argv_and_env` (around lines 180-225) — it should already include the workdir. If yes, no change.

**`needs_net` — single source of truth.** Today `deno_ipc_argv_and_env` derives `needs_net` from `script_for_network_scan` (the user script only). Update its signature to accept `needs_net` as an **explicit parameter** instead of recomputing internally. Remove (or gate) any internal call to `_detect_pm_require_specs(script_for_network_scan)` that derives `needs_net` from the user script alone.

**Every caller of `deno_ipc_argv_and_env` must pass the new `needs_net`** — including:
- `_run_bundle` (this PR)
- `build_debug_bundle_text` path / `deno_debug.py` callers (parity bullet below)
- Any utility helper that wraps spawn — grep with `grep -rn "deno_ipc_argv_and_env" src/` to catch them all.

**ValueError policy.** Today an invalid specifier from `_detect_pm_require_specs` may force `needs_net = True` as a safe fallback (so the run fails with a clear network-permission error rather than silently dropping the spec). Under the union scan, an invalid specifier in *any* local module must instead **fail the run upfront** via `ValueError → _error_output`. Do **not** widen network access on parse failure — surface the error.

**Interaction with private `.npmrc`** (shipped earlier): the per-execution `.npmrc` is only emitted when `needs_net` is True. With only `local:` specs, `needs_net=False` → no `.npmrc` written, no `--node-modules-dir` needed. Verify by reading the `.npmrc` emission code in `deno_ipc_argv_and_env` and gating it on the new explicit `needs_net` parameter.

**Debug bundle parity.** `build_debug_bundle_text` (line 321) and the debug code path in [src/services/scripting/debug/deno_debug.py](../../src/services/scripting/debug/deno_debug.py) must use the **same** union scan + local-file materialization + `needs_net` computation as `_build_bundle_text`. Recommended: extract the shared algorithm into a helper

```python
def _resolve_locals_and_specs(user_source: str) -> tuple[
    list[PmRequireSpec],           # union specs
    dict[str, LocalModule],        # local closure
    bool,                          # needs_net
]:
    ...
```

called from both `_build_bundle_text` and `build_debug_bundle_text`. The debug spawn path must also pass `needs_net=...` into `deno_ipc_argv_and_env`.

Acceptance for PR 2: running the same script through Send (normal) and Debug must produce identical local-module file writes and identical `needs_net` outcomes. Add a test `test_debug_bundle_matches_normal_bundle_for_local_modules`.

### 2.3 — Tests for the unified API contract

(Tests for the resolver and union-scan behavior are in §2.4 below; this section is intentionally short — error handling lives entirely in `_run_bundle`.)

### 2.4 — Tests `tests/unit/services/test_pm_require_local_js.py`

New file. Cases:
1. `test_regex_accepts_top_level_file` — `_PM_REQUIRE_LOCAL_RE.search('pm.require("local:foo.js")')` matches with `path=foo`, `ext=js`.
2. `test_regex_accepts_subdir_path` — `'pm.require("local:utils/jwt.ts")'` matches with `path=utils/jwt`, `ext=ts`.
3. `test_regex_accepts_deep_path` — `'pm.require("local:auth/oauth/google.ts")'` matches with `path=auth/oauth/google`.
4. `test_regex_rejects_local_without_extension` — `'pm.require("local:foo")'` returns no `local` specs.
5. `test_regex_rejects_local_with_version` — `'pm.require("local:foo.js@1.2.3")'` does not match.
6. `test_regex_rejects_dotdot_in_path` — `'pm.require("local:../escape.js")'` does not match (regex doesn't allow `..`).
7. `test_regex_rejects_leading_slash` — `'pm.require("local:/etc/foo.js")'` does not match.
8. `test_imports_block_emits_relative_import` — `_pm_require_imports_block([PmRequireSpec("local","utils/jwt",".ts")], local_paths={"utils/jwt.ts"})` contains `from "./local/utils/jwt.ts"`.
9. `test_imports_block_rejects_unresolved_local` — passing a spec whose path isn't in `local_paths` raises ValueError.
10. `test_build_bundle_writes_local_files_preserving_tree` — fake `local_modules_dir` with `utils/jwt.ts`. Build bundle. Assert `tdir/local/utils/jwt.ts` exists.
11. `test_transitive_local_require_resolved` — `local:utils/a.js` requires `local:utils/b.js`. User script requires `local:utils/a.js`. Both files appear under `tdir/local/utils/`.
12. `test_union_scan_picks_up_registry_specs_inside_local` — `local:auth/oauth.js` source contains `pm.require("npm:jose@5.2.0")`; user script doesn't. Bundle imports block contains `from "npm:jose@5.2.0"`.
13. `test_missing_local_returns_error_output` — script requires `local:nope.js` → `_error_output` mentions `nope`.
14. `test_extension_mismatch_returns_error_output` — only `foo.ts` on disk; script requires `local:foo.js` → error mentions mismatch.
15. `test_local_only_does_not_set_needs_net` — only `local:` specs → `needs_net` is False.
16. `test_cycle_returns_error_output` — A → B → A → `_error_output` with "cycle".
17. `test_debug_bundle_matches_normal_bundle_for_local_modules` — `_build_bundle_text` and `assemble_debug_bundle_with_meta` agree on `local_mods` + `needs_net` for path-bearing specs.
18. `test_resolver_rejects_symlink_outside_root` — symlink in a subdirectory pointing outside is excluded from `discover()`.

### 2.5 — Modify `data/scripts/pm_bootstrap.js`

Find the `pm.require` implementation (around lines 1019-1060). In the existing "module not found" error branch, add a hint for `local:` prefix:

```js
if (spec.startsWith("local:")) {
    throw new Error(
        `pm.require(${JSON.stringify(spec)}): local module not found. ` +
        `Create a file named ${spec.slice(6)}.js or ${spec.slice(6)}.ts ` +
        `in your local modules folder.`
    );
}
// existing error path for npm/jsr ...
```

PR 2 ships once `test_pm_require_local_js.py` is green and a manual JS smoke works (see Verification).

---

## Section 3 — Python runtime `local:` support (PR 3)

### 3.1 — Modify `src/services/scripting/py_runtime.py`

**Specifier shape**: `pm.require("local:<path>.py")` where `<path>` is one or more `/`-separated **Python-identifier** segments (so `importlib` can register dotted names like `__pm_local_utils.jwt`).

Add a second regex (the existing `_PM_REQUIRE_PY_RE` matches only bare PyPI names). Insert after the existing regex (line 53):

```python
_PM_REQUIRE_PY_LOCAL_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]local:"""
    r"""(?P<path>[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*)\.py"""
    r"""['"]\s*\)""",
)
```

**Modify** `_PM_REQUIRE_PY_RE` so it cannot accidentally match `local:foo.py`. Add a negative lookahead to the bare-name regex:

```python
_PM_REQUIRE_PY_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]"""
    r"""(?!local:)(?P<name>[a-z0-9][a-z0-9._-]*)"""
    r"""(?:==(?P<ver>[^'"]+))?['"]\s*\)""",
    re.IGNORECASE,
)
```

**Extend** `PmPyRequireSpec` with a `kind` field. Put `kind` first so test constructors read naturally (`PmPyRequireSpec("pip", "requests", "2.31.0")` reads better than `PmPyRequireSpec("requests", "2.31.0", "pip")`):

```python
class PmPyRequireSpec(NamedTuple):
    kind: Literal["pip", "local"]
    name: str       # PyPI package or local stem
    version: str    # version (pip only — empty for local)

    @property
    def pip_spec(self) -> str:
        if self.kind == "local":
            raise ValueError("local modules have no pip spec")
        return f"{self.name}=={self.version}" if self.version else self.name
```

**Modify** `detect_pm_require_py_specs`:

```python
def detect_pm_require_py_specs(source: str) -> list[PmPyRequireSpec]:
    seen: dict[tuple[str, str, str], PmPyRequireSpec] = {}
    for m in _PM_REQUIRE_PY_LOCAL_RE.finditer(source):
        path = m.group("path")  # e.g. "utils/jwt"
        seen[("local", path, "")] = PmPyRequireSpec("local", path, "")
    for m in _PM_REQUIRE_PY_RE.finditer(source):
        name = m.group("name").lower()
        ver = m.group("ver") or ""
        if ver and not _PY_EXACT_VERSION_RE.match(ver):
            raise ValueError(
                f"pm.require: version must be exact (got {ver!r})."
            )
        seen[("pip", name, ver)] = PmPyRequireSpec("pip", name, ver)
    return list(seen.values())


def _iter_pm_require_py_local_paths(source: str) -> Iterable[str]:
    """Yield unique local **relative paths with extension** for the resolver.

    e.g. ``"jwt.py"``, ``"utils/jwt.py"`` — matches the resolver's key format.
    """
    seen: set[str] = set()
    for m in _PM_REQUIRE_PY_LOCAL_RE.finditer(source):
        rel = f"{m.group('path')}.py"
        if rel not in seen:
            seen.add(rel)
            yield rel
```

### 3.2 — Modify `src/services/scripting/pyodide_runtime.py`

**Find** `PyodideRuntime.execute` (currently lines 192-264). Replace specifier detection with the same two-pass algorithm as JS (resolve locals → union scan for pip specs):

```python
from services.scripting.py_runtime import (
    detect_pm_require_py_specs, _iter_pm_require_py_local_stems,
)
from services.scripting.local_modules import LocalModuleResolver

# Step 1: resolve local closure.
resolver = LocalModuleResolver()
try:
    local_mods = resolver.resolve_required(
        script, _iter_pm_require_py_local_stems, language="python"
    )
except ValueError as exc:
    return _err(str(exc))

# Step 2: scan pip specs across user + all local sources.
union_source = script + "\n" + "\n".join(m.source for m in local_mods.values())
try:
    all_specs = detect_pm_require_py_specs(union_source)
except ValueError as exc:
    return _err(str(exc))
pip_specs = [s.pip_spec for s in all_specs if s.kind == "pip"]

local_py_modules_payload = {stem: m.source for stem, m in local_mods.items()}
```

Then in the payload (lines 224-230) — call the key `local_py_modules` (parallel to existing `pm_require` / `pypi_index_urls`, narrows to "this is the Python local-module bundle"):

```python
payload = {
    "user_script": script,
    "context": dict(context),
    "pm_require": pip_specs,                       # PyPI only (drives micropip.install)
    "pypi_index_urls": pypi_index_urls,
    "local_py_modules": local_py_modules_payload,  # NEW: {stem: source}
}
```

`needs_net = bool(pip_specs)` — locals never trigger network.

**RestrictedPython subprocess path** (in `py_runtime.py`, both `PyRuntime.execute` and `PyRuntime.execute_restricted` non-Pyodide branches): before running, scan user source for `_PM_REQUIRE_PY_LOCAL_RE.search(...)`; if any present, return a `_runtime_error_output` with message: `'Local script modules (pm.require("local:<name>.py")) require the Pyodide Python runtime (Deno + vendor_pyodide). The RestrictedPython sandbox cannot load them.'` Tests must cover both paths (see Section 3.6).

### 3.3 — New file `data/scripts/pm_local_loader.py`

Runs **inside Pyodide**. Stores under a namespaced **dotted** name so subdirectory layouts map cleanly to Python's module system. Path `utils/jwt.py` → `__pm_local_utils.jwt`. Never registers under the bare segment alone, so stdlib (`json`, `re`, …) cannot be shadowed.

```python
r"""Register ``pm.require("local:<rel>.py")`` modules under ``__pm_local_.<rel-dotted>``.

Loaded by ``pyodide_run.mjs`` before ``pm_bootstrap.py``. Sources arrive as
``{rel_posix_path: source_text}`` from the host. Each is exec'd into a fresh
module and registered under ``sys.modules`` using a dotted name derived from
the relative path (slashes → dots, ``.py`` stripped). The top-level
``__pm_local_`` package node is created on first call so dotted lookups work.
"""
from __future__ import annotations

import re
import sys
import types

_PACKAGE_ROOT = "__pm_local_"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ensure_package(dotted: str) -> None:
    """Create empty parent package modules so dotted import resolves."""
    parts = dotted.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            mod = types.ModuleType(parent)
            mod.__path__ = []  # mark as package
            sys.modules[parent] = mod


def register_pm_local_modules(sources: dict[str, str]) -> None:
    """Register each *rel_path → source* pair under ``__pm_local_.<dotted>``.

    Example: ``{"utils/jwt.py": "..."}`` becomes ``sys.modules["__pm_local_.utils.jwt"]``.
    Raises ValueError for invalid segments, duplicate registration, or unsafe paths.
    """
    # Ensure the root package node exists.
    if _PACKAGE_ROOT not in sys.modules:
        root = types.ModuleType(_PACKAGE_ROOT)
        root.__path__ = []
        sys.modules[_PACKAGE_ROOT] = root

    for rel, src in sources.items():
        if not rel.endswith(".py") or ".." in rel.split("/") or rel.startswith("/"):
            raise ValueError(f"invalid local module path {rel!r}")
        segments = rel[:-3].split("/")  # strip .py
        for seg in segments:
            if not _SAFE_SEGMENT.match(seg):
                raise ValueError(f"invalid segment {seg!r} in {rel!r}")
        dotted = f"{_PACKAGE_ROOT}." + ".".join(segments)
        if dotted in sys.modules:
            raise ValueError(f"local module {dotted!r} is already registered")
        _ensure_package(dotted)
        module = types.ModuleType(dotted)
        module.__file__ = f"<local {rel}>"
        exec(compile(src, module.__file__, "exec"), module.__dict__)
        sys.modules[dotted] = module
```

### 3.4 — Modify `data/scripts/pm_bootstrap.py`

Find `pm.require` (around line 1104). Prepend a `local:` branch **before** the existing pip-import path. Resolves via dotted name derived from the specifier path: `local:utils/jwt.py` → `__pm_local_.utils.jwt`.

```python
def require(self, spec):
    if not isinstance(spec, str):
        raise RuntimeError("pm.require: specifier must be a string")
    raw = spec.strip()
    if raw.startswith("local:"):
        body = raw[len("local:"):]
        if not body.endswith(".py"):
            raise RuntimeError(
                'pm.require: local Python modules must use an explicit ".py" suffix'
            )
        if ".." in body.split("/") or body.startswith("/"):
            raise RuntimeError(f"pm.require: unsafe local path {raw!r}")
        segments = body[:-3].split("/")
        if not segments or any(not s for s in segments):
            raise RuntimeError("pm.require: empty local module name")
        dotted = "__pm_local_." + ".".join(segments)
        try:
            return importlib.import_module(dotted)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"pm.require({spec!r}): local module not registered "
                f"(expected importable {dotted!r})"
            ) from exc
    # ... existing path: importlib.import_module(spec) etc.
```

### 3.5 — Modify `data/scripts/pyodide_run.mjs`

Locate `main()` (around line 130-200). After `micropip.install(...)` and **before** `pm_bootstrap.py` is loaded:

```javascript
// After micropip.install(...) of pip specs:
const localMap =
  inp.local_py_modules &&
  typeof inp.local_py_modules === "object" &&
  !Array.isArray(inp.local_py_modules)
    ? inp.local_py_modules
    : {};
if (Object.keys(localMap).length > 0) {
  const loaderPath = join(_here, "pm_local_loader.py");
  const loaderSrc = readFileSync(loaderPath, { encoding: "utf-8" });
  await pyodide.runPythonAsync(loaderSrc);
  const localsJson = JSON.stringify(localMap);
  await pyodide.runPythonAsync(
    `register_pm_local_modules(__import__("json").loads(${JSON.stringify(
      localsJson,
    )}))`,
  );
}
// then existing: load pm_bootstrap.py, then exec user_script
```

Update the file's docstring at the top to mention the new payload field:
```
// Stdin: one JSON line
// { user_script, context, pm_require: string[], pypi_index_urls?: string[],
//   local_py_modules?: { [stem: string]: string } }
```

### 3.6 — Tests `tests/unit/services/test_pm_require_local_py.py`

New file. Cases:
1. `test_detect_specs_recognizes_local` — `detect_pm_require_py_specs('pm.require("local:util.py")')` returns one spec `PmPyRequireSpec("local","util","")`.
2. `test_detect_specs_keeps_pip_separate` — mixed `pm.require("requests")` + `pm.require("local:util.py")` returns one of each kind.
3. `test_detect_specs_rejects_local_without_py_suffix` — `pm.require("local:foo")` is not matched as either kind; `_iter_pm_require_py_local_stems` yields nothing for it.
4. `test_pip_regex_does_not_match_local_prefix` — negative lookahead works: `pm.require("local:foo.py")` does not produce a pip spec.
5. `test_payload_includes_local_py_modules` — mock `LocalModuleResolver` + `subprocess.Popen`; parsed payload JSON contains `local_py_modules: {"util": "..."}`.
6. `test_pip_specs_unaffected_by_local` — when both kinds present, `pm_require` field contains only pip specs.
7. `test_payload_union_scans_for_pip` — local module source contains `pm.require("requests==2.31")`; user script does not. Payload `pm_require` field contains `requests==2.31` (union scan).
8. `test_pm_local_loader_registers_under_namespace` — call `register_pm_local_modules({"foo": "x=1"})`; assert `sys.modules["__pm_local_foo"]` has `x == 1`; assert `sys.modules.get("foo") is None`.
9. `test_pm_local_loader_does_not_shadow_stdlib` — `register_pm_local_modules({"json": "POISONED=True"})`; verify `import json` still returns the real stdlib `json`.
10. `test_pm_local_loader_rejects_invalid_stem` — `register_pm_local_modules({"123bad": "x=1"})` raises `ValueError`.
11. `test_pm_local_loader_rejects_duplicate_registration` — calling `register_pm_local_modules({"foo": "x=1"})` twice raises (defensive).
12. `test_pm_bootstrap_local_branch_uses_namespaced_lookup` — register `__pm_local_foo`; call `pm.require("local:foo.py")`; assert identity.
13. `test_pm_bootstrap_local_branch_rejects_missing_py_suffix` — `pm.require("local:foo")` raises with the "explicit '.py' suffix" message.
14. `test_missing_local_returns_error` — user script requires `local:nope.py` with empty modules dir → `PyodideRuntime.execute` returns `{"error": ...}` mentioning `nope`.
15. `test_execute_path_rejects_local` — invoke `PyRuntime.execute` (non-Pyodide branch) with a script containing `pm.require("local:foo.py")`; assert error result includes "Pyodide".
16. `test_execute_restricted_path_rejects_local` — same for `PyRuntime.execute_restricted`.
17. `test_cross_language_python_requires_js_raises` — `local:helper.js` exists, user Python script requires `local:helper.py` → resolver "not found" error (file with that stem+`.py` doesn't exist; the `.js` file is ignored for Python).

### 3.7 — Modify `tests/unit/services/test_pm_python_parity.py`

Add cases:
- Both JS regex and Python regex detect their respective `local:` shapes.
- Both regexes reject `local:foo` (no extension).
- Both regexes reject `local:foo.txt` (wrong extension).

PR 3 ships once Python tests are green and a manual Python smoke works.

---

## Section 4 — Left-pane toggle row (PR 4)

### 4.0 — Architecture diagram (Cursor primary-sidebar pattern)

**Before** (today):
```
┌────────────────┬───────────────┬───────────────┐
│ collection_    │ request +     │ right         │
│ widget         │ response      │ sidebar       │
│                │               │               │
└────────────────┴───────────────┴───────────────┘
       splitter slot 0    slot 1        slot 2
```

**After** (this PR — slot 0 only changes its contents):
```
┌────────────────┬───────────────┬───────────────┐
│ LeftSidebarPane│ request +     │ right         │
│ ┌────────────┐ │ response      │ sidebar       │
│ │[📁][</>]   │ │ (unchanged)   │ (unchanged)   │
│ ├────────────┤ │               │               │
│ │ Stack page0│ │               │               │
│ │ Collection │ │               │               │
│ │ Widget     │ │               │               │
│ │ (verbatim) │ │               │               │
│ │   OR       │ │               │               │
│ │ Stack page1│ │               │               │
│ │ Scripts    │ │               │               │
│ │ Panel      │ │               │               │
│ └────────────┘ │               │               │
└────────────────┴───────────────┴───────────────┘
       slot 0          slot 1         slot 2
```

`main_splitter` keeps **exactly the same number of slots** (3, as today). Slot 0's child widget changes from `CollectionWidget` directly → `LeftSidebarPane` wrapper. Inside the wrapper, the existing `CollectionWidget` is page 0 of a `QStackedWidget`; the new `ScriptsPanel` is page 1. The toggle row sits above the stack.

This is the Cursor primary-sidebar pattern: icon row at top of the pane, content below.

### 4.1 — New file `src/ui/sidebar/left_pane.py`

Single widget — `LeftSidebarPane(QWidget)`. Owns the toggle row + a `QStackedWidget` for content. Takes the existing `CollectionWidget` instance and a new `ScriptsPanel` instance via constructor (no re-parent gymnastics).

```python
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from ui.styling.icons import phi


_TOGGLE_BTN_HEIGHT = 24
_TOGGLE_ROW_PADDING = 4


class LeftSidebarPane(QWidget):
    """Horizontal toggle row at the top + stacked content below.

    Pages: 0 = Collections (existing CollectionWidget), 1 = Scripts (ScriptsPanel).
    """

    panel_changed = Signal(str)  # emits "collections" or "scripts"

    def __init__(
        self,
        collections_widget: QWidget,
        scripts_widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("leftSidebarPane")

        # --- Toggle row -----------------------------------------------
        row = QWidget(self)
        row.setObjectName("leftPaneToggleRow")
        row.setFixedHeight(_TOGGLE_BTN_HEIGHT + _TOGGLE_ROW_PADDING * 2)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(
            _TOGGLE_ROW_PADDING, _TOGGLE_ROW_PADDING,
            _TOGGLE_ROW_PADDING, _TOGGLE_ROW_PADDING,
        )
        row_lay.setSpacing(4)

        # Both buttons MUST have an icon. Icons make Cursor's pattern legible
        # at a glance; an iconless toggle row is unacceptable.
        # Use phi() (Phosphor icon font). Verify the icon names exist in
        # data/fonts/phosphor-charmap.json before PR 4 — fallbacks listed below.
        self._collections_btn = self._make_toggle_btn(
            "tree-structure", "Collections (Ctrl+1)"
        )
        # Phosphor icon options for the Scripts button — pick whichever reads
        # cleanest at 16px on this app's theme: "code", "file-code",
        # "code-block", or "brackets-curly".
        self._scripts_btn = self._make_toggle_btn(
            "code", "Scripts (Ctrl+2)"
        )
        row_lay.addWidget(self._collections_btn)
        row_lay.addWidget(self._scripts_btn)
        row_lay.addStretch(1)

        # --- Content stack --------------------------------------------
        self._stack = QStackedWidget(self)
        self._stack.addWidget(collections_widget)  # index 0
        self._stack.addWidget(scripts_widget)      # index 1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(row)
        outer.addWidget(self._stack, 1)

        self._collections_widget = collections_widget
        self._scripts_widget = scripts_widget
        self._active: str = "collections"

        self._collections_btn.clicked.connect(
            lambda: self.set_active_panel("collections")
        )
        self._scripts_btn.clicked.connect(
            lambda: self.set_active_panel("scripts")
        )

        # Restore last active panel.
        s = self._qsettings()
        restored = str(s.value("ui/left_pane/active", "collections") or "collections")
        self.set_active_panel(restored if restored in {"collections", "scripts"} else "collections")

    def _make_toggle_btn(self, icon_name: str, tooltip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("leftPaneToggleButton")
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setToolTip(tooltip)
        btn.setIcon(phi(icon_name, size=16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setFixedSize(_TOGGLE_BTN_HEIGHT + 4, _TOGGLE_BTN_HEIGHT)
        return btn

    def _qsettings(self) -> QSettings:
        from ui.styling.theme_manager import _ORG, _APP
        return QSettings(_ORG, _APP)

    def set_active_panel(self, name: str) -> None:
        """Show the named page (``"collections"`` or ``"scripts"``)."""
        if name not in {"collections", "scripts"}:
            return
        self._active = name
        self._stack.setCurrentIndex(0 if name == "collections" else 1)
        self._collections_btn.setChecked(name == "collections")
        self._scripts_btn.setChecked(name == "scripts")
        self._qsettings().setValue("ui/left_pane/active", name)
        self.panel_changed.emit(name)

    def active_panel(self) -> str:
        return self._active

    def collections_widget(self) -> QWidget:
        return self._collections_widget

    def scripts_widget(self) -> QWidget:
        return self._scripts_widget
```

**Notes on the design:**
- The toggle row is a plain `QHBoxLayout` of `QToolButton`s — same pattern Postmark already uses for `CollectionHeader`'s "New" / "Import" buttons. Cheap, no novel infrastructure.
- The content area is a vanilla `QStackedWidget`, the same pattern used by `_editor_stack` / `_response_stack` in `main_window/window.py`. No `QDockWidget`.
- No `install_in_splitter` shenanigans. `LeftSidebarPane` is just a `QWidget` you drop into the splitter where `collection_widget` used to go.
- No collapse behavior — clicking the active button is a no-op (idempotent). The whole left pane collapses via the existing `_toggle_sidebar` action (which hides this `LeftSidebarPane`).

### 4.2 — QSS styling

Add to [src/ui/styling/global_qss.py](../../src/ui/styling/global_qss.py) inside the same f-string block that already styles `sidebarToolButton`:

```python
QWidget#leftPaneToggleRow {{
    background: {p["bg_alt"]};
    border-bottom: 1px solid {p["border"]};
}}
QToolButton#leftPaneToggleButton {{
    background: transparent;
    border: none;
    padding: 2px;
    border-radius: 4px;
    color: {p["text_muted"]};
}}
QToolButton#leftPaneToggleButton:hover {{
    background: {p["hover_bg"]};
    color: {p["text"]};
}}
QToolButton#leftPaneToggleButton:checked {{
    background: {p["selected_bg"]};
    color: {p["accent"]};
}}
```

Use existing palette keys only (`bg_alt`, `border`, `hover_bg`, `selected_bg`, `accent`, `text`, `text_muted`). If `text_muted` doesn't exist, grep the file for the actual key name and substitute.

### 4.3 — Modify `src/ui/main_window/window.py`

Currently (per Phase-1 exploration, [window.py:469](../../src/ui/main_window/window.py#L469)):
```python
self._main_splitter.addWidget(self.collection_widget)
```

Replace with:
```python
from ui.sidebar.left_pane import LeftSidebarPane
from ui.sidebar.scripts_panel import ScriptsPanel

self._scripts_panel = ScriptsPanel()
self._scripts_panel.file_open_requested.connect(self._open_script_module_tab)
self._left_sidebar_pane = LeftSidebarPane(
    collections_widget=self.collection_widget,
    scripts_widget=self._scripts_panel,
)
self._main_splitter.addWidget(self._left_sidebar_pane)
```

**Keyboard shortcuts** — add after splitter setup:

```python
from PySide6.QtGui import QShortcut, QKeySequence
QShortcut(QKeySequence("Ctrl+1"), self,
          activated=lambda: self._left_sidebar_pane.set_active_panel("collections"))
QShortcut(QKeySequence("Ctrl+2"), self,
          activated=lambda: self._left_sidebar_pane.set_active_panel("scripts"))
```

**Existing `_toggle_sidebar`** (around [window.py:547](../../src/ui/main_window/window.py#L547)) — keep as-is: it toggles visibility of the whole `LeftSidebarPane` (which is now what occupies the slot `collection_widget` used to occupy). No code change needed there; just verify the reference points to `self._left_sidebar_pane` instead of `self.collection_widget`.

**Settings → re-rooting hook**:
```python
def _on_local_modules_dir_changed(self) -> None:
    self._scripts_panel.refresh_root()
```
Connect to `SettingsDialog.local_modules_dir_changed` signal (Section 6.7).

### 4.4 — Tests `tests/ui/sidebar/test_left_pane.py`

New file. Cases:
1. `test_starts_on_collections_by_default` — fresh QSettings, default page index = 0.
2. `test_set_active_panel_switches_stack` — `set_active_panel("scripts")` → `stack.currentIndex() == 1`.
3. `test_buttons_reflect_active_panel` — after switch, `scripts_btn.isChecked() is True` and `collections_btn.isChecked() is False`.
4. `test_panel_changed_signal_emits` — switching emits `"scripts"`.
5. `test_active_panel_persisted_via_qsettings` — set, recreate widget, restored.
6. `test_clicking_active_button_is_idempotent` — calling `set_active_panel("collections")` twice doesn't toggle off; the pane never enters a no-active state.
7. `test_invalid_panel_name_ignored` — `set_active_panel("bogus")` is a no-op; active stays the same.

### 4.5 — Tests `tests/ui/test_main_window.py` (extend)

Two cases:
1. `test_left_pane_is_left_sidebar_pane` — `main_splitter.widget(0)` is a `LeftSidebarPane`.
2. `test_collection_widget_still_accessible_via_left_pane` — `main_window.collection_widget` resolves to the same instance held by `LeftSidebarPane.collections_widget()`.

PR 4 ships once tests pass + manual smoke: opens app → see toggle row above collections → click Scripts icon → **Scripts tree** appears → click Collections icon → tree back.

---

## Section 5 — Scripts panel (PR 5)

### 5.-1 — Tree layout (mirrors the Collections tree pattern)

The Scripts panel is a **tree** (not a flat list) — same visual pattern as the existing collections sidebar. Folders contain files; folders expand/collapse; selection lands on either a file or a folder.

**Reuse path**: subclass / parametrize the existing collections-tree machinery so the visual feel matches the rest of the app.

- `CollectionTree` lives at [src/ui/collections/tree/collection_tree.py](../../src/ui/collections/tree/collection_tree.py).
- The base widget is `DraggableTreeWidget` at [src/ui/collections/tree/draggable_tree_widget.py](../../src/ui/collections/tree/draggable_tree_widget.py) — `QTreeWidget` subclass with custom delegate styling.
- The `CollectionTreeDelegate` provides the row styling used app-wide for sidebar trees.

**Approach**: extract the styling-only bits (delegate + icon set + indent + spacing) into a reusable base. The Scripts panel instantiates that base and populates it from disk. The existing `CollectionTree`'s drag-drop / persistence logic is **not** reused (it persists to SQL; we're persisting to disk by rename). Only the **visual** layer is shared.

Concretely, the Scripts panel tree:
- Top-level entries = direct children of the local-modules root (folder OR file).
- Folder entries are expandable; their children come from recursive `iterdir()`.
- File entries display the base name (e.g. `jwt.js`) — extension stays visible so users see the language at a glance.
- Sort: folders first (alphabetical), then files (alphabetical).
- Each row's `UserRole` data carries the resolved absolute `Path`.
- Hidden dirs (`.git`, etc.) and unsupported extensions are filtered out — same rules as `LocalModuleResolver.discover()`.



### 5.0 — Required UI mockup (Collections parity + tree)

**(Amended)** The Scripts page must **look and behave like the Collections sidebar**: a **named section** inside the panel (not only the icon toggle above), **“+ New”** and **“Refresh”** as **link-style / text+beside-icon** actions matching [`CollectionHeader`](../../src/ui/collections/collection_header.py), a **search field** with placeholder (e.g. `Search scripts`) filtering the tree, then the **folder/file tree**. The left icon row (§4) answers “which sidebar page”; the **Scripts header** answers “what am I editing” — same two-level pattern as Collections (rail vs section).

```
┌────────────────────────────────────────────────┐
│ [📁][</>]   ← toggle row from Section 4        │
├────────────────────────────────────────────────┤
│ Scripts                    + New    Refresh    │  ← row 1: section label + actions (mirror CollectionHeader)
├────────────────────────────────────────────────┤
│ 🔍  Search scripts…                            │  ← row 2: QLineEdit (objectName sidebarSearch)
├────────────────────────────────────────────────┤
│ [ optional compact row: delete / rename / … ]   │  ← optional icon row OR overflow ⋯ menu (see 5.0a)
├────────────────────────────────────────────────┤
│ 📁 auth                                        │
│   📄 oauth.ts                                  │
│   📄 google.ts                                 │
│ 📁 utils                                       │
│   📄 jwt.js                  ← selected         │
│   📄 shout.py                                  │
│ 📄 jwt.js                                      │
│ 📄 validators.py                               │
│                                                │
│    No modules yet.                             │  ← empty-state (no “subfolders ignored” copy)
│    Click “+ New” to create one.                │
└────────────────────────────────────────────────┘
        │
        └── Right-click on a file row:
            ┌────────────────────────────────┐
            │ New file                 ▸     │  → same flow as + New (or opens Create New dialog)
            │ Copy import specifier          │  → clipboard local:<rel_posix_path>
            │ Reveal in file manager         │
            │ ─────────────────────────── │
            │ Rename…                        │
            │ Delete                         │
            └────────────────────────────────┘
```

### 5.0a — Required UI elements (reviewer checklist) **(Amended)**

None of the following are optional. A prior implementation shipped a bare list with no mutations — reject that.

1. **Scripts header (Collections-shaped)** — `QLabel` “Scripts” (`sidebarSectionLabel`), **`+ New`** (`sidebarToolButton`, text beside icon, opens **Create New** dialog — §5.0b), **`Refresh`** (`sidebarToolButton` or `linkButton`-style) calling the same rescan as the 5s timer, preserving selection when possible. Model directly on `CollectionHeader`’s first row (without Import unless product wants an analogue such as “Open folder”).
2. **Search row** — full-width `QLineEdit`, `sidebarSearch`, leading magnifier action, emits `search_changed` (or equivalent) to filter visible tree rows **without** hiding folder ancestors of matches (standard tree-filter behaviour).
3. **Tree** — as §5.-1: folders, script files, double-click file → `file_open_requested(Path)`; double-click folder expands/collapses only.
4. **Create New dialog (Postman-style)** — **§5.0b**; do **not** use a bare `QInputDialog` as the only UI for creating a module (that was the gap vs Collections).
5. **Context menu** on tree items — New file submenu, Copy import specifier (relative POSIX path under root), Reveal, Rename, Delete; mirror toolbar when a secondary toolbar exists.
6. **Selection-aware controls** — disable delete/rename when inappropriate; disable mutations when `os.access(root, os.W_OK)` is False (tooltip: “Folder is read-only”).
7. **Empty-state label** when no eligible files: e.g. “No modules yet. Click ‘+ New’ to create one.” **Do not** claim subfolders are ignored (they are supported).

**Optional secondary chrome:** A row of small icon buttons (delete, rename, open folder) may remain for parity with early mockups; if present, it sits **below** the search row. Primary discovery remains **+ New** + **Refresh** + search like Collections.

### 5.0b — `NewScriptModulePopup` (mirror `NewItemPopup`) **(Amended)**

Add a modal dialog alongside [`NewItemPopup`](../../src/ui/collections/new_item_popup.py): same window chrome (`newItemPopup`, `newItemTitle`, tile `objectName`s, fixed size ~380×260, centered “What do you want to create?” style copy adapted for **script modules**). **Tiles**: at minimum **JavaScript**, **TypeScript**, **Python** (icons `file-js` / `file-ts` / `file-py` or Phosphor equivalents). Optional fourth tile: **Folder** (creates empty directory under root or under selected folder). After tile choice, prompt for **name** (second step inside same dialog or follow-up — implementation choice) then create `*.js|*.ts|*.py` or `mkdir`. Emit / callback → `file_open_requested` for new files. This satisfies “similar window to Collections New”.

---

### 5.0 (legacy mockup — superseded)

The ASCII block and numbered list in the **original** §5.0 (five-icon-only toolbar, no Scripts title, `QInputDialog`-only new file, empty-state “Subfolders are ignored”) is **retired**. It is replaced by **§5.0 + §5.0a + §5.0b** above. The rest of this document (§5.1 code, tests, wiring) still applies but **implementations must follow §5.0a layout**; update the §5.1 sample code accordingly (embed `ScriptsHeader`, wire search, replace `_on_new_file` to open `NewScriptModulePopup`).

### 5.1 — New package `src/ui/sidebar/scripts_panel/`

Files:
- `__init__.py` — `from .panel import ScriptsPanel` (re-export).
- `panel.py` — main widget (`ScriptsHeader` + search + tree + optional secondary toolbar per §5.0a).
- `scripts_header.py` — **(Amended)** row 1+2 mirroring [`CollectionHeader`](../../src/ui/collections/collection_header.py) (label, + New, Refresh, search field + signals).
- `new_script_popup.py` — **(Amended)** `NewScriptModulePopup` (§5.0b), same chrome as `NewItemPopup`.
- `actions.py` — context menu handlers (`prompt_new_module`, rename, delete, reveal, copy specifier).

`panel.py`. **Tree layout** (mirrors the collections tree). Use `QTreeWidget` populated by hand via `Path.iterdir()` (not `QFileSystemModel`, so we keep full control of filtering/icons/sort). Walks subdirectories.

**(Amended)** The sample `_build_ui` below still uses the **legacy five-icon toolbar** for illustration of tree wiring; the shipped widget must embed **`ScriptsHeader` + search + tree** per §5.0a (toolbar row optional). `_on_new_file` must open **`NewScriptModulePopup`** (§5.0b), not only `QInputDialog`.

```python
import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
    QTreeWidget, QTreeWidgetItem, QLabel,
)
from services.scripting.runtime_settings import RuntimeSettings
from ui.styling.icons import phi


_ALLOWED_EXTS = (".js", ".ts", ".py")
_ROLE_ABSOLUTE_PATH = Qt.ItemDataRole.UserRole + 1
_ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 2


class ScriptsPanel(QWidget):
    file_open_requested = Signal(Path)
    file_renamed = Signal(Path, Path)
    file_deleted = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root = RuntimeSettings.local_modules_dir()
        self._build_ui()
        self._refresh()
        # Cheap poll for outside-of-app changes (5s).
        self._poll = QTimer(self)
        self._poll.setInterval(5000)
        self._poll.timeout.connect(self._refresh)
        self._poll.start()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(4)
        self._new_btn     = self._mk_btn("plus",            "New module")
        self._delete_btn  = self._mk_btn("trash",           "Delete selected")
        self._rename_btn  = self._mk_btn("pencil-simple",   "Rename selected")
        self._refresh_btn = self._mk_btn("arrow-clockwise", "Refresh list")
        self._reveal_btn  = self._mk_btn("folder-open",     "Open folder in file manager")
        for b in (self._new_btn, self._delete_btn, self._rename_btn,
                  self._refresh_btn, self._reveal_btn):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._empty_label = QLabel(
            'No modules yet. Click "+ New" to create one.'
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("scriptsEmptyState")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setExpandsOnDoubleClick(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemSelectionChanged.connect(self._sync_button_enabled)
        layout.addWidget(self._tree, 1)

        self._new_btn.clicked.connect(self._on_new_file)
        self._delete_btn.clicked.connect(self._on_delete_selected)
        self._rename_btn.clicked.connect(self._on_rename_selected)
        self._refresh_btn.clicked.connect(self._refresh)
        self._reveal_btn.clicked.connect(self._on_reveal)

        self._delete_btn.setEnabled(False)
        self._rename_btn.setEnabled(False)

    def _mk_btn(self, icon_name: str, tooltip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(phi(icon_name, size=16))
        btn.setToolTip(tooltip)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(26, 26)
        return btn

    def _sync_button_enabled(self) -> None:
        sel = self._selected_path()
        writable = os.access(self._root, os.W_OK)
        self._delete_btn.setEnabled(sel is not None and writable)
        self._rename_btn.setEnabled(sel is not None and writable)
        self._new_btn.setEnabled(writable)

    def refresh_root(self) -> None:
        """Called when Settings → Local modules path changes."""
        self._root = RuntimeSettings.local_modules_dir()
        self._refresh()

    def _refresh(self) -> None:
        # Preserve current selection by absolute path so refresh doesn't jump.
        prev_sel = self._selected_path()
        self._tree.clear()
        if not self._root.is_dir():
            self._empty_label.show()
            self._tree.hide()
            return
        has_any = self._populate_node(self._tree.invisibleRootItem(), self._root)
        if not has_any:
            self._empty_label.show()
            self._tree.hide()
            return
        self._empty_label.hide()
        self._tree.show()
        if prev_sel is not None:
            self._restore_selection(prev_sel)

    def _populate_node(self, parent: QTreeWidgetItem, dir_path: Path) -> bool:
        """Recursively populate *parent* with the children of *dir_path*.

        Returns True if at least one descendant was added (so callers can detect
        empty subtrees and prune the empty-state).
        """
        # Sort: folders first (alpha), then files (alpha). Hidden + non-script files filtered.
        children = sorted(
            (p for p in dir_path.iterdir() if not p.name.startswith(".")),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
        added = False
        for child in children:
            if child.is_dir():
                node = QTreeWidgetItem([child.name])
                node.setIcon(0, phi("folder", size=16))
                node.setData(0, _ROLE_ABSOLUTE_PATH, str(child))
                node.setData(0, _ROLE_IS_DIR, True)
                if self._populate_node(node, child):
                    parent.addChild(node)
                    added = True
                # else: empty subtree — skip the folder entirely
            elif child.suffix.lower() in _ALLOWED_EXTS:
                node = QTreeWidgetItem([child.name])
                node.setIcon(0, phi(_icon_for_ext(child.suffix), size=16))
                node.setData(0, _ROLE_ABSOLUTE_PATH, str(child))
                node.setData(0, _ROLE_IS_DIR, False)
                parent.addChild(node)
                added = True
        return added

    def _restore_selection(self, target: Path) -> None:
        """Re-select the row whose UserRole path matches *target*, if present."""
        target_s = str(target)
        it = iter([self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())])
        # Walk all items via a stack.
        stack = list(self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount()))
        while stack:
            node = stack.pop()
            if node.data(0, _ROLE_ABSOLUTE_PATH) == target_s:
                node.setSelected(True)
                self._tree.setCurrentItem(node)
                return
            stack.extend(node.child(i) for i in range(node.childCount()))

    def _selected_path(self) -> Path | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        raw = items[0].data(0, _ROLE_ABSOLUTE_PATH)
        return Path(raw) if raw else None

    def _selected_is_dir(self) -> bool:
        items = self._tree.selectedItems()
        return bool(items and items[0].data(0, _ROLE_IS_DIR))

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.data(0, _ROLE_IS_DIR):
            return  # let Qt handle expand/collapse
        raw = item.data(0, _ROLE_ABSOLUTE_PATH)
        if raw:
            self.file_open_requested.emit(Path(raw))

    def _on_context_menu(self, pos) -> None:
        from .actions import build_context_menu
        menu = build_context_menu(self, self._selected_path())
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_new_file(self) -> None:
        from .actions import prompt_new_module
        prompt_new_module(self, self._root, self._selected_path())

    def _on_delete_selected(self) -> None:
        from .actions import _prompt_delete
        path = self._selected_path()
        if path is not None:
            _prompt_delete(self, path)

    def _on_rename_selected(self) -> None:
        from .actions import _prompt_rename
        path = self._selected_path()
        if path is not None:
            _prompt_rename(self, path)

    def _on_reveal(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._root)))


def _icon_for_ext(ext: str) -> str:
    return {
        ".js": "file-js",
        ".ts": "file-ts",
        ".py": "file-py",
    }.get(ext.lower(), "file")
```

Wire `SettingsDialog.local_modules_dir_changed` → `ScriptsPanel.refresh_root` in `window.py`.

`actions.py` (extend with `new_script_popup.py` for `NewScriptModulePopup` per §5.0b):

```python
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QClipboard
from PySide6.QtWidgets import QMenu, QInputDialog, QMessageBox, QApplication
from PySide6.QtGui import QDesktopServices


def build_context_menu(panel, path: Path | None) -> QMenu:
    menu = QMenu(panel)
    # New file submenu.
    new_menu = menu.addMenu("New file")
    for label, ext in [("JavaScript (.js)", ".js"),
                       ("TypeScript (.ts)", ".ts"),
                       ("Python (.py)", ".py")]:
        a = new_menu.addAction(label)
        a.triggered.connect(
            lambda _checked=False, e=ext: prompt_new_module(panel, panel._root, panel._selected_path(), ext=e)
        )
    if path and path.is_file():
        menu.addSeparator()
        copy_a = menu.addAction("Copy import specifier")
        copy_a.triggered.connect(lambda: _copy_import_specifier(panel._root, path))
        reveal_a = menu.addAction("Reveal in file manager")
        reveal_a.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))
        menu.addSeparator()
        rename_a = menu.addAction("Rename…")
        rename_a.triggered.connect(lambda: _prompt_rename(panel, path))
        del_a = menu.addAction("Delete")
        del_a.triggered.connect(lambda: _prompt_delete(panel, path))
    return menu


def prompt_new_module(panel, root: Path, selected: Path | None, ext: str = ".js") -> None:
    """Open ``NewScriptModulePopup`` (§5.0b); then collect name and create under *root* or *selected* folder."""
    # Full implementation: see §5.0b. End state: ``panel.file_open_requested.emit(target_path)``.
    pass


def prompt_new_file(panel, root: Path, ext: str = ".js") -> None:
    """Legacy helper name — prefer ``prompt_new_module`` + popup. Kept for grep parity in tests."""
    prompt_new_module(panel, root, None, ext=ext)


def _copy_import_specifier(modules_root: Path, path: Path) -> None:
    """Copy ``local:<relative/posix/path.ext>`` under *modules_root*."""
    rel = path.resolve().relative_to(modules_root.resolve()).as_posix()
    spec = f"local:{rel}"
    QApplication.clipboard().setText(spec)


def _prompt_rename(panel, path: Path) -> None:
    new_name, ok = QInputDialog.getText(panel, "Rename", "New name (no extension):", text=path.stem)
    if not ok or not new_name.strip():
        return
    new_path = path.with_name(f"{new_name.strip()}{path.suffix}")
    path.rename(new_path)
    panel.file_renamed.emit(path, new_path)


def _prompt_delete(panel, path: Path) -> None:
    if QMessageBox.question(panel, "Delete", f"Delete {path.name}?") != QMessageBox.StandardButton.Yes:
        return
    path.unlink()
    panel.file_deleted.emit(path)
```

### 5.2 — Tests `tests/ui/sidebar/test_scripts_panel.py`

New file. Cases (all required — sparse coverage was a flagged gap last time):
1. `test_root_matches_settings` — `local_modules_dir` set to tmp dir → panel's `_root` is that dir.
2. `test_filter_hides_unsupported_extensions` — drop `.md` / `.txt` → not in tree.
3. `test_subdirectory_files_visible_under_folder_node` — `utils/jwt.js` → top-level `utils` folder node with `jwt.js` child.
4. `test_deep_subdirectory_visible` — `auth/oauth/google.ts` → 3-level deep node visible.
5. `test_empty_subdirectory_pruned` — folder with no eligible files → folder node not shown (avoids visual clutter).
6. `test_hidden_dirs_filtered` — `.git/foo.js` → not in tree.
7. `test_folder_first_alpha_sort` — folders sorted before files within each level, alphabetical.
8. `test_double_click_on_file_emits_signal_with_path` — signal payload is `Path`, points to the absolute file.
9. `test_double_click_on_folder_does_not_emit_signal` — expanding a folder doesn't trigger `file_open_requested`.
10. `test_copy_import_specifier_top_level` — `Path("foo.js")` → clipboard has `local:foo.js`.
11. `test_copy_import_specifier_nested` — `utils/jwt.js` → clipboard has `local:utils/jwt.js`.
12. `test_copy_import_specifier_python_nested` — `helpers/shout.py` → clipboard has `local:helpers/shout.py`.
13. `test_new_file_creates_with_correct_extension` — mock dialog → file appears in tree, signal emits Path.
14. `test_new_file_in_selected_folder` — folder selected → new file created inside that folder.
15. `test_new_file_collision_shows_warning` — existing file → no overwrite, no signal.
16. `test_rename_emits_signal` — `(old_path, new_path)`.
17. `test_delete_confirmation_no_keeps_file` — user picks No → file still exists, no signal.
18. `test_delete_emits_signal_and_removes_file`.
19. `test_context_menu_on_file_includes_copy_specifier_rename_delete` — menu correctness.
20. `test_context_menu_on_folder_omits_copy_specifier` — folders have no specifier; menu adapts.
21. `test_read_only_root_disables_mutation_buttons` — `os.access` mocked False → New / Rename / Delete disabled.
22. `test_empty_root_shows_empty_state` — no eligible files → empty label visible, tree hidden.
23. `test_refresh_root_preserves_selection_when_possible` — select `utils/jwt.js`, refresh, selection restored.
24. `test_refresh_root_updates_on_settings_change` — change root → tree reflects new contents.
25. **(Amended)** `test_scripts_header_has_new_refresh_search` — widgets present; `Refresh` triggers `_refresh`.
26. **(Amended)** `test_new_module_popup_opens_from_header` — `+ New` shows `NewScriptModulePopup` (or equivalent exec).

### 5.3 — Wire panel into main window

In `window.py` (already touched in PR 4):

```python
self._scripts_panel = ScriptsPanel()
self._scripts_panel.file_open_requested.connect(self._open_script_module_tab)
# (set_scripts_widget called in PR 4)
```

`_open_script_module_tab` is implemented in PR 6 — wire the signal even if the handler is a stub here.

PR 5 ships once `ScriptsPanel` tests pass. Double-click is a no-op until PR 6.

---

## Section 6 — Script-module tab type (PR 6)

### 6.0 — FULL editor surface reuse (mirror the pre/post scripts pane)

**Script-module tabs must use the same multi-pane layout, widgets, and toolbar as the existing pre/post-request scripts editor.** Not just the editor widget — the **entire chrome**. Users authoring a request script and authoring a module file must see the same surface.

**Mandatory layout** (mirrors [scripts_mixin.py:56-249](../../src/ui/request/request_editor/scripts/scripts_mixin.py#L56-L249)):

```
┌──────────────────────────────────────────────────────────┐
│ Toolbar: [🔍 Find][↔ Replace][🎯 Go to line] │ [↶ ↷] │ [💾 Save] │
├──────────────────────────────────────────────────────────┤
│ Search/replace bar (toggleable — same widget as scripts) │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  CodeEditorWidget                                        │
│  (same class, same LSP wiring, same completion popup)    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ Status bar: Ln 5, Col 12  │  Language: JavaScript  │ 1.2K│
├──────────────────────────────────────────────────────────┤    ← QSplitter handle
│ ScriptOutputPanel (same class as scripts editor)         │
│ ┌─[ Output ][ Problems ]──────────────────────────────┐ │
│ │  Problems tab: LSP diagnostics list (clickable,     │ │
│ │  same ScriptLspProblemsTab class).                  │ │
│ │  Output tab: stays empty for modules (no Run).      │ │
│ └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Concrete reuse list** (all classes/widgets, no rebuilds):

| Component | Source class | File |
|---|---|---|
| Code editor itself | `CodeEditorWidget` | [src/ui/widgets/code_editor/editor_widget.py](../../src/ui/widgets/code_editor/editor_widget.py) |
| Vertical splitter (editor top / output bottom, ~44/56 ratio) | `QSplitter(Qt.Vertical)` per [scripts_mixin.py:128-139](../../src/ui/request/request_editor/scripts/scripts_mixin.py#L128) | — |
| Output + Problems panel | `ScriptOutputPanel` | [src/ui/request/request_editor/scripts/output_panel.py](../../src/ui/request/request_editor/scripts/output_panel.py) |
| Problems tab (LSP diagnostics) | `ScriptLspProblemsTab` | [src/ui/request/request_editor/scripts/lsp_problems_tab.py](../../src/ui/request/request_editor/scripts/lsp_problems_tab.py) |
| Search/replace bar | `SearchReplaceBar` | (same as scripts editor) |
| Find / Replace / Go-to-line buttons | toolbar built by `_build_script_header` | [scripts_mixin.py:544-709](../../src/ui/request/request_editor/scripts/scripts_mixin.py#L544) |
| Undo / Redo buttons | same toolbar | — |
| Save button + Ctrl+S | same toolbar | — |
| Status bar (Ln/Col, language, char count) | `_build_script_status_bar` | [scripts_mixin.py:711-793](../../src/ui/request/request_editor/scripts/scripts_mixin.py#L711) |
| LSP attach | `CodeEditorWidget.set_language()` auto-wires `attach_lsp()` | — |

**Wire `ScriptOutputPanel.bind_script_editor(editor)`** so the Problems tab receives `lsp_diagnostics_changed` signals — same as the scripts editor. This is the entire LSP-diagnostics hookup.

**Omit from module tabs** (different from scripts editor):
- **Run button** — modules have no entry point standalone. Hide the button (don't disable — hide). Output tab stays present for chrome parity but stays empty.
- **Debug button** — same reason. Hide.
- **Run all** — same reason. Hide.
- **Mock response tab** — only meaningful for post-response scripts. Omit from the `ScriptOutputPanel` for module tabs (constructor takes a `script_type` arg; pass a new `"module"` value that skips the Mock tab).
- **RuntimeBanner / InheritedScriptsBanner** — request-context concerns, not relevant for modules.

**The simplest implementation path**: extract the `_build_pre_request_tab` body of `_ScriptsMixin` into a free function `build_script_editor_surface(*, script_type)` (or a small `ScriptEditorSurface` widget) that takes a `script_type: Literal["pre_request","test","module"]`. Both `_ScriptsMixin` and `ScriptModuleTab` call it. The `"module"` branch hides Run/Debug/Banner/Mock; everything else stays identical.

**Do not** copy-paste the layout code. Reuse via extraction so a future bug fix in one surface fixes both.

### 6.1 — New file `src/ui/tabs/script_module_tab.py`

**Illustrative-only (Amended):** The code block below sketches dirty/save/orphan behaviour with a bare `CodeEditorWidget`. The **shipped** module tab **must** embed the full surface from §6.0 via `build_script_editor_surface(..., script_type="module")` (toolbar, splitter, `ScriptOutputPanel`, Problems, LSP bind). Replace the central widget layout accordingly while keeping the same dirty/save signals contract.

```python
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ui.widgets.code_editor.editor_widget import CodeEditorWidget


_EXT_TO_LANG = {".js": "javascript", ".ts": "typescript", ".py": "python"}


class ScriptModuleEditorWidget(QWidget):
    dirty_changed = Signal(bool)

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = path
        self._dirty = False
        self._orphan = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._banner = QLabel("File deleted on disk — Save to restore.")
        self._banner.hide()
        layout.addWidget(self._banner)

        self._editor = CodeEditorWidget(read_only=False)
        language = _EXT_TO_LANG.get(path.suffix, "javascript")
        self._editor.set_language(language)  # call existing API
        if path.exists():
            self._editor.set_text(path.read_text(encoding="utf-8"))
        layout.addWidget(self._editor, 1)

        self._editor.textChanged.connect(self._on_text_changed)

        QShortcut(QKeySequence.Save, self, activated=self.save)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _set_dirty(self, v: bool) -> None:
        if self._dirty != v:
            self._dirty = v
            self.dirty_changed.emit(v)

    def _on_text_changed(self) -> None:
        self._set_dirty(True)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._editor.text(), encoding="utf-8")
        self._orphan = False
        self._banner.hide()
        self._set_dirty(False)

    def mark_orphan(self) -> None:
        self._orphan = True
        self._banner.show()
        self._set_dirty(True)
```

Note: `set_language(...)` and `.text()` / `.set_text()` must exist on `CodeEditorWidget`. If their names differ, look up actual API at [src/ui/widgets/code_editor/editor_widget.py](../../src/ui/widgets/code_editor/editor_widget.py) and adjust.

### 6.2 — Modify `src/ui/request/navigation/tab_manager.py`

This is **high blast radius** — every site that touches `ctx.editor` must be audited. Run this audit BEFORE writing code:

```bash
grep -rn "ctx\.editor\|\.editor\.\|TabContext" src/ui/ | sort -u
```

Find `TabContext.__init__` (around line 64). Add new fields. Keep `editor` typed `RequestEditorWidget | None` so existing code can early-return on `None`:

```python
class TabContext:
    def __init__(
        self,
        ...existing args...,
        tab_type: str = "request",                   # NEW: "request" | "script_module"
        script_module_path: Path | None = None,      # NEW
        script_module_editor: QWidget | None = None, # NEW
    ) -> None:
        self.tab_type = tab_type
        self.script_module_path = script_module_path
        self.script_module_editor = script_module_editor
        # Existing: editor / response_viewer / breadcrumb / request_id / is_preview
        if tab_type == "request":
            self.editor = editor or RequestEditorWidget()
        else:
            self.editor = None  # callers must check tab_type before touching editor

    def is_request(self) -> bool:
        return self.tab_type == "request"
```

**Touchpoint checklist** — every one of these must early-return or branch on `is_request()`:
- `cleanup_thread()` — no-op for script-module tabs (no send pipeline).
- `start_send()` — no-op (raises if called on a non-request tab — defensive).
- `send_pipeline.py` send-button handlers — verify `ctx.is_request()` before queue ops.
- `_on_tab_changed` / `_refresh_sidebar` in `tab_controller.py` — branch already in §6.3.
- `tab_close` — save dirty script-module before closing; confirm with user if dirty.
- Session restore (lines 459-485 region) — separate persistence format (§6.5).
- Breadcrumb update — skip for script-module tabs.
- `set_request_dirty` / draft persistence — skip.
- Title-bar / window-title update — use file basename for script-module tabs.

Run the audit grep again after edits to make sure no `ctx.editor.<x>` path is left unguarded.

### 6.3 — Modify `src/ui/main_window/tab_controller.py`

Add a new method:

```python
def _open_script_module_tab(self, path: Path) -> None:
    # If a tab for this path is already open, focus it.
    for tab_id, ctx in self._tabs.items():
        if ctx.tab_type == "script_module" and ctx.script_module_path == path:
            self._tab_bar.setCurrentIndex(self._tab_bar.indexOf(tab_id))
            return
    editor = ScriptModuleEditorWidget(path)
    ctx = TabContext(
        tab_type="script_module",
        script_module_path=path,
        script_module_editor=editor,
    )
    tab_id = self._next_tab_id()  # follow existing convention
    self._tabs[tab_id] = ctx
    self._editor_stack.addWidget(editor)
    title = path.name
    self._tab_bar.add_tab(tab_id, title)
    editor.dirty_changed.connect(
        lambda d, t=tab_id: self._tab_bar.set_dirty(t, d)
    )
    self._tab_bar.setCurrentIndex(self._tab_bar.indexOf(tab_id))
```

Find `_on_tab_changed` (lines 354-414 region). Branch on `tab_type`:

```python
def _on_tab_changed(self, idx: int) -> None:
    tab_id = self._tab_bar.tab_id_at(idx)
    ctx = self._tabs.get(tab_id)
    if ctx is None:
        return
    if ctx.tab_type == "script_module":
        self._editor_stack.setCurrentWidget(ctx.script_module_editor)
        # Hide the response area, breadcrumb, send button — they don't apply.
        self._response_area.setVisible(False)
        self._breadcrumb.setVisible(False)
        return
    # ... existing request-tab branch unchanged.
```

### 6.4 — Wire to scripts panel

In `window.py`, ensure:

```python
self._scripts_panel.file_open_requested.connect(self._open_script_module_tab)
self._scripts_panel.file_deleted.connect(self._on_local_module_deleted)
```

Add handler:

```python
def _on_local_module_deleted(self, path: Path) -> None:
    for ctx in self._tabs.values():
        if ctx.tab_type == "script_module" and ctx.script_module_path == path:
            ctx.script_module_editor.mark_orphan()
```

### 6.5 — Session persistence

Find existing tab restore code in `tab_controller.py` (around lines 459-485). Extend the persisted format to record script-module tabs by path:

```python
{"tab_type": "script_module", "path": str(path)}
```

On restore, silently drop entries whose path doesn't exist.

### 6.6 — Tests `tests/ui/test_script_module_tab.py`

New file. Cases:
1. `test_open_creates_tab_with_editor` — call `_open_script_module_tab(tmp_path/"foo.js")` → new tab appears, `ScriptModuleEditorWidget` in stack.
2. `test_dirty_indicator_on_edit` — type into editor → tab bar `dirty` flag set True.
3. `test_save_writes_to_disk_and_clears_dirty` — modify, Ctrl+S → disk content matches editor, dirty False.
4. `test_open_twice_focuses_existing_tab` — call open twice with same path → only one tab; index is on it.
5. `test_response_area_hidden_for_script_module_tab` — switch to a script-module tab → response area hidden; switch back to request tab → visible again.
6. `test_external_delete_marks_orphan` — emit `file_deleted` signal → banner shown, dirty True.

### 6.7 — Settings UI

**Important**: the existing Settings dialog uses a single monolithic `_do_apply()` method (line 1527) — there is **no** `_apply_callbacks` list. Integration must happen inside the dialog class itself, not via callback registration.

**New file** `src/ui/dialogs/settings_local_modules.py`:

```python
"""Builders for the 'Local modules' Settings subpage.

Returns a built QWidget plus the line-edit so the dialog can wire dirty
tracking and read it from inside ``SettingsDialog._do_apply``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QFileDialog,
)
from services.scripting.runtime_settings import RuntimeSettings


@dataclass
class LocalModulesPage:
    widget: QWidget
    path_edit: QLineEdit


def build_local_modules_page(parent_dialog) -> LocalModulesPage:
    page = QWidget()
    layout = QVBoxLayout(page)

    layout.addWidget(QLabel("<b>Local script modules</b>"))

    help_label = QLabel(
        "Files in this folder can be imported from any request script with "
        "<code>pm.require(\"local:&lt;name&gt;\")</code>. Supported "
        "extensions: <code>.js</code>, <code>.ts</code>, <code>.py</code>. "
        "Subfolders are ignored."
    )
    help_label.setWordWrap(True)
    layout.addWidget(help_label)

    row = QHBoxLayout()
    path_edit = QLineEdit(str(RuntimeSettings.local_modules_dir()))
    browse_btn = QPushButton("Browse…")
    open_btn = QPushButton("Open folder")
    row.addWidget(path_edit, 1)
    row.addWidget(browse_btn)
    row.addWidget(open_btn)
    layout.addLayout(row)
    layout.addStretch()

    def on_browse() -> None:
        d = QFileDialog.getExistingDirectory(
            page, "Local modules folder", path_edit.text()
        )
        if d:
            path_edit.setText(d)

    def on_open() -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path_edit.text()))

    browse_btn.clicked.connect(on_browse)
    open_btn.clicked.connect(on_open)
    # Dialog wires dirty tracking + apply itself (see settings_dialog.py changes).
    path_edit.textChanged.connect(parent_dialog._mark_dirty)
    return LocalModulesPage(widget=page, path_edit=path_edit)
```

Modify [src/ui/dialogs/settings_dialog.py](../../src/ui/dialogs/settings_dialog.py):
1. **Add a child node** under the existing "Scripting" parent in the category tree (look for the section that builds the tree near line 543; pattern mirrors `_build_private_packages_pages` at line 555).
2. **In `__init__`** (or wherever existing Scripting page builders are called, near line 149): call `self._local_modules_page = build_local_modules_page(self)`, then register `self._local_modules_page.widget` in the `QStackedWidget` under key `"local_modules"` (follow the existing private-packages-pages registration pattern verbatim).
3. **In `_do_apply`** (line 1527): add a line near the other persistence calls:
   ```python
   RuntimeSettings.set_local_modules_dir(Path(self._local_modules_page.path_edit.text()))
   ```
4. **Emit a signal or call back into the main window** so `ScriptsPanel._refresh_root()` runs when the path changes (add a `local_modules_dir_changed` signal on `SettingsDialog`, emit from `_do_apply` when the value differs from the original; connect in the dialog opener inside `MainWindow`).

Tests `tests/ui/dialogs/test_settings_local_modules.py`:
1. `test_default_path_shown_when_unset` — `local_modules_dir` unset → text field shows default per-OS path.
2. `test_browse_sets_path_via_dialog` — mock `getExistingDirectory` → text field updated, dirty flag set.
3. `test_apply_persists_path` — set text, simulate Apply → `RuntimeSettings.local_modules_dir()` returns new value.

PR 6 ships once these tests pass and end-to-end manual smoke (below) works.

---

## Section 7 — Docs

Modify [docs/scripting/external-packages.md](../scripting/external-packages.md). Add a top section titled "Local script modules" with:
- Brief: what they are, where to put files (default `<user data>/postmark/scripts/`), configurable via Settings → Scripting → Local script modules.
- Specifier shape table:
  - JS: `pm.require("local:auth.js")` / `pm.require("local:types.ts")`
  - Python: `pm.require("local:utils.py")`
  - **Extension is mandatory.**
- Walkthrough: open Scripts pane via top-of-left-pane icon (or `Ctrl+2`) → click "New module" → file opens in tab → save → call from a request script.
- Composition example: `local:auth.js` imports `npm:jose@5.2.0` (works via union scan).
- Cross-language note: not supported (`pm.require("local:helper.py")` from a JS script errors).
- Pyodide-only note for Python local modules (RestrictedPython subprocess rejects them with a clear error).
- One-line link to "Private packages" section that follows.

Modify [src/AGENTS.md](../../src/AGENTS.md): under scripting, add a bullet pointing to `LocalModuleResolver` and the `local:` specifier syntax (extension-mandatory).

Modify [AGENTS.md](../../AGENTS.md) directory map: list new `src/ui/sidebar/left_pane.py`, `src/ui/sidebar/scripts_panel/`, `src/ui/tabs/script_module_tab.py`, `src/ui/dialogs/settings_local_modules.py`, `src/services/scripting/local_modules.py`, `data/scripts/pm_local_loader.py`.

---

## Order of work

Each PR must keep `poetry run pytest tests/` green.

| PR | Scope | Depends on | User-visible? |
|---|---|---|---|
| 1 | Resolver + settings row (Local script modules path) | — | New section in Settings → Scripting (unused yet) |
| 2 | JS runtime `local:foo.js`/`.ts` support | PR 1 | Devs can drop a file into the folder + call `pm.require("local:foo.js")` from a request script |
| 3 | Python runtime `local:foo.py` (Pyodide) + RestrictedPython error path | PR 1 | Same as PR 2 but for Python |
| 4 | `LeftSidebarPane` shell — toggle row at top, stacked content, Collections page wired (Scripts page = empty stub) | — | **YES — toggle row appears at top of left pane; Collections still default.** |
| 5 | `ScriptsPanel` (toolbar + list + context menu) — wires into stacked page 1 | PR 1, PR 4 | Scripts icon now switches to a working file panel; double-click stub |
| 6 | `ScriptModuleTab` + Settings dialog wiring + `local_modules_dir_changed` signal | PR 2, PR 3, PR 5 | End-to-end feature live |

Backend (PRs 1-3) and UI (PRs 4-6) can stack in parallel reviews. **No feature flag for PR 4** — the toggle row is a small, recoverable change. If something goes wrong, revert that PR; don't ship an env-var hack.

---

## Pre-implementation verification

Before starting PR 1, confirm the following one-time facts (they should be true based on exploration but worth a 30-second check):
- `src/services/scripting/runtime_settings.py` exports a `_get_settings()` helper at module scope. **Use it; never call `QSettings()` directly.** UI code uses `QSettings(_ORG, _APP)` (org/app constants from [src/ui/styling/theme_manager.py](../../src/ui/styling/theme_manager.py) lines 20-22); the `LeftSidebarPane._qsettings()` helper in §4.1 follows this. Bare `QSettings()` calls go to a different namespace and break test isolation.
- `src/services/scripting/deno_manager.py` `runtime_dir()` builds a per-OS data dir. Plan to refactor into a shared `_postmark_user_data_dir()` (Section 1.2) so this lives in one place.
- `src/ui/styling/global_qss.py` builds QSS via Python f-strings against a palette dict `p`. **Qt does not support CSS `var(--…)`.** Use `{p["accent"]}` interpolation.
- `src/ui/dialogs/settings_dialog.py` `_do_apply` (line 1527) is monolithic — there is **no** callback registration list. Plan integrates by adding a line directly inside `_do_apply` (Section 6.7).
- `CodeEditorWidget` API names — check actual signatures at [src/ui/widgets/code_editor/editor_widget.py:122-180](../../src/ui/widgets/code_editor/editor_widget.py#L122) for `setPlainText` vs `set_text`, `toPlainText` vs `text`, `set_language(...)` vs another spelling. Adjust §6.1 method calls to match.
- Scripting directory file-count limit (per [src/AGENTS.md](../../src/AGENTS.md)): if `src/services/scripting/` is near the convention cap, plan to split `local_modules.py` into a subpackage. Check before PR 1.

## Risks / sharp edges

- **Traversal/symlink escape** — resolver uses `resolve(strict=True)` + `relative_to(root)` where root is already canonical. Test with `../escape.js`, `link.js → /etc/passwd`.
- **No silent-ambiguity class** — extension-mandatory specifier means `foo.js` and `foo.ts` can coexist; each has its own specifier. No "ambiguous stem" error possible from the call site.
- **Cycles** — A requires B, B requires A → resolver raises with chain message.
- **Per-execution scan** — bounded by `MAX_LOCAL_MODULES = 500`. Glob is cheap; source read lazily for reached modules.
- **mtime races** — snapshot source at run start; in-flight execs use their snapshot.
- **Read-only root** — Scripts panel detects via `os.access(root, os.W_OK)`; disables mutation buttons + context-menu entries.
- **Tab open when file deleted** — emit `file_deleted` signal; tab marks orphan with banner. Save creates the file again.
- **Cross-language pm.require** — JS user requiring `local:foo.py` not detected by JS regex (silently no-op at scan; bundle then errors at runtime in `pm_bootstrap.js`). Python user requiring `local:helper.js` not detected by Python regex.
- **Pyodide entry script location** — `data/scripts/pyodide_run.mjs` (verified). Section 3.5 spec.
- **CodeEditorWidget API names** — `set_text`/`set_language`/`text()` may differ; check actual names at [src/ui/widgets/code_editor/editor_widget.py](../../src/ui/widgets/code_editor/editor_widget.py) and align in §6.1 before writing code.
- **`sys.modules` shadowing** — loader uses only `__pm_local_<stem>`. A file called `json.py` does NOT replace stdlib `json`. `pm.require("local:json.py")` works via the namespaced lookup; `import json` in user code still resolves to stdlib.
- **LSP on module-tab editors** — out of scope for MVP. Note in docs.
- **Toggle row icons** — confirm `phi("tree-structure")` and `phi("code")` exist in `data/fonts/phosphor-charmap.json` before PR 4 (or pick alternates like `phi("list")`, `phi("file-code")`).
- **Settings path change re-rooting** — `local_modules_dir_changed` signal:
  1. Compute `new_root = RuntimeSettings.local_modules_dir().resolve()`.
  2. For each open script-module tab, compute `tab_path.resolve()`.
  3. If `tab_path` is not under `new_root`, call `mark_orphan()` (same banner as external delete).
  4. `ScriptsPanel.refresh_root()` reloads the list.
- **`ctx.editor` audit** — grep `ctx\.editor\|\.editor\.\|TabContext` is a starting list. Run full test suite after; fix any `AttributeError: 'NoneType' object has no attribute 'editor'` traces.
- **No `QDockWidget` for Scripts** — explicit anti-pattern (see Context). A prior implementation made this mistake. Reviewer should reject any PR that uses `QDockWidget` for the Scripts panel.
- **No vertical activity rail** — explicit anti-pattern. Toggle row is horizontal, inside the left pane.

---

## Verification

After each PR, run the listed unit/UI tests for that PR plus a full sweep:

```
poetry run pytest tests/unit/services/test_local_modules_resolver.py -q          # PR 1
poetry run pytest tests/unit/services/test_runtime_settings.py -q                # PR 1
poetry run pytest tests/unit/services/test_pm_require_local_js.py -q             # PR 2
poetry run pytest tests/unit/services/test_pm_require_local_py.py -q             # PR 3
poetry run pytest tests/unit/services/test_pm_python_parity.py -q                # PR 3
poetry run pytest tests/ui/sidebar/test_left_pane.py -q                          # PR 4
poetry run pytest tests/ui/test_main_window.py -q                                # PR 4
poetry run pytest tests/ui/sidebar/test_scripts_panel.py -q                      # PR 5
poetry run pytest tests/ui/test_script_module_tab.py -q                          # PR 6
poetry run pytest tests/ui/dialogs/test_settings_local_modules.py -q             # PR 6
poetry run pytest tests/ -q                                                      # always
```

End-to-end manual smoke (after PR 6):

1. Launch app. **Toggle row visible at top of left pane**, Collections icon active by default.
2. Settings → Scripting → Local script modules. Path defaults to per-OS default. Click "Open folder" → OS file manager pops to a freshly-created `<user data>/postmark/scripts/` folder.
3. Press `Ctrl+2` (or click Scripts icon). Stacked content swaps to ScriptsPanel; empty state visible.
4. Click "New module" → modal asks for name → `mathx`. `mathx.js` appears in list and opens in a new editor tab.
5. Type `export function add(a,b){ return a+b; }`. Press `Ctrl+S`. Dirty dot disappears.
6. Right-click `mathx.js` → Copy import specifier. Clipboard now has `local:mathx.js` (with extension).
7. Paste into a request's Tests tab: `const m = pm.require("local:mathx.js"); pm.test("adds", () => pm.expect(m.add(1,2)).to.eql(3));`. Send. Test passes.
8. Python: create `helpers.py` via context menu → `def shout(s): return s.upper()`. Python pre-request script: `h = pm.require("local:helpers.py"); pm.environment.set("greet", h.shout("hi"))`. Send. Env var set to "HI".
9. Composition: create `multiplier.js` with `export const mul = (a,b) => a*b;`. Edit `mathx.js` to also export `mul = pm.require("local:multiplier.js").mul;`. Original test still passes; add a test calling `m.mul(2,3)`.
10. Extension mismatch: in a request script, `pm.require("local:mathx.ts")` → error mentions extension mismatch (only `.js` on disk).
11. Path traversal: try to create `../escape.js` via OS file manager outside the modules dir — file appears outside but resolver doesn't list it; `pm.require("local:escape.js")` → "not found" error.
12. Delete `mathx.js` from panel context menu while tab is open → tab shows orphan banner. `Ctrl+S` → file recreated.
13. Right sidebar (variables / snippets / saved responses) still toggles. No regression.
14. Restart app → Toggle row remembers active panel; last-open script-module tabs restored.
15. **No `QDockWidget` exists anywhere in the running UI.** Inspect via `QApplication.allWidgets()` if needed.

---

## Critical files

- [src/services/scripting/js_runtime.py](../../src/services/scripting/js_runtime.py) — JS specifier scanner, imports block
- [src/services/scripting/py_runtime.py](../../src/services/scripting/py_runtime.py) — Python specifier scanner
- [src/services/scripting/pyodide_runtime.py](../../src/services/scripting/pyodide_runtime.py) — IPC payload
- [src/services/scripting/deno_runtime.py](../../src/services/scripting/deno_runtime.py) — bundle + workdir file writes
- [src/services/scripting/runtime_settings.py](../../src/services/scripting/runtime_settings.py) — new `local_modules_dir` key
- `src/services/scripting/local_modules.py` — NEW resolver (link when file lands on disk)
- [data/scripts/pm_bootstrap.py](../../data/scripts/pm_bootstrap.py) — Python `pm.require` `local:` branch
- [data/scripts/pm_bootstrap.js](../../data/scripts/pm_bootstrap.js) — JS hint for `local:` errors
- `data/scripts/pm_local_loader.py` — NEW Pyodide-side registrar (link when file lands on disk)
- [src/ui/collections/collection_widget.py](../../src/ui/collections/collection_widget.py) — unchanged content; reparented under `LeftSidebarPane`
- [src/ui/collections/collection_header.py](../../src/ui/collections/collection_header.py) — unchanged; sits beneath toggle row
- `src/ui/sidebar/left_pane.py` — NEW (`LeftSidebarPane` — toggle row + stacked content; link when file lands on disk)
- [src/ui/sidebar/scripts_panel/](../../src/ui/sidebar/scripts_panel/) — NEW package (`ScriptsPanel` + `actions.py`)
- `src/ui/tabs/script_module_tab.py` — NEW (link when file lands on disk)
- [src/ui/main_window/window.py](../../src/ui/main_window/window.py) — splitter wiring (replace `collection_widget` with `LeftSidebarPane`) + Ctrl+1/+2
- [src/ui/main_window/tab_controller.py](../../src/ui/main_window/tab_controller.py) — script-module tab type
- [src/ui/request/navigation/tab_manager.py](../../src/ui/request/navigation/tab_manager.py) — `TabContext.tab_type` / `script_module_panel` / `script_module_path`
- [src/ui/dialogs/settings_dialog.py](../../src/ui/dialogs/settings_dialog.py) — new "Local script modules" row + `local_modules_dir_changed` signal
- `src/ui/dialogs/settings_local_modules.py` — NEW (row builder; link when file lands on disk)
- [src/ui/styling/global_qss.py](../../src/ui/styling/global_qss.py) — `#leftPaneToggleRow` + `#leftPaneToggleButton` rules
