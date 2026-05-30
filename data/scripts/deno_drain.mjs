// Appended to the end of a bundled user script; runs only under Deno.
// The bundle must begin with: import { readSync, writeSync } from "node:fs";
// (see deno_runtime._NODE_FS_IMPORT). Deno 2.x no longer has Deno.writeSync / Deno.readSync.
// Drains `__pm_state._send_queue` via line JSON IPC to the host (see `deno_runtime.py`),
// then prints a final `__done__` line matching the MiniRacer extraction shape.
await (async function __denoIpcDrain() {
  var _MAX_R = 20, _MAX_T = 50;
  var enc = new TextEncoder();
  var total = 0;
  for (var r = 0; r < _MAX_R; r++) {
    var q = __pm_state._send_queue;
    if (!q || q.length === 0) { break; }
    __pm_state._send_queue = [];
    for (var i = 0; i < q.length; i++) {
      total += 1;
      if (total > _MAX_T) {
        __pm_state.console_logs.push({
          level: "error",
          message: "[Script] pm.sendRequest total limit exceeded",
          timestamp: Date.now() / 1000,
        });
        await __printDone();
        return;
      }
      var item = q[i] || {};
      var spec = item.spec || {};
      var idx = parseInt(item.callbackIndex, 10) | 0;
      var u = (spec && spec.url) ? String(spec.url) : "";
      var m = (spec && spec.method) ? String(spec.method) : "GET";
      var logMsg = JSON.stringify("[Script] pm.sendRequest(\"" + m + " " + u + "\")");
      __pm_state.console_logs.push({
        level: "log",
        message: JSON.parse(logMsg),
        timestamp: Date.now() / 1000,
      });
      var out = JSON.stringify({ __ipc__: "sendRequest", spec: spec, callbackIndex: idx })
        + "\n";
      writeSync(1, enc.encode(out));
      var line = _readLineSyncDeno0();
      if (line == null) {
        return;
      }
      var resp;
      try { resp = JSON.parse(line); } catch (_e) { return; }
      if (typeof __pm_fulfill_send === "function") {
        __pm_fulfill_send(idx, resp);
      }
    }
  }
  var pending = __pm_state._pending_tests || [];
  if (pending.length > 0) {
    await Promise.allSettled(
      pending.map(function (p) { return p.promise; })
    );
  }
  await __printDone();

  function _readLineSyncDeno0() {
    const parts = [];
    const u8 = new Uint8Array(1);
    while (true) {
      var n;
      try {
        n = readSync(0, u8);
      } catch (_e) {
        return null;
      }
      if (n === 0) { return null; }
      if (u8[0] === 10) { break; } // \n
      if (u8[0] === 13) { continue; } // \r
      parts.push(String.fromCharCode(u8[0]));
    }
    return parts.join("");
  }

  async function __printDone() {
    var legacy = (typeof globalThis !== "undefined" && globalThis.tests) || {};
    var existing = {};
    for (var ti = 0; ti < __pm_state.test_results.length; ti++) {
      existing[__pm_state.test_results[ti].name] = true;
    }
    for (var k in legacy) {
      if (!Object.prototype.hasOwnProperty.call(legacy, k)) { continue; }
      if (existing[k]) { continue; }
      __pm_state.test_results.push({
        name: String(k),
        passed: !!legacy[k],
        error: null,
        duration_ms: 0,
      });
    }
    const o = {
      __done__: true,
      test_results: __pm_state.test_results,
      console_logs: __pm_state.console_logs,
      variable_changes: __pm_state.variable_changes,
      request_mutations: __pm_state.request_mutations,
      next_request: __pm_state.next_request,
      skip_request: __pm_state.skip_request,
    };
    if (__pm_state.global_variable_changes) {
      o.global_variable_changes = __pm_state.global_variable_changes;
    }
    writeSync(1, enc.encode(JSON.stringify(o) + "\n"));
  }
})();
