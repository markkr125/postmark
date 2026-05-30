// Minimal JSON Schema validator — mirrors services.scripting.json_schema_mini.
(function () {
    function typeMatches(value, expected) {
        if (expected === "null") return value === null;
        if (expected === "boolean") return typeof value === "boolean";
        if (expected === "integer") return Number.isInteger(value);
        if (expected === "number") return typeof value === "number";
        if (expected === "string") return typeof value === "string";
        if (expected === "array") return Array.isArray(value);
        if (expected === "object") return value !== null && typeof value === "object" && !Array.isArray(value);
        return true;
    }

    function validateValue(value, schema, path, errors) {
        if (schema.enum && schema.enum.indexOf(value) < 0) {
            errors.push((path || "root") + ": not in enum");
            return;
        }
        if (schema.type && !typeMatches(value, schema.type)) {
            errors.push((path || "root") + ": expected type " + schema.type);
            return;
        }
        if (typeof value === "string") {
            if (schema.minLength !== undefined && value.length < schema.minLength) {
                errors.push(path + ": minLength");
            }
            if (schema.maxLength !== undefined && value.length > schema.maxLength) {
                errors.push(path + ": maxLength");
            }
        }
        if (typeof value === "number") {
            if (schema.minimum !== undefined && value < schema.minimum) errors.push(path + ": minimum");
            if (schema.maximum !== undefined && value > schema.maximum) errors.push(path + ": maximum");
        }
        if (Array.isArray(value)) {
            if (schema.minItems !== undefined && value.length < schema.minItems) {
                errors.push(path + ": minItems");
            }
            if (schema.maxItems !== undefined && value.length > schema.maxItems) {
                errors.push(path + ": maxItems");
            }
            if (schema.items) {
                for (var i = 0; i < value.length; i++) {
                    validateValue(value[i], schema.items, path + "[" + i + "]", errors);
                }
            }
        }
        if (value !== null && typeof value === "object" && !Array.isArray(value)) {
            var req = schema.required || [];
            for (var r = 0; r < req.length; r++) {
                if (!Object.prototype.hasOwnProperty.call(value, req[r])) {
                    errors.push(path + "." + req[r] + ": required");
                }
            }
            var props = schema.properties || {};
            var keys = Object.keys(props);
            for (var k = 0; k < keys.length; k++) {
                var pk = keys[k];
                if (Object.prototype.hasOwnProperty.call(value, pk)) {
                    validateValue(value[pk], props[pk], path ? path + "." + pk : pk, errors);
                }
            }
        }
    }

    globalThis.__pm_validateSchema = function (data, schema) {
        var errors = [];
        validateValue(data, schema || {}, "", errors);
        return { ok: errors.length === 0, errors: errors };
    };
})();
