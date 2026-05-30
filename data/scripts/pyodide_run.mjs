// Postmark Python scripts via Pyodide (Deno subprocess).
//
// Stdin: one JSON line { user_script, context, pm_require: string[] }
// Stdout: JSON lines — optional { __ipc__: "sendRequest", spec } then final { __done__: true, ... }.
//
// 1. Read the first line from stdin (host payload).
// 2. loadPyodide from ./vendor_pyodide/ (offline runtime).
// 3. micropip-install pm_require specs (optional network).
// 4. Run data/scripts/pm_bootstrap.py (sets pm, init_pm, run_user_script).
// 5. Stream sendRequest IPC on stdout / read responses on stdin (node:fs sync).

import { readFileSync, readSync, writeSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const require = createRequire(import.meta.url);
if (typeof globalThis.require === "undefined") {
  globalThis.require = require;
}
if (typeof globalThis.__dirname === "undefined") {
  globalThis.__dirname = __dirname;
}
if (typeof globalThis.__filename === "undefined") {
  globalThis.__filename = __filename;
}
if (typeof globalThis.setImmediate === "undefined") {
  globalThis.setImmediate = function (fn, ...args) {
    return setTimeout(fn, 0, ...args);
  };
}

const { loadPyodide } = await import("./vendor_pyodide/pyodide.mjs");

const _here = __dirname;
const indexURL = join(_here, "vendor_pyodide") + "/";

function readLineFromStdin() {
  const parts = [];
  const u8 = new Uint8Array(1);
  while (true) {
    let n;
    try {
      n = readSync(0, u8);
    } catch (_e) {
      return null;
    }
    if (n === 0) {
      return null;
    }
    if (u8[0] === 10) {
      break;
    }
    if (u8[0] === 13) {
      continue;
    }
    parts.push(String.fromCharCode(u8[0]));
  }
  return parts.join("");
}

function readFirstJsonLine() {
  const line = readLineFromStdin();
  if (line == null) {
    throw new Error("no stdin");
  }
  return JSON.parse(line);
}

function writeDone(payload) {
  payload.__done__ = true;
  const line = JSON.stringify(payload) + "\n";
  writeSync(1, new TextEncoder().encode(line));
}

const _pyConsole = [];

function pushStdout(text) {
  const s = String(text);
  for (const line of s.split("\n")) {
    if (!line.trim()) {
      continue;
    }
    _pyConsole.push({ level: "log", message: line, timestamp: Date.now() / 1000 });
    if (_pyConsole.length > 200) {
      _pyConsole.shift();
    }
  }
}

function pushStderr(text) {
  const s = String(text).trimEnd();
  if (!s) {
    return;
  }
  _pyConsole.push({ level: "error", message: s, timestamp: Date.now() / 1000 });
  if (_pyConsole.length > 200) {
    _pyConsole.shift();
  }
}

async function main() {
  let inp;
  try {
    inp = readFirstJsonLine();
  } catch (e) {
    writeDone({
      error: String(e),
      test_results: [],
      console_logs: [],
      variable_changes: {},
      request_mutations: null,
    });
    return;
  }

  const cacheDir =
    Deno.env.get("PM_PYODIDE_CACHE") ||
    `${Deno.env.get("HOME") ?? ""}/.cache/postmark/pyodide/pkgs`;

  let pyodide;
  try {
    pyodide = await loadPyodide({
      indexURL,
      packageCacheDir: cacheDir,
      stdout: pushStdout,
      stderr: pushStderr,
    });
  } catch (e) {
    writeDone({
      error: `loadPyodide failed: ${String(e)}`,
      test_results: [],
      console_logs: [],
      variable_changes: {},
      request_mutations: null,
    });
    return;
  }

  const pmReq = Array.isArray(inp.pm_require) ? inp.pm_require : [];
  const pypiIndexes = Array.isArray(inp.pypi_index_urls) ? inp.pypi_index_urls : [];
  if (pmReq.length > 0) {
    try {
      await pyodide.loadPackage("micropip");
      const micropip = pyodide.pyimport("micropip");
      if (pypiIndexes.length > 0) {
        // Route ``micropip.install`` through the configured private PyPI
        // index(es) before any package fetch. Auth is embedded in the URL
        // (e.g. ``https://user:token@pypi.mycorp.io/simple/``) — that's the
        // only format ``micropip`` honours since it has no .netrc parsing.
        micropip.set_index_urls(pypiIndexes);
      }
      for (const spec of pmReq) {
        await micropip.install(spec);
      }
      // Pyodide ships several CPython stdlib modules as separate packages
      // (ssl, sqlite3, lzma …). Common PyPI packages assume they exist
      // because they're stdlib in CPython but must be loaded explicitly
      // here, e.g. PyJWT's ``jwks_client`` does ``from ssl import ...``.
      // Pre-load the cheap ones so transitive imports inside installed
      // packages don't fail with ``ModuleNotFoundError: 'ssl'``.
      await pyodide.loadPackage(["ssl"]).catch(() => {});
    } catch (e) {
      writeDone({
        error: `micropip install failed: ${String(e)}`,
        test_results: [],
        console_logs: _pyConsole.slice(),
        variable_changes: {},
        request_mutations: null,
      });
      return;
    }
  }

  pyodide.registerJsModule("postmark_ipc", {
    send_request_sync: (jsonLine) => {
      const enc = new TextEncoder();
      const spec = JSON.parse(String(jsonLine));
      writeSync(1, enc.encode(JSON.stringify({ __ipc__: "sendRequest", spec }) + "\n"));
      const respLine = readLineFromStdin();
      if (respLine == null) {
        throw new Error("no IPC response for sendRequest");
      }
      return respLine;
    },
  });

  const dynvarPath = join(_here, "dynamic_variables.json");
  const dynvarSrc = readFileSync(dynvarPath, { encoding: "utf-8" });
  await pyodide.runPythonAsync(`__pm_dynvar_json = ${JSON.stringify(dynvarSrc)}`);

  const dynFragPath = join(_here, "pm_dynamic_vars.py");
  const dynFragSrc = readFileSync(dynFragPath, { encoding: "utf-8" });
  await pyodide.runPythonAsync(dynFragSrc);

  const jsonSchemaPath = join(_here, "pm_json_schema.py");
  const jsonSchemaSrc = readFileSync(jsonSchemaPath, { encoding: "utf-8" });
  await pyodide.runPythonAsync(jsonSchemaSrc);

  const bootstrapPath = join(_here, "pm_bootstrap.py");
  const bootstrapSrc = readFileSync(bootstrapPath, { encoding: "utf-8" });

  const ctxStr = JSON.stringify(inp.context || {});
  await pyodide.runPythonAsync(`__pm_context_json = ${JSON.stringify(ctxStr)}`);
  await pyodide.runPythonAsync(bootstrapSrc);
  await pyodide.runPythonAsync("init_pm()");
  await pyodide.runPythonAsync("__pm_user_script_line0 = 0");

  try {
    await pyodide.runPythonAsync(`run_user_script(${JSON.stringify(inp.user_script || "")})`);
  } catch (e) {
    writeDone({
      error: String(e),
      test_results: [],
      console_logs: _pyConsole.slice(),
      variable_changes: {},
      request_mutations: null,
    });
    return;
  }

  let inner;
  try {
    inner = pyodide.runPython(
      "import json; json.dumps(collect_pm_output())",
    );
  } catch (e) {
    writeDone({
      error: String(e),
      test_results: [],
      console_logs: _pyConsole.slice(),
      variable_changes: {},
      request_mutations: null,
    });
    return;
  }

  const result = JSON.parse(inner);
  const mergedLogs = (result.console_logs || []).concat(_pyConsole);
  if (mergedLogs.length > 200) {
    mergedLogs.splice(0, mergedLogs.length - 200);
  }
  result.console_logs = mergedLogs;
  result.error = null;
  writeDone(result);
}

main().catch((e) => {
  writeDone({
    error: String(e),
    test_results: [],
    console_logs: [],
    variable_changes: {},
    request_mutations: null,
  });
});
