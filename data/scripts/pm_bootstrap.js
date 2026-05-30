// pm_bootstrap.js — Postmark JavaScript scripting API preamble.
//
// Injected before every user script.  Provides the full pm.* API,
// console mock, and Chai-like assertion chains.
//
// After injection, __pm_context is set by the host with request,
// response, variables, environment, collection vars, and info.
//
// After user script runs, host reads JSON.stringify(__pm_state).

"use strict";

// -- Internal state accumulator ----------------------------------------

var __pm_state = {
    test_results: [],
    console_logs: [],
    variable_changes: {},
    global_variable_changes: {},
    request_mutations: null,
    send_request_count: 0,
    next_request: undefined,
    skip_request: false,
    _send_queue: [],
    _pending_tests: [],
};

var __pm_callbacks = [];

// Preserve host-injected context (set before bootstrap is evaluated).
var __pm_context = __pm_context || {
    request: {},
    response: null,
    variables: {},
    environment_vars: {},
    collection_vars: {},
    global_vars: {},
    info: {},
    is_pre_request: true,
};

// -- Console mock (rate-limited to 200 messages) -----------------------
// Best-effort source_line: stack frames outside _PM_INTERNAL_FRAMES are mapped
// to 0-based editor lines via __pm_user_script_line0 (set in the Deno bundle).

var __CONSOLE_LIMIT = 200;

// Keep in sync with Python shims / debug wrapper names (see scripting roadmap A4).
var _PM_INTERNAL_FRAMES = [
    "pm_bootstrap.js",
    "__pm_debugUserScript",
    "__pm_runUserScript",
    "deno_drain.mjs",
    "pyodide_run.mjs",
];

function _parseConsoleSourceLine(stack) {
    if (!stack) return null;
    var base =
        typeof __pm_user_script_line0 === "number" ? __pm_user_script_line0 : 0;
    var lines = String(stack).split("\n");
    for (var i = 0; i < lines.length; i++) {
        var ln = lines[i];
        var m = ln.match(
            /(?:at\s+(?:[^\s]+\s+)?\(?)([^():]+):(\d+):(\d+)\)?\s*$/
        );
        if (!m) continue;
        var file = m[1];
        var lineNum = parseInt(m[2], 10);
        if (isNaN(lineNum)) continue;
        var internal = false;
        for (var j = 0; j < _PM_INTERNAL_FRAMES.length; j++) {
            if (file.indexOf(_PM_INTERNAL_FRAMES[j]) !== -1) {
                internal = true;
                break;
            }
        }
        if (internal) continue;
        var editorLine = lineNum - 1 - base;
        return editorLine >= 0 ? editorLine : null;
    }
    return null;
}

var console = {
    _emit: function (level, args) {
        if (__pm_state.console_logs.length >= __CONSOLE_LIMIT) return;
        var parts = [];
        for (var i = 0; i < args.length; i++) {
            try {
                parts.push(
                    typeof args[i] === "string"
                        ? args[i]
                        : JSON.stringify(args[i])
                );
            } catch (e) {
                parts.push(String(args[i]));
            }
        }
        var entry = {
            level: level,
            message: parts.join(" "),
            timestamp: Date.now() / 1000,
        };
        try {
            var sl = _parseConsoleSourceLine(new Error().stack);
            if (sl !== null) entry.source_line = sl;
        } catch (_e) {
            /* best-effort */
        }
        __pm_state.console_logs.push(entry);
    },
    log: function () {
        console._emit("log", arguments);
    },
    warn: function () {
        console._emit("warn", arguments);
    },
    error: function () {
        console._emit("error", arguments);
    },
    info: function () {
        console._emit("info", arguments);
    },
};

// -- Variable scope helper --------------------------------------------

function __makeVariableScope(initial, scopeName, changesKey) {
    var store = {};
    var targetChanges = changesKey || "variable_changes";
    var keys = Object.keys(initial || {});
    for (var i = 0; i < keys.length; i++) {
        store[keys[i]] = String(initial[keys[i]]);
    }

    return {
        get: function (key) {
            return store.hasOwnProperty(key) ? store[key] : undefined;
        },
        set: function (key, value) {
            var strVal = String(value);
            store[key] = strVal;
            __pm_state[targetChanges][key] = strVal;
        },
        has: function (key) {
            return store.hasOwnProperty(key);
        },
        unset: function (key) {
            delete store[key];
        },
        toObject: function () {
            var copy = {};
            var k = Object.keys(store);
            for (var i = 0; i < k.length; i++) copy[k[i]] = store[k[i]];
            return copy;
        },
        clear: function () {
            var k = Object.keys(store);
            for (var i = 0; i < k.length; i++) {
                delete store[k[i]];
                __pm_state[targetChanges][k[i]] = "";
            }
        },
        replaceIn: function (template) {
            return template.replace(/\{\{(.+?)\}\}/g, function (m, key) {
                key = String(key).trim();
                if (store.hasOwnProperty(key)) return store[key];
                if (key.charAt(0) === "$" && typeof __pm_resolveDynamic === "function") {
                    var dyn = __pm_resolveDynamic(key);
                    if (dyn !== null && dyn !== undefined) return dyn;
                }
                return m;
            });
        },
    };
}

// -- HeaderList helper ------------------------------------------------

function __makeHeaderList(headerArray, mutable) {
    var headers = [];
    if (headerArray) {
        for (var i = 0; i < headerArray.length; i++) {
            headers.push({
                key: headerArray[i].key || headerArray[i][0] || "",
                value: headerArray[i].value || headerArray[i][1] || "",
            });
        }
    }

    var obj = {
        get: function (name) {
            var lower = name.toLowerCase();
            for (var i = 0; i < headers.length; i++) {
                if (headers[i].key.toLowerCase() === lower)
                    return headers[i].value;
            }
            return undefined;
        },
        has: function (name) {
            return obj.get(name) !== undefined;
        },
        toObject: function () {
            var result = {};
            for (var i = 0; i < headers.length; i++) {
                result[headers[i].key] = headers[i].value;
            }
            return result;
        },
        each: function (fn) {
            for (var i = 0; i < headers.length; i++) {
                fn({ key: headers[i].key, value: headers[i].value });
            }
        },
        all: function () {
            var out = [];
            for (var i = 0; i < headers.length; i++) {
                out.push({ key: headers[i].key, value: headers[i].value });
            }
            return out;
        },
        find: function (name) {
            var lower = name.toLowerCase();
            for (var i = 0; i < headers.length; i++) {
                if (headers[i].key.toLowerCase() === lower) {
                    return { key: headers[i].key, value: headers[i].value };
                }
            }
            return undefined;
        },
        idx: function (n) {
            if (typeof n !== "number" || n < 0 || n >= headers.length) {
                return undefined;
            }
            return { key: headers[n].key, value: headers[n].value };
        },
    };

    if (mutable) {
        obj.add = function (header) {
            headers.push({
                key: header.key || "",
                value: header.value || "",
            });
        };
        obj.remove = function (name) {
            var lower = name.toLowerCase();
            for (var i = headers.length - 1; i >= 0; i--) {
                if (headers[i].key.toLowerCase() === lower)
                    headers.splice(i, 1);
            }
        };
        obj.upsert = function (header) {
            var lower = (header.key || "").toLowerCase();
            for (var i = 0; i < headers.length; i++) {
                if (headers[i].key.toLowerCase() === lower) {
                    headers[i].value = header.value || "";
                    return;
                }
            }
            headers.push({
                key: header.key || "",
                value: header.value || "",
            });
        };
        obj._toArray = function () {
            return headers;
        };
    }

    return obj;
}

// -- Chai-like Expectation class --------------------------------------

function __Expectation(value) {
    this._value = value;
    this._not = false;
}

// Chainable no-op getters for readability
var __chains = [
    "to",
    "be",
    "been",
    "is",
    "that",
    "which",
    "and",
    "has",
    "have",
    "with",
    "at",
    "of",
    "same",
    "but",
    "does",
    "deep",
];
for (var __ci = 0; __ci < __chains.length; __ci++) {
    (function (name) {
        Object.defineProperty(__Expectation.prototype, name, {
            get: function () {
                return this;
            },
        });
    })(__chains[__ci]);
}

// Negation
Object.defineProperty(__Expectation.prototype, "not", {
    get: function () {
        this._not = !this._not;
        return this;
    },
});

// Boolean/existence property assertions
var __propAssertions = {
    true: function (v) {
        return v === true;
    },
    false: function (v) {
        return v === false;
    },
    null: function (v) {
        return v === null;
    },
    undefined: function (v) {
        return v === undefined;
    },
    NaN: function (v) {
        return typeof v === "number" && isNaN(v);
    },
    exist: function (v) {
        return v !== null && v !== undefined;
    },
    empty: function (v) {
        if (typeof v === "string" || Array.isArray(v)) return v.length === 0;
        if (v && typeof v === "object") return Object.keys(v).length === 0;
        return false;
    },
};

var __propKeys = Object.keys(__propAssertions);
for (var __pi = 0; __pi < __propKeys.length; __pi++) {
    (function (name, fn) {
        Object.defineProperty(__Expectation.prototype, name, {
            get: function () {
                var result = fn(this._value);
                if (this._not) result = !result;
                if (!result) {
                    throw new Error(
                        "expected " +
                            JSON.stringify(this._value) +
                            (this._not ? " not " : " ") +
                            "to be " +
                            name
                    );
                }
                return this;
            },
        });
    })(__propKeys[__pi], __propAssertions[__propKeys[__pi]]);
}

__Expectation.prototype._assert = function (result, msg) {
    if (this._not) result = !result;
    if (!result) throw new Error(msg);
    return this;
};

// Method assertions
__Expectation.prototype.equal = function (expected) {
    return this._assert(
        this._value === expected,
        "expected " +
            JSON.stringify(this._value) +
            (this._not ? " not " : " ") +
            "to equal " +
            JSON.stringify(expected)
    );
};
__Expectation.prototype.equals = __Expectation.prototype.equal;
__Expectation.prototype.eq = __Expectation.prototype.equal;

__Expectation.prototype.eql = function (expected) {
    var pass = JSON.stringify(this._value) === JSON.stringify(expected);
    return this._assert(
        pass,
        "expected " +
            JSON.stringify(this._value) +
            (this._not ? " not " : " ") +
            "to deeply equal " +
            JSON.stringify(expected)
    );
};

__Expectation.prototype.a = function (type) {
    var actual;
    if (Array.isArray(this._value)) actual = "array";
    else actual = typeof this._value;
    return this._assert(
        actual === type,
        "expected " +
            JSON.stringify(this._value) +
            (this._not ? " not " : " ") +
            "to be a " +
            type
    );
};
__Expectation.prototype.an = __Expectation.prototype.a;

__Expectation.prototype.include = function (val) {
    var pass = false;
    if (typeof this._value === "string") pass = this._value.indexOf(val) !== -1;
    else if (Array.isArray(this._value)) pass = this._value.indexOf(val) !== -1;
    else if (this._value && typeof this._value === "object")
        pass = val in this._value;
    return this._assert(
        pass,
        "expected " +
            JSON.stringify(this._value) +
            (this._not ? " not " : " ") +
            "to include " +
            JSON.stringify(val)
    );
};
__Expectation.prototype.includes = __Expectation.prototype.include;
__Expectation.prototype.contain = __Expectation.prototype.include;
__Expectation.prototype.contains = __Expectation.prototype.include;

__Expectation.prototype.property = function (name, val) {
    var has = this._value != null && this._value.hasOwnProperty(name);
    if (arguments.length === 2) {
        has = has && this._value[name] === val;
    }
    return this._assert(
        has,
        "expected " +
            JSON.stringify(this._value) +
            (this._not ? " not " : " ") +
            "to have property " +
            JSON.stringify(name) +
            (arguments.length === 2
                ? " with value " + JSON.stringify(val)
                : "")
    );
};

__Expectation.prototype.lengthOf = function (n) {
    var len = this._value && this._value.length;
    return this._assert(
        len === n,
        "expected length " + len + (this._not ? " not " : " ") + "to be " + n
    );
};
__Expectation.prototype.length = __Expectation.prototype.lengthOf;

__Expectation.prototype.above = function (n) {
    return this._assert(
        this._value > n,
        "expected " +
            this._value +
            (this._not ? " not " : " ") +
            "to be above " +
            n
    );
};
__Expectation.prototype.greaterThan = __Expectation.prototype.above;
__Expectation.prototype.gt = __Expectation.prototype.above;

__Expectation.prototype.below = function (n) {
    return this._assert(
        this._value < n,
        "expected " +
            this._value +
            (this._not ? " not " : " ") +
            "to be below " +
            n
    );
};
__Expectation.prototype.lessThan = __Expectation.prototype.below;
__Expectation.prototype.lt = __Expectation.prototype.below;

__Expectation.prototype.least = function (n) {
    return this._assert(
        this._value >= n,
        "expected " +
            this._value +
            (this._not ? " not " : " ") +
            "to be at least " +
            n
    );
};
__Expectation.prototype.gte = __Expectation.prototype.least;

__Expectation.prototype.most = function (n) {
    return this._assert(
        this._value <= n,
        "expected " +
            this._value +
            (this._not ? " not " : " ") +
            "to be at most " +
            n
    );
};
__Expectation.prototype.lte = __Expectation.prototype.most;

__Expectation.prototype.match = function (re) {
    return this._assert(
        re.test(this._value),
        "expected " +
            JSON.stringify(this._value) +
            (this._not ? " not " : " ") +
            "to match " +
            re
    );
};
__Expectation.prototype.matches = __Expectation.prototype.match;

// HTTP status code to canonical reason phrase (used by ``.status("Created")``;
// referenced from ``data/snippets/javascript.json`` test snippets).
var __HTTP_REASON = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non-Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Payload Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
};

// HTTP-specific assertions
__Expectation.prototype.status = function (code) {
    var actual = this._value;
    if (actual && typeof actual === "object" && "code" in actual)
        actual = actual.code;
    if (typeof code === "string") {
        var reason = __HTTP_REASON[actual] || "";
        return this._assert(
            reason.toLowerCase() === code.toLowerCase(),
            "expected status " +
                actual +
                " (" +
                reason +
                ")" +
                (this._not ? " not " : " ") +
                "to be " +
                JSON.stringify(code)
        );
    }
    return this._assert(
        actual === code,
        "expected status " +
            actual +
            (this._not ? " not " : " ") +
            "to be " +
            code
    );
};

__Expectation.prototype.header = function (name, value) {
    var resp = this._value;
    if (resp && typeof resp === "object" && resp.headers) {
        var headerVal = resp.headers.get
            ? resp.headers.get(name)
            : resp.headers[name];
        if (arguments.length === 2) {
            return this._assert(
                headerVal === value,
                "expected header " +
                    name +
                    " to be " +
                    JSON.stringify(value) +
                    " but got " +
                    JSON.stringify(headerVal)
            );
        }
        return this._assert(
            headerVal !== undefined,
            "expected response to have header " + JSON.stringify(name)
        );
    }
    return this._assert(false, "expected a response object with headers");
};

__Expectation.prototype.body = function (expected) {
    var resp = this._value;
    var actual = "";
    if (resp && typeof resp === "object") {
        if (typeof resp.text === "function") {
            actual = resp.text();
        } else if (typeof resp.body === "string") {
            actual = resp.body;
        }
    } else if (typeof resp === "string") {
        actual = resp;
    }
    var preview =
        actual.length > 80 ? actual.slice(0, 77) + "..." : actual;
    if (expected instanceof RegExp) {
        return this._assert(
            expected.test(actual),
            "expected body to match " +
                String(expected) +
                " but got " +
                JSON.stringify(preview)
        );
    }
    return this._assert(
        actual === expected,
        "expected body to equal " +
            JSON.stringify(expected) +
            " but got " +
            JSON.stringify(preview)
    );
};

// Strict ``===`` membership (not deep-equal Chai semantics).
__Expectation.prototype.oneOf = function (allowed) {
    var actual = this._value;
    if (!Array.isArray(allowed)) {
        return this._assert(false, "oneOf expects an array argument");
    }
    var ok = false;
    for (var i = 0; i < allowed.length; i++) {
        if (allowed[i] === actual) {
            ok = true;
            break;
        }
    }
    return this._assert(
        ok,
        "expected " +
            JSON.stringify(actual) +
            (this._not ? " not " : " ") +
            "to be one of " +
            JSON.stringify(allowed)
    );
};

__Expectation.prototype.jsonBody = function (path, value) {
    var resp = this._value;
    var body = resp;
    if (resp && typeof resp === "object" && "body" in resp) {
        body =
            typeof resp.body === "string" ? JSON.parse(resp.body) : resp.body;
    }
    // Lodash-style path: ``a.b[0].c`` → ["a", "b", 0, "c"].
    var tokens = [];
    var chunks = path.split(".");
    for (var ci = 0; ci < chunks.length; ci++) {
        var bracketParts = chunks[ci].split(/[\[\]]+/);
        for (var bi = 0; bi < bracketParts.length; bi++) {
            var tok = bracketParts[bi];
            if (tok === "") continue;
            if (/^-?\d+$/.test(tok)) tokens.push(parseInt(tok, 10));
            else tokens.push(tok);
        }
    }
    var cur = body;
    for (var i = 0; i < tokens.length; i++) {
        if (cur == null) { cur = undefined; break; }
        cur = cur[tokens[i]];
    }
    if (arguments.length === 2) {
        return this._assert(
            JSON.stringify(cur) === JSON.stringify(value),
            "expected " +
                path +
                " to be " +
                JSON.stringify(value) +
                " but got " +
                JSON.stringify(cur)
        );
    }
    return this._assert(
        cur !== undefined,
        "expected body to have path " + JSON.stringify(path)
    );
};

function __pm_jsonSchemaTarget(value) {
    var resp = value;
    if (resp && typeof resp === "object" && ("body" in resp || typeof resp.json === "function")) {
        try {
            if (typeof resp.json === "function") return resp.json();
            var raw = typeof resp.body === "string" ? resp.body : "";
            return raw ? JSON.parse(raw) : {};
        } catch (_e) {
            return null;
        }
    }
    return value;
}

__Expectation.prototype.jsonSchema = function (schema) {
    var data = __pm_jsonSchemaTarget(this._value);
    var r = __pm_validateSchema(data, schema);
    return this._assert(
        r.ok,
        "expected value to match schema: " + r.errors.join(", ")
    );
};

// -- Inline sendRequest IPC + response wrapper -----------------------
//
// ``writeSync`` / ``readSync`` are imported at the top of the bundled
// Deno script (see ``deno_runtime._NODE_FS_IMPORT``). They give
// ``pm.sendRequest`` a synchronous IPC channel to the host: the spec
// is written to stdout as a JSON line, the host fetches the URL, and
// writes the response back as a JSON line on stdin. With this in
// place, ``await pm.sendRequest(...)`` matches Postman's modern API.
//
// The drain pass (``deno_drain.mjs``) is now mostly a no-op for
// ``sendRequest`` — kept only as a safety net for legacy code that
// still pushes to ``__pm_state._send_queue`` manually.

function __pm_inline_ipc_send(spec) {
    if (typeof writeSync !== "function" || typeof readSync !== "function") {
        return {
            error: "pm.sendRequest unavailable: no IPC channel",
            body: "",
        };
    }
    var enc = new TextEncoder();
    var line =
        JSON.stringify({
            __ipc__: "sendRequest",
            spec: spec,
            callbackIndex: 0,
        }) + "\n";
    try {
        writeSync(1, enc.encode(line));
    } catch (_e) {
        return { error: "pm.sendRequest write failed", body: "" };
    }
    var parts = [];
    var u8 = new Uint8Array(1);
    while (true) {
        var n;
        try {
            n = readSync(0, u8);
        } catch (_e) {
            return { error: "pm.sendRequest read failed", body: "" };
        }
        if (n === 0 || n == null) {
            return { error: "pm.sendRequest read closed", body: "" };
        }
        if (u8[0] === 10) break; // \n
        if (u8[0] === 13) continue; // \r
        parts.push(String.fromCharCode(u8[0]));
    }
    var raw = parts.join("");
    try {
        return JSON.parse(raw);
    } catch (_e) {
        return { error: "pm.sendRequest bad json", body: "" };
    }
}

// -- URL factory (Postman ``pm.request.url`` shape) -------------------

function __pm_makeUrl(rawUrl) {
    var s = String(rawUrl || "");
    var parsed = null;
    try {
        parsed = new URL(s);
    } catch (_e) {
        parsed = null;
    }
    var queryItems = [];
    if (parsed && parsed.searchParams) {
        parsed.searchParams.forEach(function (v, k) {
            queryItems.push({ key: k, value: v });
        });
    }
    var query = __makeHeaderList(queryItems, true);
    return {
        toString: function () {
            return parsed ? parsed.toString() : s;
        },
        getHost: function () {
            return parsed ? parsed.host : "";
        },
        getPath: function () {
            return parsed ? parsed.pathname : "";
        },
        getQueryString: function () {
            return parsed ? parsed.search.replace(/^\?/, "") : "";
        },
        protocol: parsed ? parsed.protocol.replace(/:$/, "") : "",
        host: parsed ? parsed.hostname : "",
        port: parsed ? parsed.port : "",
        path: parsed ? parsed.pathname : "",
        query: query,
        _isPostmarkUrl: true,
    };
}

// -- Cookie helpers (``pm.cookies`` / ``pm.response.cookies``) --------

function __pm_parseCookieHeaders(headerArray) {
    var cookies = {};
    if (!headerArray) {
        return cookies;
    }
    for (var i = 0; i < headerArray.length; i++) {
        if ((headerArray[i].key || "").toLowerCase() === "set-cookie") {
            var raw = headerArray[i].value || "";
            var eqIdx = raw.indexOf("=");
            if (eqIdx > 0) {
                var cName = raw.substring(0, eqIdx).trim();
                var rest = raw.substring(eqIdx + 1);
                var semiIdx = rest.indexOf(";");
                var cVal =
                    semiIdx >= 0
                        ? rest.substring(0, semiIdx).trim()
                        : rest.trim();
                cookies[cName] = cVal;
            }
        }
    }
    return cookies;
}

function __pm_makeCookiesApi(cookies) {
    return {
        get: function (name) {
            return cookies.hasOwnProperty(name) ? cookies[name] : undefined;
        },
        getAll: function () {
            var result = [];
            var keys = Object.keys(cookies);
            for (var i = 0; i < keys.length; i++) {
                result.push({
                    name: keys[i],
                    value: cookies[keys[i]],
                });
            }
            return result;
        },
        has: function (name) {
            return cookies.hasOwnProperty(name);
        },
    };
}

function __pm_wrap_response(raw) {
    if (!raw || typeof raw !== "object") {
        return null;
    }
    var obj = {
        code: raw.status_code || raw.code || 0,
        status: raw.status || "",
        headers: __makeHeaderList(raw.headers, false),
        responseTime: raw.response_time || raw.responseTime || 0,
        responseSize: raw.response_size || raw.responseSize || 0,
        body: typeof raw.body === "string" ? raw.body : raw.body || "",
        error: raw.error || null,
    };
    obj.json = function () {
        var s = typeof obj.body === "string" ? obj.body : "";
        if (s.length === 0) {
            throw new Error(
                "response.json(): response body is empty"
            );
        }
        try {
            return JSON.parse(s);
        } catch (e) {
            throw new Error(
                "response.json(): body is not valid JSON (" +
                    (e && e.message ? e.message : "parse error") +
                    ")"
            );
        }
    };
    obj.text = function () {
        return typeof obj.body === "string" ? obj.body : String(obj.body);
    };
    obj.reason = function () {
        return __HTTP_REASON[obj.code] || "";
    };
    obj.mime = function () {
        var ct =
            obj.headers && obj.headers.get
                ? obj.headers.get("Content-Type") || ""
                : "";
        var sep = ct.indexOf(";");
        return {
            type: sep >= 0 ? ct.slice(0, sep).trim() : ct.trim(),
            charset: (function () {
                var m = /charset=([^;]+)/i.exec(ct);
                return m ? m[1].trim() : "";
            })(),
        };
    };
    obj.dataURI = function () {
        var ct =
            obj.headers && obj.headers.get
                ? obj.headers.get("Content-Type") || "application/octet-stream"
                : "application/octet-stream";
        var raw = typeof obj.body === "string" ? obj.body : "";
        return (
            "data:" +
            ct +
            ";base64," +
            (typeof btoa !== "undefined"
                ? btoa(unescape(encodeURIComponent(raw)))
                : "")
        );
    };
    obj.size = function () {
        return (
            obj.responseSize ||
            (typeof obj.body === "string" ? obj.body.length : 0)
        );
    };
    Object.defineProperty(obj, "to", {
        get: function () {
            return new __Expectation(obj);
        },
    });
    return obj;
}

// -- pm object --------------------------------------------------------

var __pm_info_raw = __pm_context.info || {};
var pm = {
    info: {
        eventName: __pm_info_raw.eventName || "",
        requestName: __pm_info_raw.requestName || "",
        requestId: __pm_info_raw.requestId || "",
        iteration: __pm_info_raw.iteration != null ? __pm_info_raw.iteration : 0,
        iterationCount:
            __pm_info_raw.iterationCount != null
                ? __pm_info_raw.iterationCount
                : 0,
        testFilter: __pm_info_raw.testFilter || null,
    },

    request: (function () {
        var req = __pm_context.request || {};
        var bodyVal = req.body;
        var bodyObj;
        if (!bodyVal || typeof bodyVal === "string") {
            var rawStr = typeof bodyVal === "string" ? bodyVal : "";
            bodyObj = {
                mode: rawStr ? "raw" : "",
                raw: rawStr,
                urlencoded: __makeHeaderList([], true),
                formdata: __makeHeaderList([], true),
                graphql: null,
                file: null,
                toString: function () {
                    return this.raw || "";
                },
            };
        } else if (typeof bodyVal === "object") {
            var mode = bodyVal.mode || "raw";
            bodyObj = {
                mode: mode,
                raw: bodyVal.raw || "",
                urlencoded: __makeHeaderList(bodyVal.urlencoded || [], true),
                formdata: __makeHeaderList(bodyVal.formdata || [], true),
                graphql: bodyVal.graphql || null,
                file: bodyVal.file || null,
                toString: function () {
                    return typeof this.raw === "string" ? this.raw : "";
                },
            };
        } else {
            bodyObj = {
                mode: "",
                raw: "",
                urlencoded: __makeHeaderList([], true),
                formdata: __makeHeaderList([], true),
                graphql: null,
                file: null,
                toString: function () {
                    return "";
                },
            };
        }
        return {
            url: __pm_makeUrl(req.url || ""),
            method: req.method || "GET",
            headers: __makeHeaderList(req.headers, __pm_context.is_pre_request),
            body: bodyObj,
            auth: req.auth != null ? req.auth : null,
        };
    })(),

    response: (function () {
        var res = __pm_context.response;
        if (!res) return null;
        var obj = __pm_wrap_response(res);
        obj.cookies = __pm_makeCookiesApi(__pm_parseCookieHeaders(res.headers || []));
        var ori = __pm_context.original_request;
        if (ori) {
            var ob =
                typeof ori.body === "object" &&
                ori.body !== null &&
                typeof ori.body.toString === "function"
                    ? ori.body.toString()
                    : String(ori.body || "");
            obj.originalRequest = {
                url: __pm_makeUrl(ori.url || ""),
                method: String(ori.method || "GET"),
                headers: __makeHeaderList(ori.headers, false),
                body: ob,
            };
        } else {
            obj.originalRequest = null;
        }
        return obj;
    })(),

    environment: (function () {
        var scope = __makeVariableScope(
            __pm_context.environment_vars,
            "environment"
        );
        scope.name = __pm_context.environment_name || "";
        return scope;
    })(),
    collectionVariables: __makeVariableScope(
        __pm_context.collection_vars,
        "collectionVariables"
    ),
    globals: __makeVariableScope(__pm_context.global_vars, "globals", "global_variable_changes"),

    test: (function () {
        var fnTest = function (name, fn) {
            var filter =
                (typeof __pm_context !== "undefined" &&
                    __pm_context.info &&
                    __pm_context.info.testFilter) ||
                globalThis.__pm_test_filter ||
                null;
            if (filter && String(name) !== String(filter)) {
                return;
            }
            var start = Date.now();
            var result = {
                name: name,
                passed: true,
                error: null,
                duration_ms: 0,
                skipped: false,
            };
            var didSkip = false;
            var skipFn = function () {
                didSkip = true;
            };
            try {
                if (typeof fn !== "function") {
                    throw new Error("pm.test callback must be a function");
                }
                var ret = fn.call({ skip: skipFn }, skipFn);
                if (
                    ret &&
                    typeof ret === "object" &&
                    typeof ret.then === "function"
                ) {
                    result.duration_ms = Date.now() - start;
                    if (didSkip) {
                        result.passed = true;
                        result.skipped = true;
                    }
                    var srcAsync = globalThis.__pm_test_source_name;
                    if (srcAsync) {
                        result.source_name = String(srcAsync);
                    }
                    __pm_state.test_results.push(result);
                    var pending = { result: result, promise: ret };
                    ret.then(
                        function () {
                            pending.result.duration_ms = Date.now() - start;
                        },
                        function (e) {
                            pending.result.passed = false;
                            pending.result.error = e.message || String(e);
                            pending.result.duration_ms = Date.now() - start;
                        }
                    );
                    __pm_state._pending_tests.push(pending);
                    return;
                }
            } catch (e) {
                result.passed = false;
                result.error = e.message || String(e);
            }
            result.duration_ms = Date.now() - start;
            if (didSkip) {
                result.passed = true;
                result.skipped = true;
            }
            var src = globalThis.__pm_test_source_name;
            if (src) {
                result.source_name = String(src);
            }
            __pm_state.test_results.push(result);
        };
        fnTest.skip = function (name, _fn) {
            __pm_state.test_results.push({
                name: String(name),
                passed: true,
                skipped: true,
                duration_ms: 0,
                error: null,
            });
        };
        return fnTest;
    })(),

    expect: function (value) {
        return new __Expectation(value);
    },

    require: function (specifier) {
        if (typeof specifier !== "string" || specifier.length === 0) {
            throw new Error("pm.require: specifier must be a non-empty string");
        }
        if (specifier === "cheerio") {
            throw new Error(
                "Module 'cheerio' is not available in the Postmark sandbox; use pm.require('npm:cheerio')"
            );
        }
        if (
            typeof __pm_builtins !== "undefined" &&
            Object.prototype.hasOwnProperty.call(__pm_builtins, specifier)
        ) {
            var builtin = __pm_builtins[specifier];
            if (builtin === undefined) {
                throw new Error(
                    "pm.require: built-in '" + specifier + "' is not bundled"
                );
            }
            return builtin;
        }
        if (specifier.indexOf("local:") === 0) {
            var localRegistry = globalThis.__pm_require_modules || {};
            if (Object.prototype.hasOwnProperty.call(localRegistry, specifier)) {
                return localRegistry[specifier];
            }
            throw new Error(
                "pm.require: local script '" +
                    specifier.slice(6) +
                    "' was not bundled. Use a string literal and check the path in " +
                    "Local scripts (path-safe names, case-sensitive)."
            );
        }
        if (specifier.indexOf("npm:") !== 0 && specifier.indexOf("jsr:") !== 0) {
            throw new Error(
                "pm.require: unknown package '" +
                    specifier +
                    "' (use a built-in name, local:, npm:, or jsr:)"
            );
        }
        var registry = globalThis.__pm_require_modules || {};
        if (Object.prototype.hasOwnProperty.call(registry, specifier)) {
            return registry[specifier];
        }
        var at = specifier.lastIndexOf("@");
        var slash = specifier.lastIndexOf("/");
        if (at > 4 && at > slash) {
            var bare = specifier.slice(0, at);
            if (Object.prototype.hasOwnProperty.call(registry, bare)) {
                return registry[bare];
            }
        }
        throw new Error(
            "pm.require: package '" +
                specifier +
                "' was not bundled. " +
                "Make sure the call uses a string literal so the host can detect it."
        );
    },

    visualizer: {
        set: function (_template, _data, _options) {
            throw new Error(
                "pm.visualizer.set is not supported in postmark — see data/snippets/README.md"
            );
        },
    },

    sendRequest: function (spec, callback) {
        // Postman-API parity: synchronous-IPC fetch during user script
        // execution. Returns a resolved Promise so ``await`` works; also
        // fires the optional callback for the legacy form. Without the
        // inline IPC, ``await`` would never resolve because the queue
        // drain runs after the user script body has already finished.
        if (__pm_state.send_request_count >= 10) {
            throw new Error("pm.sendRequest rate limit exceeded (max 10)");
        }
        __pm_state.send_request_count++;
        var reqSpec =
            typeof spec === "string" ? { url: spec, method: "GET" } : spec;
        __pm_state.console_logs.push({
            level: "log",
            message:
                '[Script] pm.sendRequest("' +
                (reqSpec.method || "GET") +
                " " +
                (reqSpec.url && reqSpec.url.toString
                    ? reqSpec.url.toString()
                    : String(reqSpec.url || "")) +
                '")',
            timestamp: Date.now() / 1000,
        });
        var raw = __pm_inline_ipc_send(reqSpec);
        var wrapped = __pm_wrap_response(raw);
        if (typeof callback === "function") {
            try {
                callback(raw && raw.error ? raw.error : null, wrapped);
            } catch (e) {
                __pm_state.console_logs.push({
                    level: "error",
                    message:
                        "[Script] sendRequest callback error: " +
                        (e && e.message ? e.message : String(e)),
                    timestamp: Date.now() / 1000,
                });
            }
        }
        return Promise.resolve(wrapped);
    },

    cookies: (function () {
        var hdrs = __pm_context.response ? __pm_context.response.headers || [] : [];
        var api = __pm_makeCookiesApi(__pm_parseCookieHeaders(hdrs));
        api.jar = function () {
            return {
                getAll: function (_url) {
                    return [];
                },
                set: function () {
                    throw new Error(
                        "pm.cookies.jar mutation is not yet supported in postmark"
                    );
                },
                unset: function () {
                    throw new Error(
                        "pm.cookies.jar mutation is not yet supported in postmark"
                    );
                },
                clear: function () {
                    throw new Error(
                        "pm.cookies.jar mutation is not yet supported in postmark"
                    );
                },
            };
        };
        return api;
    })(),

    execution: (function () {
        var loc = __pm_context.execution_location || { current: "" };
        return {
            setNextRequest: function (name) {
                __pm_state.next_request =
                    name === null || name === undefined ? null : String(name);
            },
            skipRequest: function () {
                __pm_state.skip_request = true;
            },
            location: loc,
        };
    })(),

    iterationData: (function () {
        var data = __pm_context.iteration_data || {};
        return {
            get: function (key) {
                return data.hasOwnProperty(key) ? data[key] : undefined;
            },
            toObject: function () {
                var copy = {};
                var keys = Object.keys(data);
                for (var i = 0; i < keys.length; i++) {
                    copy[keys[i]] = data[keys[i]];
                }
                return copy;
            },
            has: function (key) {
                return data.hasOwnProperty(key);
            },
        };
    })(),

    variables: (function () {
        var local = {};
        return {
            get: function (k) {
                if (Object.prototype.hasOwnProperty.call(local, k)) {
                    return local[k];
                }
                var it = __pm_context.iteration_data || {};
                if (Object.prototype.hasOwnProperty.call(it, k)) {
                    return it[k];
                }
                var env = __pm_context.environment_vars || {};
                if (Object.prototype.hasOwnProperty.call(env, k)) {
                    return env[k];
                }
                var coll = __pm_context.collection_vars || {};
                if (Object.prototype.hasOwnProperty.call(coll, k)) {
                    return coll[k];
                }
                var glob = __pm_context.global_vars || {};
                if (Object.prototype.hasOwnProperty.call(glob, k)) {
                    return glob[k];
                }
                return undefined;
            },
            set: function (k, v) {
                var strVal = String(v);
                local[k] = strVal;
                __pm_state.variable_changes[k] = strVal;
            },
            unset: function (k) {
                delete local[k];
            },
            has: function (k) {
                return this.get(k) !== undefined;
            },
            toObject: function () {
                var out = {};
                var glob = __pm_context.global_vars || {};
                Object.keys(glob).forEach(function (key) {
                    out[key] = glob[key];
                });
                var coll = __pm_context.collection_vars || {};
                Object.keys(coll).forEach(function (key) {
                    out[key] = coll[key];
                });
                var env = __pm_context.environment_vars || {};
                Object.keys(env).forEach(function (key) {
                    out[key] = env[key];
                });
                var it = __pm_context.iteration_data || {};
                Object.keys(it).forEach(function (key) {
                    out[key] = it[key];
                });
                Object.keys(local).forEach(function (key) {
                    out[key] = local[key];
                });
                return out;
            },
            replaceIn: function (template) {
                var self = this;
                return template.replace(/\{\{(.+?)\}\}/g, function (m, key) {
                    key = String(key).trim();
                    var v = self.get(key);
                    if (v !== undefined) return v;
                    if (key.charAt(0) === "$" && typeof __pm_resolveDynamic === "function") {
                        var dyn = __pm_resolveDynamic(key);
                        if (dyn !== null && dyn !== undefined) return dyn;
                    }
                    return m;
                });
            },
            clear: function () {
                Object.keys(local).forEach(function (key) {
                    delete local[key];
                });
            },
        };
    })(),
};

function __pm_fulfill_send(index, resp) {
    var cb = __pm_callbacks[index];
    if (cb) {
        try {
            cb(resp.error || null, resp);
        } catch (e) {
            __pm_state.console_logs.push({
                level: "error",
                message:
                    "[Script] sendRequest callback error: " +
                    (e.message || String(e)),
                timestamp: Date.now() / 1000,
            });
        }
    }
}

// -- Legacy Postman compatibility shim ---------------------------------

var postman = {
    setEnvironmentVariable: function (key, value) {
        pm.environment.set(key, String(value));
    },
    getEnvironmentVariable: function (key) {
        return pm.environment.get(key);
    },
    clearEnvironmentVariable: function (key) {
        pm.environment.unset(key);
    },
    setGlobalVariable: function (key, value) {
        pm.globals.set(key, String(value));
    },
    getGlobalVariable: function (key) {
        return pm.globals.get(key);
    },
    clearGlobalVariable: function (key) {
        pm.globals.unset(key);
    },
    setNextRequest: function (name) {
        __pm_state.next_request = name == null ? null : String(name);
    },
};

// -- Postman require() shim -------------------------------------------
// Supports the most-used sandbox built-in libraries.

var __pm_builtins = {
    "crypto-js": typeof CryptoJS !== "undefined" ? CryptoJS : undefined,
    lodash: typeof __pm_lodash !== "undefined" ? __pm_lodash : undefined,
    moment: typeof __pm_moment !== "undefined" ? __pm_moment : undefined,
    chai: typeof __pm_chai !== "undefined" ? __pm_chai : undefined,
    tv4: typeof __pm_tv4 !== "undefined" ? __pm_tv4 : undefined,
    ajv:
        typeof __pm_ajv !== "undefined"
            ? __pm_ajv.default || __pm_ajv
            : undefined,
    xml2js: typeof __pm_xml2js !== "undefined" ? __pm_xml2js : undefined,
    "csv-parse/sync":
        typeof __pm_csv_parse !== "undefined" ? __pm_csv_parse : undefined,
    "csv-parse/lib/sync":
        typeof __pm_csv_parse !== "undefined" ? __pm_csv_parse : undefined,
    atob: typeof atob !== "undefined" ? atob : undefined,
    btoa: typeof btoa !== "undefined" ? btoa : undefined,
    uuid: (function () {
        // Minimal UUIDv4 implementation.
        function v4() {
            var bytes = new Uint8Array(16);
            globalThis.crypto.getRandomValues(bytes);
            bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
            bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 1
            var hex = [];
            for (var i = 0; i < 16; i++) {
                hex.push(("0" + bytes[i].toString(16)).slice(-2));
            }
            return (
                hex.slice(0, 4).join("") +
                "-" +
                hex.slice(4, 6).join("") +
                "-" +
                hex.slice(6, 8).join("") +
                "-" +
                hex.slice(8, 10).join("") +
                "-" +
                hex.slice(10, 16).join("")
            );
        }
        return { v4: v4 };
    })(),
};

function require(name) {
    if (name in __pm_builtins) {
        var mod = __pm_builtins[name];
        if (mod === undefined) {
            throw new Error("Module '" + name + "' failed to load");
        }
        return mod;
    }
    throw new Error(
        "Module '" + name + "' is not available in the Postmark sandbox"
    );
}

// -- Freeze read-only objects -----------------------------------------

Object.freeze(pm.info);
Object.freeze(pm.cookies);
Object.freeze(pm.execution);
Object.freeze(pm.iterationData);

if (!__pm_context.is_pre_request) {
    // In test context, request and response are read-only
    if (pm.response) Object.freeze(pm.response);
    Object.freeze(pm.request);
} else {
    // In pre-request context, track request mutations
    __pm_state.request_mutations = {
        url:
            typeof pm.request.url === "string"
                ? pm.request.url
                : pm.request.url && pm.request.url.toString
                    ? pm.request.url.toString()
                    : "",
        method: pm.request.method,
        headers: pm.request.headers._toArray
            ? pm.request.headers._toArray()
            : [],
        body:
            typeof pm.request.body === "string"
                ? pm.request.body
                : pm.request.body && pm.request.body.toString
                    ? pm.request.body.toString()
                    : "",
    };
}

// ``Debugger.evaluateOnCallFrame`` evaluates in the paused user frame; module
// top-level ``var`` bindings are not in that lexical environment.  Mirror the
// live objects onto ``globalThis`` so debug variable reads see ``variable_changes``.
if (typeof globalThis !== "undefined") {
    globalThis.__pm_state = __pm_state;
    globalThis.pm = pm;
    globalThis.postman = postman;
    globalThis.responseBody = pm.response ? pm.response.text() : undefined;
    globalThis.responseCode = pm.response
        ? { code: pm.response.code, name: pm.response.reason() }
        : undefined;
    globalThis.responseHeaders = pm.response ? pm.response.headers.toObject() : {};
    globalThis.responseTime = pm.response
        ? pm.response.responseTime
        : undefined;
    globalThis.tests = {};
    globalThis.xml2Json = function (xml) {
        var x = __pm_builtins.xml2js;
        if (!x || typeof x.parseString !== "function") {
            return null;
        }
        var out = null;
        x.parseString(String(xml), function (err, r) {
            if (!err) {
                out = r;
            }
        });
        return out;
    };
}
