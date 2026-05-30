# Security

Script execution uses defense-in-depth sandboxing for both JavaScript
and Python runtimes.  This page documents the threat model, sandbox
architecture, and resource limits.

## Threat Model

Postmark is a desktop app — the user runs scripts on their own machine.
Primary threats:

1. **Imported collections with malicious scripts** — a shared Postman
   collection could contain scripts that exfiltrate data or damage the
   filesystem.
2. **Copy-pasted scripts** from untrusted internet sources.
3. **Accidental damage** — infinite loops, memory exhaustion, or app
   state corruption.

Scripts are NOT like browser JavaScript.  The user explicitly imports a
collection or writes a script.  But users often don't read scripts
before running them, so defense-in-depth is mandatory.

## JavaScript (Deno subprocess)

JavaScript runs in a **Deno** child process, not in an embedded V8 in the
Postmark process.  The runner builds a single file (polyfills, allowed vendor
shims, pm bootstrap, user script, and a small drain that prints JSON per line)
and invokes ``deno run`` with a narrow ``--allow-read`` scoped to the
temporary work directory, plus a hard wall-clock timeout that kills the
process if the script or IPC loop hangs.

| Capability | Status | Notes |
|-----------|--------|-------|
| File system (outside workdir) | Not granted by default | Only the temp run directory is allowed for ``deno run`` |
| Direct network in Deno | Not used for typical runs | `pm.sendRequest` is line-JSON IPC to the host, which issues HTTP (`context.py`) |
| `require` / `import` | Controlled | Pre-bundled vendor files only; map in `js_runtime` |
| `eval()` | In user space | Still subject to `deno run` + same bundle as normal execution |

### Resource Limits

| Resource | Limit |
|----------|-------|
| Execution time (Deno process) | 10 seconds (hard) |
| Console messages | 200 per execution (host-side cap) |
| `pm.sendRequest()` calls | 10 (JS-side); 50 total (host-side) |
| Sub-request response size | 10 MB |

Implementation: `src/services/scripting/deno_runtime.py` —
`_SUBPROCESS_TIMEOUT`, `src/services/scripting/js_runtime.py` — sub-request cap
and vendor loading.

## Python Sandbox (Three-Layer Defense)

> **Two Python runtimes — same outer containment.** When Deno and the bundled
> Pyodide assets are present (the default desktop setup), Python scripts run on
> **Pyodide** (CPython compiled to WebAssembly) hosted by a Deno subprocess.
> Otherwise Postmark falls back to a **RestrictedPython** subprocess.  Both are
> contained by the same outer boundary: a child process with a **scrubbed
> environment** (no host secrets — see [Environment isolation](#environment-isolation)),
> no inherited network, and a scoped, read-only temp directory.
>
> - **RestrictedPython** (fallback) also blocks escapes at the *Python* layer —
>   `compile_restricted` + attribute/item guards + a builtins whitelist
>   (Layers 2–3 below); `import` and raw `getattr` are unavailable.
> - **Pyodide** (default) runs user code with a restricted builtin set (no
>   `__import__`, so `import` fails) but does **not** apply RestrictedPython's
>   AST guards, so it is *not* a hard Python-level boundary on its own.  Its
>   security rests on the **outer** Deno/WASM container: even a script that
>   reaches Python internals cannot read your files, host environment/secrets,
>   or open arbitrary network connections — it can only act inside that
>   sandbox and call the rate-limited, host-mediated `pm.sendRequest`.

### Layer 1: Subprocess Isolation

Python scripts run in a separate subprocess
(`src/services/scripting/_py_sandbox.py`).  A crash, exploit, or
resource exhaustion in the subprocess cannot affect the main Postmark
app.

### Layer 2: RestrictedPython Compilation

Scripts are compiled using `compile_restricted()` from RestrictedPython.
This performs AST-level blocking of:

- `import` statements
- `exec()` and `eval()` calls
- Augmented attribute access (all `_`-prefixed attributes blocked)

### Layer 3: Restricted Builtins + Resource Limits

A minimal whitelist of builtins is provided.  Dangerous builtins are
removed:

**Blocked:** `open`, `__import__`, `exec`, `eval`, `compile`,
`globals`, `locals`, `vars`, `dir`, `delattr`, `setattr`, `getattr`
(on `_`-prefixed names), `breakpoint`, `exit`, `quit`, `help`,
`input`, `memoryview`, `object.__subclasses__`.

**Allowed:** `abs`, `all`, `any`, `bool`, `dict`, `enumerate`,
`filter`, `float`, `int`, `isinstance`, `len`, `list`, `map`, `max`,
`min`, `range`, `reversed`, `round`, `set`, `sorted`, `str`, `sum`,
`tuple`, `type` (single-argument only), `zip`.

### Python Resource Limits (Linux)

| Resource | Limit | `rlimit` |
|----------|-------|----------|
| CPU time | 5 seconds | `RLIMIT_CPU` |
| Memory (address space) | 128 MB | `RLIMIT_AS` |
| File descriptors | 3 (stdin/stdout/stderr only) | `RLIMIT_NOFILE` |

Implementation: `_py_sandbox.py::_apply_resource_limits()`.  On
non-Linux systems, limits are best-effort (may not apply).

### Attribute Guard

The `_getattr_guard()` function rejects all access to `_`-prefixed
attributes.  This prevents escape attempts via `__class__`,
`__subclasses__`, `__dict__`, etc.

```text
pm.response.__class__  --> AttributeError: Attribute access denied: __class__
```

## Safe Standard Library

Python scripts cannot import modules.  Instead, a curated set of
functions is pre-injected into the script namespace.  See
[Python API Reference](python-api.md) for the full list.

## Console Rate Limiting

Both runtimes cap console output at 200 messages per execution.
Messages beyond the limit are silently dropped.

## Environment isolation

Script subprocesses receive a **minimal environment** — only the operational
variables the Deno / Pyodide / npm toolchain needs to run (`PATH`, `HOME`,
locale, temp dirs, …).  Host secrets in the parent process (cloud credentials,
API tokens, …) are **never forwarded**, so a script cannot read them via
`Deno.env` / `os.environ` and exfiltrate them through `pm.sendRequest`.

Postman-style variables (`pm.environment`, `pm.variables`, `pm.globals`,
`{{var}}`) are unaffected — they travel in the script payload, not the process
environment.

Implementation: `src/services/scripting/_subprocess_env.py`
(`safe_subprocess_env`).

## What Scripts CAN Do

- Read request/response data via `pm.request` / `pm.response`.
- Set/get variables across scopes.
- Register named test assertions.
- Mutate the request in pre-request scripts.
- Parse JSON, use regex, compute hashes (MD5, SHA-256, HMAC-SHA256),
  encode/decode base64, generate UUIDs.
- Write to the Console panel via `console.log()` / `print()`.
- (JavaScript only) Use bundled libraries via `require()` — see
  [Built-in Libraries](javascript-api.md#built-in-libraries) for the
  full list.  These run inside the same V8 isolate and share its
  resource limits.

## What Scripts CANNOT Do

- Access the filesystem.
- Make network requests except via `pm.sendRequest()` (http/https only,
  rate-limited, 10 MB response cap) — which is also **blocked from
  loopback / private / link-local / cloud-metadata hosts by default** (SSRF
  protection; opt in with `scripting/allow_local_subrequests`).
- Import arbitrary modules (Python) or require arbitrary packages.  Python
  `pm.require` is allowlisted to bundled modules; JavaScript `require` serves
  pre-bundled libraries, and `pm.require('npm:…')` resolves declared packages.
- Access Postmark's internal state or database.
- Spawn processes.
- Read host OS/shell environment variables or secrets — the subprocess
  environment is scrubbed (Postman `{{variables}}` remain available).
- Persist data outside of variables.
- Run longer than the timeout allows.

## Credential storage (private package registries)

When the user configures a private npm / JSR / PyPI registry, auth tokens
go through `services.scripting.secret_store`:

| Backend | When chosen | Risk profile |
|---------|-------------|--------------|
| `KeyringSecretStore` (OS keychain) | Default — `keyring` importable AND its backend passes a write/read self-test | Token protected by the OS user account (Keychain unlock, GNOME Keyring session, Credential Manager) |
| `EncryptedFileSecretStore` (Fernet) | Fallback when keyring fails or is missing | Token decryptable by anyone with disk + login access to this machine (machine-id-derived key). Dialog surfaces a "less safe" warning. |
| `NoopSecretStore` | Both `keyring` and `cryptography` are missing | Secrets silently dropped; registries resolve anonymously |

Generated `.npmrc` files are chmod `0600` so other Unix users on the same
host cannot read them. Tokens are resolved into the file at spawn time
(see `services.scripting.deno_runtime._build_npmrc_text`) rather than
left as `${NPM_TOKEN}` placeholders, because Deno's env-var expansion in
`.npmrc` is documented as unreliable
([supabase/cli#4927](https://github.com/supabase/cli/issues/4927)).

PyPI tokens are embedded in the index URL
(`https://user:token@pypi.mycorp.io/simple/`) and passed to
`micropip.set_index_urls(…)`; they live only in the Pyodide subprocess
memory for the lifetime of one script run.

## For Contributors

### Adding Sandbox Tests

Every sandbox escape attempt MUST be covered by a test in
`tests/unit/services/test_script_sandbox.py`.  Test categories:

1. **Import blocking** — `import os`, `__import__("os")`.
2. **Attribute escape** — `__class__.__subclasses__()`.
3. **Builtin abuse** — `open()`, `exec()`, `eval()`.
4. **Resource exhaustion** — infinite loop, large allocation.
5. **getattr bypass** — `_`-prefixed attribute access.

### Security Test Requirements

Security tests are part of CI.  If a sandbox test fails, the build
fails.  New sandbox features must include escape-attempt tests.
