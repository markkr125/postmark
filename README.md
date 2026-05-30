<p align="center">
  <img src="data/images/logo.png" alt="Postmark logo" width="200" />
</p>

<h1 align="center">Postmark</h1>

<p align="center">
  A local-first desktop API client with a Postman-compatible scripting engine.<br/>
  Design, test, and automate HTTP requests — built with <strong>PySide6</strong> and <strong>SQLAlchemy</strong>.
</p>

---

Postmark is a native desktop API client for testing and managing HTTP requests. Organise
requests into collections, drive them with a full **JavaScript/TypeScript and Python**
scripting engine, and write your tests with **IDE-grade code intelligence** — autocomplete,
inline diagnostics, a step-through debugger, and a side-by-side version diff. Existing
Postman scripts run unmodified through a comprehensive, sandboxed `pm.*` API.

## Scripting at a glance

Write pre-request and post-response (test) scripts in JavaScript/TypeScript or Python — the
same `pm.*` API in both:

```js
// Post-response (test) script — JavaScript
pm.test("status is 200", () => {
  pm.expect(pm.response.code).to.equal(200);
});

const body = pm.response.json();
pm.expect(body).to.have.property("id");
pm.environment.set("token", body.token);   // reuse in the next request
```

```python
# Post-response script — Python (Pyodide), same pm.* API in snake_case
pm.test("status is 200", lambda: pm.expect(pm.response.code).to.equal(200))
pm.environment.set("token", pm.response.json()["token"])
```

## Features

### Requests & Collections
- Organise requests into nested collections (folders), with drag-and-drop reordering and in-place rename (rollback on failure)
- Import from **Postman collections, cURL commands, or raw URLs**
- **GraphQL support** — schema introspection, syntax highlighting, and prettify
- Tabbed request editing with breadcrumb navigation and back/forward **tab history**
- Response viewer with search, **JSONPath/XPath filtering**, and beautify; metadata popups for status, timing, size, and network/TLS details
- Generate request code in **cURL and 20+ languages**
- **Collection runner** — run every request under a folder in sequence with per-request test results, **data-driven CSV/JSON iterations**, flow control (`setNextRequest`/`skipRequest`), and result export (JSON / JUnit XML)
- Background, non-blocking data loading with SQLite persistence via SQLAlchemy

### Scripting & Automation
- **JavaScript & TypeScript** scripts run in a sandboxed **Deno** subprocess; **Python** scripts run on a bundled **Pyodide** (WASM) runtime
- **Postman-compatible `pm.*` API** (`pm.environment`, `pm.globals`, `pm.collectionVariables`, `pm.request`, `pm.response`, `pm.test`, `pm.expect`, `pm.sendRequest`, `pm.cookies`, `pm.iterationData`, …) — paste Postman scripts and run them as-is
- **Chai-style assertions** via `pm.test()` + `pm.expect(...)`, plus a no-code **Assertions tab** for response checks without writing code
- **Script inheritance** — scripts cascade collection → folder → request (pre-request top-down, tests bottom-up)
- **Step-through debugger** — breakpoints (including conditional), step over/into/out, call stack, variable & watch inspector, and break-on-exception; breakpoints persist per request
- **Real HTTP from scripts** via `pm.sendRequest` (host-executed and rate-limited) for fetching tokens or chaining calls
- **Postman dynamic variables** — `{{$guid}}`, `{{$randomInt}}`, `{{$isoTimestamp}}`, and many more
- **Defense-in-depth sandbox** — scripts run with no filesystem, network, or OS access (network only through `pm.sendRequest`), bounded by per-run time and memory limits

### Code Intelligence
- Real **language servers** back the script editors — **Deno** for JavaScript/TypeScript, **jedi** for Python
- **IntelliSense autocomplete** that merges the `pm.*` API with members of the packages and local modules you import
- **Live diagnostics** in a dedicated Problems panel, hover documentation, signature/parameter hints, and **go-to-definition**
- **Format-on-save** (`deno fmt` / Ruff) and inline validation that flags unsupported `pm`/`postman` usage and ESM↔CommonJS mismatches before you run

### Packages & Libraries
- Bundled, **offline `require()` libraries** in JavaScript — lodash, moment, CryptoJS, Chai, tv4, Ajv, xml2js, and csv-parse
- **External packages on demand** via `pm.require` — `npm:` and `jsr:` specifiers in JavaScript (resolved by Deno) and **PyPI** packages in Python (via micropip), cached after first fetch
- **Private / self-hosted registries** with per-scope auth; credentials stored in the OS keychain (with an encrypted-file fallback), never in plain settings

### Snippets & Local Scripts
- **In-editor Snippets palette** — a searchable popover that inserts ready-made `pm.*` boilerplate at the cursor, filtered to the current pre-request vs. test context
- **Personal snippets** you create, edit, rename, and organise by category from the sidebar — or **"Save selection as snippet"** straight from the editor
- **Local scripts** — a sidebar tree of standalone, reusable script files (JavaScript, TypeScript, Python) that open as full editors with Run, Debug, and Problems
- Call local modules from any script via **`pm.require("local:…")`**, import/export between files like a small TypeScript project, with **safe rename/move** that auto-rewrites references everywhere

### Environments & Secrets
- Environment variables with a key-value editor and **`{{var}}` substitution**
- **Inline environment switching** in the sidebar — set active, clear, or open the full environment editor without leaving your collections
- **Encrypted credential storage** for private package registries (OS keychain or encrypted file); secrets are resolved only at run time and never written to plain settings

### History & Versioning
- **Automatic script version history** — snapshots saved as you edit, with a searchable timeline and one-click restore
- **Side-by-side diff viewer** — two-column, syntax-highlighted diffs with intra-line change marking, change navigation, and whitespace-aware comparison
- **Collection run history** — per-run totals (pass/fail/skip, duration, average response time) with a per-request breakdown

### Workspace & UI
- **VS Code-style left activity rail** with collapsible flyout pages: **Collections & Environments** and **Local scripts & snippets**
- **Bulk key-value editing** — paste many params/headers as one-row-per-line text (`key: value`); prefix a line with `//` to keep but disable it
- Resizable key-value columns with inline `{{variable}}` highlighting (distinct colour for unresolved variables)
- **Theme support** — automatic OS dark/light detection with manual override — plus Fusion or native widget style and Hi-DPI scaling

## Prerequisites

- **Python 3.12+**
- [**Poetry**](https://python-poetry.org/) for dependency management

> JavaScript scripting runs on **Deno** and Python scripting on a bundled **Pyodide** runtime.
> See [Scripting → Overview](docs/scripting/overview.md) for runtime setup and configuration.

## Setup

```bash
# Clone the repository
git clone <repo-url> && cd postmark

# Install dependencies (creates a virtualenv in .venv/)
poetry install

# Install dev tools (linter, type checker, test runner)
poetry install --with dev
```

## Running

```bash
poetry run python src/main.py
```

Or use the VS Code task **Run main with Poetry** (`Ctrl+Shift+B`).

## Development

```bash
# Lint
poetry run ruff check src/

# Format
poetry run ruff format src/

# Type check
poetry run mypy src/

# Run tests
poetry run pytest
```

## Architecture

`src/` is organised into three layers: **`database/`** (SQLAlchemy models and repositories),
**`services/`** (business logic bridging UI and DB), and **`ui/`** (PySide6 widgets). Tests in
`tests/` mirror the source tree. See [`AGENTS.md`](AGENTS.md) for the full architecture tree and
coding conventions, and [docs/architecture/overview.md](docs/architecture/overview.md) for a
narrative walkthrough (including the [script runtime](docs/architecture/script-runtime.md)).

## Documentation

Full documentation lives under [`docs/`](docs/README.md):

- **Getting started** — [overview](docs/getting-started/overview.md) · [installation](docs/getting-started/installation.md) · [running](docs/getting-started/running.md)
- **Scripting** — [overview](docs/scripting/overview.md) · [JavaScript API](docs/scripting/javascript-api.md) · [Python API](docs/scripting/python-api.md) · [Postman parity](docs/scripting/postman-parity.md) · [examples](docs/scripting/examples.md)
- **Packages & modules** — [external packages](docs/scripting/external-packages.md) · [local modules](docs/scripting/local-modules.md) · [snippets](docs/scripting/snippets.md) · [security](docs/scripting/security.md)
- **Runner & UI** — [collection runner](docs/scripting/collection-runner.md) · [request editor](docs/ui-reference/request-editor.md) · [sidebar](docs/ui-reference/sidebar.md) · [local scripts](docs/ui-reference/local-scripts.md)
- **Contributing** — [writing scripts](docs/guides/writing-scripts.md) · [writing tests](docs/guides/writing-tests.md) · [adding a script language](docs/guides/adding-script-language.md)
