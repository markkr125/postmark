"""JavaScript helpers: bootstrap, vendor shims, and :class:`JSRuntime` (Deno delegation).

Deno :class:`DenoRuntime` and :mod:`deno_debug` use these loaders to build
bundles.  ``pm.sendRequest`` is processed from Python in the Deno drain
(see :mod:`deno_runtime`).

- **pm.sendRequest:** 50 total sub-requests per execution (see
  ``_MAX_TOTAL_SUBREQUESTS``).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from services.scripting.local_script_modules import LocalScriptModule

if TYPE_CHECKING:
    from services.scripting import ScriptInput, ScriptOutput

logger = logging.getLogger(__name__)

# Path to the bootstrap JS preamble.
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "scripts"
_BOOTSTRAP_PATH = _SCRIPTS_DIR / "pm_bootstrap.js"
_VENDOR_DIR = _SCRIPTS_DIR / "vendor"

# Polyfills always loaded (small, provides crypto/atob/btoa/window shims).
_POLYFILLS_FILE = "polyfills.js"

# Map from require('name') → vendor file(s) to load.
# Order within each list matters — dependencies first.
# ``None`` means the module is provided by pm_bootstrap.js (no extra file).
_REQUIRE_MAP: dict[str, list[str] | None] = {
    "crypto-js": ["crypto-js.js"],
    "lodash": ["lodash.js"],
    "moment": ["moment.js"],
    "chai": ["chai.js"],
    "tv4": ["tv4.js"],
    "ajv": ["ajv.js"],
    "xml2js": ["xml2js.js"],
    "csv-parse/sync": ["buffer-polyfill.js", "csv-parse.js"],
    "uuid": None,  # built into bootstrap
}

# Regex to detect require('module-name') in user scripts.
_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")

# Global identifiers that imply a vendor module (used without require()).
_GLOBAL_IMPLIES: dict[str, str] = {
    "CryptoJS": "crypto-js",
}

# Cached sources — loaded once on first use.
_bootstrap_source: str | None = None
_polyfills_source: str | None = None
_vendor_cache: dict[str, str] = {}


def _get_polyfills() -> str:
    """Return cached polyfills JS source, loading on first call."""
    global _polyfills_source
    if _polyfills_source is None:
        path = _VENDOR_DIR / _POLYFILLS_FILE
        _polyfills_source = path.read_text(encoding="utf-8")
    return _polyfills_source


def _get_vendor_file(name: str) -> str:
    """Return cached vendor JS source for *name*, loading on first call."""
    if name not in _vendor_cache:
        path = _VENDOR_DIR / name
        _vendor_cache[name] = path.read_text(encoding="utf-8")
    return _vendor_cache[name]


def _detect_required_modules(script: str) -> set[str]:
    """Scan *script* for ``require('name')`` calls and global names."""
    mods = set(_REQUIRE_RE.findall(script))
    for global_name, mod_name in _GLOBAL_IMPLIES.items():
        if global_name in script:
            mods.add(mod_name)
    return mods


def _resolve_vendor_files(modules: set[str]) -> list[str]:
    """Return de-duplicated, ordered list of vendor files to load."""
    seen: set[str] = set()
    result: list[str] = []
    for mod in sorted(modules):
        files = _REQUIRE_MAP.get(mod)
        if files is None:
            continue
        for f in files:
            if f not in seen:
                seen.add(f)
                result.append(f)
    return result


_PM_REQUIRE_RE = re.compile(
    r"""pm\s*\.\s*require\s*\(\s*['"]"""
    r"""(?P<reg>npm|jsr):(?P<name>@?[\w./-]+?)"""
    r"""(?:@(?P<ver>[^'"]+))?['"]\s*\)""",
)
_NPM_NAME_RE = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*(/[\w./-]+)?$", re.IGNORECASE)
_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-+][\w.\-+]+)?$")


class PmRequireSpec(NamedTuple):
    """A literal ``pm.require('npm:…'|'jsr:…')`` specifier found in the user script."""

    registry: str
    name: str
    version: str

    @property
    def specifier(self) -> str:
        """URL fragment passed to Deno static ``import``."""
        if self.version:
            return f"{self.registry}:{self.name}@{self.version}"
        return f"{self.registry}:{self.name}"

    @property
    def ident(self) -> str:
        """Safe identifier suffix for generated ``__pm_req_*`` symbols."""
        raw = f"{self.registry}_{self.name}_{self.version or 'latest'}"
        return re.sub(r"[^A-Za-z0-9_]", "_", raw)


def _detect_pm_require_specs(script: str) -> list[PmRequireSpec]:
    """Collect unique ``pm.require('npm:…'|'jsr:…')`` string literals from *script*."""
    seen: dict[tuple[str, str, str], PmRequireSpec] = {}
    for m in _PM_REQUIRE_RE.finditer(script):
        reg, name, ver = m.group("reg"), m.group("name"), m.group("ver") or ""
        if not _NPM_NAME_RE.match(name):
            raise ValueError(f"pm.require: invalid {reg} package name {name!r}")
        if ver and not _EXACT_VERSION_RE.match(ver):
            raise ValueError(
                f"pm.require: version must be exact (got {ver!r}). "
                "Ranges and tags like '^1.0' or 'latest' are not supported."
            )
        seen[(reg, name, ver)] = PmRequireSpec(reg, name, ver)
    return list(seen.values())


def _local_module_ident(rel_path: str) -> str:
    """Safe identifier suffix for a local virtual path."""
    return re.sub(r"[^A-Za-z0-9_]", "_", rel_path)


def _pm_require_local_imports_block(
    local_modules: dict[str, LocalScriptModule],
) -> str:
    """Emit static imports for DB local scripts under ``./local/``."""
    if not local_modules:
        return ""
    lines: list[str] = []
    entries: list[str] = []
    for rel_path in sorted(local_modules):
        var = f"__pm_local_{_local_module_ident(rel_path)}"
        import_path = f"./local/{rel_path}"
        lines.append(f"import * as {var} from {json.dumps(import_path)};")
        spec = f"local:{rel_path}"
        entries.append(f"  {json.dumps(spec)}: {var}.default ?? {var}")
    lines.append("globalThis.__pm_require_modules = Object.assign(")
    lines.append("  globalThis.__pm_require_modules || {}, {")
    lines.append(",\n".join(entries))
    lines.append("});")
    return "\n".join(lines) + "\n"


def _pm_require_imports_block(
    specs: list[PmRequireSpec],
    local_modules: dict[str, LocalScriptModule] | None = None,
) -> str:
    """Emit static ESM imports plus ``globalThis.__pm_require_modules`` registration."""
    parts: list[str] = []
    if local_modules:
        parts.append(_pm_require_local_imports_block(local_modules))
    if not specs:
        return "".join(parts)
    lines: list[str] = []
    entries: list[str] = []
    for s in specs:
        var = f"__pm_req_{s.ident}"
        lines.append(f"import * as {var} from {json.dumps(s.specifier)};")
        entries.append(f"  {json.dumps(s.specifier)}: {var}.default ?? {var}")
        bare = f"{s.registry}:{s.name}"
        if s.version and bare != s.specifier:
            entries.append(f"  {json.dumps(bare)}: {var}.default ?? {var}")
    lines.append("globalThis.__pm_require_modules = Object.assign(")
    lines.append("  globalThis.__pm_require_modules || {}, {")
    lines.append(",\n".join(entries))
    lines.append("});")
    parts.append("\n".join(lines) + "\n")
    return "".join(parts)


def prepare_pm_require_bundle(
    script: str,
    *,
    language: str,
) -> tuple[str, bool, dict[str, LocalScriptModule]]:
    """Resolve local closure, union-scan npm/jsr, return scan text + ``needs_net``."""
    from services.scripting.local_script_modules import resolve_required

    local_mods = resolve_required(script, language)
    union_parts = [script, *(m.source for m in local_mods.values())]
    union_source = "\n".join(union_parts)
    specs = _detect_pm_require_specs(union_source)
    needs_net = bool(specs)
    return union_source, needs_net, local_mods


def write_local_modules_to_workdir(
    workdir: Path,
    local_modules: dict[str, LocalScriptModule],
) -> None:
    """Materialize resolved local scripts under ``<workdir>/local/``."""
    base = workdir / "local"
    for mod in local_modules.values():
        dest = base / mod.rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(mod.source, encoding="utf-8")


def _get_bootstrap() -> str:
    """Return the bootstrap JS source, caching after first read."""
    global _bootstrap_source
    if _bootstrap_source is None:
        _bootstrap_source = _BOOTSTRAP_PATH.read_text(encoding="utf-8")
    return _bootstrap_source


def _empty_output() -> ScriptOutput:
    """Return an empty ``ScriptOutput`` dict."""
    return {
        "test_results": [],
        "console_logs": [],
        "variable_changes": {},
        "request_mutations": None,
    }


class JSRuntime:
    """Execute JavaScript via :class:`DenoRuntime` (``deno run`` subprocess).

    Kept for tests and compatibility; the app runs JS through
    :class:`DenoRuntime` in the engine.
    """

    @staticmethod
    def execute(script: str, context: ScriptInput) -> ScriptOutput:
        """Run *script* with *context*; delegates to :class:`DenoRuntime`."""
        from services.scripting.deno_runtime import DenoRuntime

        return DenoRuntime.execute(script, context, language="javascript")


def _build_js_context(context: ScriptInput) -> dict[str, Any]:
    """Convert ``ScriptInput`` to the shape expected by ``pm_bootstrap.js``."""
    req = context.get("request", {})
    # Convert headers dict to list of {key, value} for the JS side.
    raw_headers = req.get("headers", {})
    if isinstance(raw_headers, dict):
        header_list = [{"key": k, "value": v} for k, v in raw_headers.items()]
    else:
        header_list = raw_headers

    resp = context.get("response")
    resp_data = None
    if resp:
        resp_headers = resp.get("headers", {})
        if isinstance(resp_headers, dict):
            resp_header_list = [{"key": k, "value": v} for k, v in resp_headers.items()]
        else:
            resp_header_list = resp_headers
        # Inline panels and ``send_pipeline`` use ``code`` / ``responseTime`` /
        # ``responseSize``; the HTTP layer uses ``status_code`` / ``elapsed_ms`` /
        # ``size_bytes``. Accept both so ``pm.response.code`` matches the UI.
        raw_status = resp.get("status_code")
        if raw_status is None:
            raw_status = resp.get("code", 0)
        try:
            status_code = int(raw_status or 0)
        except (TypeError, ValueError):
            status_code = 0
        elapsed = resp.get("elapsed_ms")
        if elapsed is None:
            elapsed = resp.get("responseTime", 0)
        try:
            response_time = float(elapsed or 0)
        except (TypeError, ValueError):
            response_time = 0.0
        size_raw = resp.get("size_bytes")
        if size_raw is None:
            size_raw = resp.get("responseSize", 0)
        try:
            response_size = int(size_raw or 0)
        except (TypeError, ValueError):
            response_size = 0
        resp_data = {
            "status_code": status_code,
            "status": resp.get("status", ""),
            "headers": resp_header_list,
            "body": resp.get("body", ""),
            "response_time": response_time,
            "response_size": response_size,
        }

    out: dict[str, Any] = {
        "request": {
            "url": req.get("url", ""),
            "method": req.get("method", "GET"),
            "headers": header_list,
            "body": req.get("body", ""),
        },
        "response": resp_data,
        "variables": context.get("variables", {}),
        "environment_vars": context.get("environment_vars", {}),
        "collection_vars": context.get("collection_vars", {}),
        "global_vars": context.get("global_vars", {}),
        "info": context.get("info", {}),
        "is_pre_request": resp is None,
        "iteration_data": context.get("iteration_data", {}),
    }
    if resp_data is not None:
        out["original_request"] = {
            "url": req.get("url", ""),
            "method": req.get("method", "GET"),
            "headers": header_list,
            "body": req.get("body", ""),
        }
    loc = context.get("execution_location")
    if isinstance(loc, dict):
        out["execution_location"] = loc
    else:
        info = context.get("info", {})
        folder = str(info.get("folderName", "") or info.get("folderPath", "") or "")
        out["execution_location"] = {"current": folder}
    return out


# Hard cap on total sub-requests (Deno :mod:`deno_runtime` + :mod:`deno_debug` IPC).
_MAX_TOTAL_SUBREQUESTS = 50
