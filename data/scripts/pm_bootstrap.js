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

var __CONSOLE_LIMIT = 200;

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
        __pm_state.console_logs.push({
            level: level,
            message: parts.join(" "),
            timestamp: Date.now() / 1000,
        });
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
        replaceIn: function (template) {
            return template.replace(/\{\{(.+?)\}\}/g, function (m, key) {
                return store.hasOwnProperty(key) ? store[key] : m;
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

// HTTP-specific assertions
__Expectation.prototype.status = function (code) {
    var actual = this._value;
    if (actual && typeof actual === "object" && "code" in actual)
        actual = actual.code;
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

__Expectation.prototype.jsonBody = function (path, value) {
    var resp = this._value;
    var body = resp;
    if (resp && typeof resp === "object" && "body" in resp) {
        body =
            typeof resp.body === "string" ? JSON.parse(resp.body) : resp.body;
    }
    var parts = path.split(".");
    var cur = body;
    for (var i = 0; i < parts.length; i++) {
        if (cur == null) {
            cur = undefined;
            break;
        }
        cur = cur[parts[i]];
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

// -- pm object --------------------------------------------------------

var pm = {
    info: __pm_context.info || {},

    request: (function () {
        var req = __pm_context.request || {};
        var obj = {
            url: req.url || "",
            method: req.method || "GET",
            headers: __makeHeaderList(req.headers, __pm_context.is_pre_request),
            body: req.body || "",
        };
        return obj;
    })(),

    response: (function () {
        var res = __pm_context.response;
        if (!res) return null;
        var obj = {
            code: res.status_code || res.code || 0,
            status: res.status || "",
            headers: __makeHeaderList(res.headers, false),
            responseTime: res.response_time || res.responseTime || 0,
            responseSize: res.response_size || res.responseSize || 0,
            body: res.body || "",
            json: function () {
                var s = typeof obj.body === "string" ? obj.body : "";
                if (s.length === 0) {
                    throw new Error(
                        "pm.response.json(): response body is empty. " +
                        "Set a JSON body in the Mock response section (Status / body) below the script editor, " +
                        "or guard the call with `if (pm.response.text())` before parsing."
                    );
                }
                try {
                    return JSON.parse(s);
                } catch (e) {
                    throw new Error(
                        "pm.response.json(): body is not valid JSON (" + (e && e.message ? e.message : "parse error") + "). " +
                        "Check the Mock response body below the script editor."
                    );
                }
            },
            text: function () {
                return typeof obj.body === "string" ? obj.body : String(obj.body);
            },
        };

        // Postman-style: pm.response.to.have.status(N), .to.have.header, .to.have.jsonBody
        // Fresh __Expectation per access so .not does not leak across chains.
        Object.defineProperty(obj, "to", {
            get: function () {
                return new __Expectation(obj);
            },
        });

        return obj;
    })(),

    variables: __makeVariableScope(__pm_context.variables, "variables"),
    environment: __makeVariableScope(
        __pm_context.environment_vars,
        "environment"
    ),
    collectionVariables: __makeVariableScope(
        __pm_context.collection_vars,
        "collectionVariables"
    ),
    globals: __makeVariableScope(__pm_context.global_vars, "globals", "global_variable_changes"),

    test: function (name, fn) {
        var start = Date.now();
        var result = { name: name, passed: true, error: null, duration_ms: 0 };
        try {
            fn();
        } catch (e) {
            result.passed = false;
            result.error = e.message || String(e);
        }
        result.duration_ms = Date.now() - start;
        __pm_state.test_results.push(result);
    },

    expect: function (value) {
        return new __Expectation(value);
    },

    require: function (specifier) {
        if (typeof specifier !== "string" || specifier.length === 0) {
            throw new Error("pm.require: specifier must be a non-empty string");
        }
        if (specifier.indexOf("npm:") !== 0 && specifier.indexOf("jsr:") !== 0) {
            throw new Error(
                "pm.require: specifier must start with 'npm:' or 'jsr:' (got '" +
                    specifier +
                    "')"
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

    sendRequest: function (spec, callback) {
        if (__pm_state.send_request_count >= 10) {
            throw new Error("pm.sendRequest rate limit exceeded (max 10)");
        }
        __pm_state.send_request_count++;
        var idx = __pm_callbacks.length;
        __pm_callbacks.push(callback || null);
        var reqSpec =
            typeof spec === "string" ? { url: spec, method: "GET" } : spec;
        __pm_state._send_queue.push({
            spec: reqSpec,
            callbackIndex: idx,
        });
    },

    cookies: (function () {
        var cookies = {};
        if (__pm_context.response) {
            var hdrs = __pm_context.response.headers || [];
            for (var i = 0; i < hdrs.length; i++) {
                if (
                    (hdrs[i].key || "").toLowerCase() === "set-cookie"
                ) {
                    var raw = hdrs[i].value || "";
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
        }
        return {
            get: function (name) {
                return cookies.hasOwnProperty(name)
                    ? cookies[name]
                    : undefined;
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
        };
    })(),

    execution: {
        setNextRequest: function (name) {
            __pm_state.next_request =
                name === null || name === undefined ? null : String(name);
        },
        skipRequest: function () {
            __pm_state.skip_request = true;
        },
    },

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
};

// -- sendRequest callback fulfillment ---------------------------------

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
        url: pm.request.url,
        method: pm.request.method,
        headers: pm.request.headers._toArray
            ? pm.request.headers._toArray()
            : [],
        body: pm.request.body,
    };
}

// ``Debugger.evaluateOnCallFrame`` evaluates in the paused user frame; module
// top-level ``var`` bindings are not in that lexical environment.  Mirror the
// live objects onto ``globalThis`` so debug variable reads see ``variable_changes``.
if (typeof globalThis !== "undefined") {
    globalThis.__pm_state = __pm_state;
    globalThis.pm = pm;
}
