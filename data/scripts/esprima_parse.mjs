// One-shot: parse a JS file with our vendored esprima (Node require).
// Invoked: deno run --allow-read=... this.mjs <source.js>
// Emits a single JSON line to stdout: { ok: true, tree } or { ok: false, line, column, message }.

import { createRequire } from "node:module";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const esprima = require(path.join(__dirname, "vendor", "esprima.js"));
const p = Deno.args[0];
if (!p) {
  console.log(
    JSON.stringify({ ok: false, line: 1, column: 1, message: "missing source path" }),
  );
  Deno.exit(1);
}
const src = await Deno.readTextFile(p);
try {
  const tree = esprima.parseScript(src, { loc: true, tolerant: false });
  console.log(JSON.stringify({ ok: true, tree: tree }));
} catch (e) {
  const line = e.lineNumber != null ? e.lineNumber : 1;
  const col = e.column != null ? e.column + 1 : 1;
  const msg = e.description != null ? e.description : (e.message != null ? e.message : String(e));
  console.log(JSON.stringify({ ok: false, line, column: col, message: msg }));
}
