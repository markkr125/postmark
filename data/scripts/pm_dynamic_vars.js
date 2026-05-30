// Postmark dynamic variable resolver — reads globalThis.__pm_dynvar (injected JSON).
(function () {
    function pick(pool, pools) {
        var items = pools[pool];
        if (!items || !items.length) return "";
        return items[Math.floor(Math.random() * items.length)];
    }

    function uuidV4() {
        var bytes = new Uint8Array(16);
        globalThis.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
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

    function randInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function applyRule(rule, pools) {
        var kind = rule.rule;
        if (kind === "uuid") return uuidV4();
        if (kind === "unixTime") return String(Math.floor(Date.now() / 1000));
        if (kind === "isoTime") return new Date().toISOString();
        if (kind === "intRange") return String(randInt(rule.min || 0, rule.max || 1000));
        if (kind === "floatRange") {
            var lo = rule.min || 0;
            var hi = rule.max || 1;
            var dec = rule.decimals || 2;
            var val = lo + (hi - lo) * Math.random();
            return val.toFixed(dec);
        }
        if (kind === "boolean") return Math.random() < 0.5 ? "true" : "false";
        if (kind === "pick") return pick(rule.pool, pools);
        if (kind === "picks") {
            var mn = rule.min || 1;
            var mx = rule.max || mn;
            var count = randInt(mn, mx);
            var out = [];
            for (var i = 0; i < count; i++) out.push(pick(rule.pool, pools));
            return out.join(" ");
        }
        if (kind === "template") {
            var parts = rule.parts || [];
            var s = "";
            for (var j = 0; j < parts.length; j++) {
                var p = parts[j];
                if (typeof p === "string") s += p;
                else if (p && p.pool) s += pick(p.pool, pools);
            }
            return s;
        }
        if (kind === "hexColor") return "#" + Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0");
        if (kind === "ipv4") {
            return [0, 1, 2, 3].map(function () {
                return String(Math.floor(Math.random() * 256));
            }).join(".");
        }
        if (kind === "ipv6") {
            return [0, 1, 2, 3, 4, 5, 6, 7].map(function () {
                return Math.floor(Math.random() * 0xffff).toString(16);
            }).join(":");
        }
        if (kind === "mac") {
            return [0, 1, 2, 3, 4, 5].map(function () {
                return Math.floor(Math.random() * 256).toString(16).padStart(2, "0");
            }).join(":");
        }
        if (kind === "alphaNumeric") {
            var chars = "abcdefghijklmnopqrstuvwxyz0123456789";
            return chars.charAt(Math.floor(Math.random() * chars.length));
        }
        if (kind === "password") {
            var alpha = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%";
            var pw = "";
            for (var k = 0; k < 16; k++) pw += alpha.charAt(Math.floor(Math.random() * alpha.length));
            return pw;
        }
        if (kind === "semver") return randInt(0, 9) + "." + randInt(0, 19) + "." + randInt(0, 99);
        if (kind === "phone") return "+1" + String(randInt(1000000000, 9999999999));
        if (kind === "phoneExt") return applyRule({ rule: "phone" }, pools) + " x" + randInt(100, 999);
        if (kind === "streetAddress") return randInt(1, 9999) + " " + pick("streets", pools);
        if (kind === "latitude") return (Math.random() * 180 - 90).toFixed(6);
        if (kind === "longitude") return (Math.random() * 360 - 180).toFixed(6);
        if (kind === "imageUrl" || kind === "imageDataUri") {
            if (kind === "imageDataUri") {
                return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
            }
            var cat = rule.pool || "abstract";
            var seed = Math.random().toString(36).slice(2, 10);
            return "https://picsum.photos/seed/" + seed + "/400/300?" + cat;
        }
        if (kind === "bankAccount") {
            var acct = "";
            for (var b = 0; b < 10; b++) acct += String(randInt(0, 9));
            return acct;
        }
        if (kind === "creditCardMask") return "****-****-****-" + String(randInt(1000, 9999));
        if (kind === "bic") {
            var bic = "";
            for (var c = 0; c < 8; c++) bic += String.fromCharCode(65 + randInt(0, 25));
            return bic + "XX";
        }
        if (kind === "iban") {
            var ib = "GB";
            for (var d = 0; d < 20; d++) ib += String(randInt(0, 9));
            return ib;
        }
        if (kind === "bitcoin") return "bc1" + Math.random().toString(16).slice(2, 18);
        if (kind === "companyName") return pick("lastNames", pools) + " " + pick("companySuffixes", pools);
        if (kind === "dateFuture" || kind === "datePast" || kind === "dateRecent") {
            var now = Date.now();
            var offset = randInt(1, kind === "dateRecent" ? 30 : 365);
            if (kind === "dateFuture") now += offset * 86400000;
            else now -= offset * 86400000;
            return new Date(now).toISOString().slice(0, 10);
        }
        if (kind === "domainName") return pick("words", pools) + "." + pick("domains", pools);
        if (kind === "exampleEmail") return "user" + randInt(0, 99999) + "@example.com";
        if (kind === "userName") return pick("firstNames", pools).toLowerCase() + randInt(0, 999);
        if (kind === "url") return "https://" + pick("words", pools) + "." + pick("domains", pools);
        if (kind === "fileName" || kind === "filePath" || kind === "directoryPath") {
            if (kind === "directoryPath") return "/var/data/" + pick("words", pools);
            if (kind === "filePath") return "/tmp/" + pick("words", pools) + "." + pick("fileExts", pools);
            return "file_" + Math.random().toString(36).slice(2, 6) + "." + pick("fileExts", pools);
        }
        if (kind === "price") return (randInt(0, 10000) / 100).toFixed(2);
        if (kind === "ingVerb") {
            var vb = pick("hackerVerbs", pools);
            return vb.endsWith("ing") ? vb : vb + "ing";
        }
        if (kind === "loremSentence") {
            var wds = [];
            for (var ls = 0; ls < randInt(3, 10); ls++) wds.push(pick("loremWords", pools));
            return wds.join(" ").replace(/^\w/, function (c) { return c.toUpperCase(); }) + ".";
        }
        if (kind === "loremSentences" || kind === "loremParagraph" || kind === "loremParagraphs" || kind === "loremText") {
            return applyRule({ rule: "loremSentence" }, pools);
        }
        if (kind === "loremSlug") {
            return [pick("loremWords", pools), pick("loremWords", pools), pick("loremWords", pools)].join("-");
        }
        if (kind === "loremLines") {
            return applyRule({ rule: "loremSentence" }, pools) + "\n" + applyRule({ rule: "loremSentence" }, pools);
        }
        if (kind === "hackerAbbr") return "IO";
        if (kind === "hackerPhrase") {
            return (
                "If we " +
                pick("hackerVerbs", pools) +
                " the " +
                pick("hackerNouns", pools) +
                ", we can get to the " +
                pick("hackerNouns", pools) +
                "."
            );
        }
        return "";
    }

    globalThis.__pm_resolveDynamic = function (name) {
        var key = String(name || "").trim();
        if (!key) return null;
        if (key.charAt(0) !== "$") key = "$" + key;
        var data = globalThis.__pm_dynvar;
        if (!data || !data.vars) return null;
        var rule = data.vars[key];
        if (!rule) return null;
        return applyRule(rule, data.pools || {});
    };
})();
