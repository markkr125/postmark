// polyfills.js — Browser/Node API polyfills for V8 sandbox.
//
// Provides globals that Postman scripts expect but are absent from
// bare V8:  crypto.getRandomValues, atob, btoa, window, self, global.
//
// Loaded before vendor libraries and the pm bootstrap.

// -- Global scope aliases (needed by xml2js/timers-browserify) ----------

if (typeof globalThis.window === "undefined") globalThis.window = globalThis;
if (typeof globalThis.self === "undefined") globalThis.self = globalThis;
if (typeof globalThis.global === "undefined") globalThis.global = globalThis;

// -- crypto.getRandomValues (needed by crypto-js AES/random) -----------
// Math.random is not cryptographically secure, but this is an API
// testing sandbox, not a production crypto application.

(function () {
    if (typeof globalThis.crypto === "undefined") {
        globalThis.crypto = {};
    }
    if (typeof globalThis.crypto.getRandomValues !== "function") {
        globalThis.crypto.getRandomValues = function (array) {
            for (var i = 0; i < array.length; i++) {
                array[i] = (Math.random() * 0x100000000) >>> 0;
            }
            return array;
        };
    }
})();

// -- atob / btoa (Base64 encode / decode) ------------------------------

(function () {
    var CHARS =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=";

    if (typeof globalThis.btoa !== "function") {
        globalThis.btoa = function (input) {
            var str = String(input);
            var output = "";
            for (
                var block, charCode, idx = 0, map = CHARS;
                str.charAt(idx | 0) || ((map = "="), idx % 1);
                output += map.charAt(63 & (block >> (8 - (idx % 1) * 8)))
            ) {
                charCode = str.charCodeAt((idx += 3 / 4));
                if (charCode > 0xff) {
                    throw new Error(
                        "btoa failed: character out of latin1 range"
                    );
                }
                block = (block << 8) | charCode;
            }
            return output;
        };
    }

    if (typeof globalThis.atob !== "function") {
        globalThis.atob = function (input) {
            var str = String(input).replace(/=+$/, "");
            if (str.length % 4 === 1) {
                throw new Error("atob failed: invalid input");
            }
            var output = "";
            for (
                var bc = 0, bs, buffer, idx = 0;
                (buffer = str.charAt(idx++));
                ~buffer &&
                ((bs = bc % 4 ? bs * 64 + buffer : buffer),
                bc++ % 4)
                    ? (output += String.fromCharCode(
                          255 & (bs >> ((-2 * bc) & 6))
                      ))
                    : 0
            ) {
                buffer = CHARS.indexOf(buffer);
            }
            return output;
        };
    }
})();
