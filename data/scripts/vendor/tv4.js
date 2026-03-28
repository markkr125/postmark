(() => {
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __commonJS = (cb, mod) => function __require() {
    return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
  };

  // node_modules/tv4/tv4.js
  var require_tv4 = __commonJS({
    "node_modules/tv4/tv4.js"(exports, module) {
      (function(global, factory) {
        if (typeof define === "function" && define.amd) {
          define([], factory);
        } else if (typeof module !== "undefined" && module.exports) {
          module.exports = factory();
        } else {
          global.tv4 = factory();
        }
      })(exports, function() {
        if (!Object.keys) {
          Object.keys = function() {
            var hasOwnProperty = Object.prototype.hasOwnProperty, hasDontEnumBug = !{ toString: null }.propertyIsEnumerable("toString"), dontEnums = [
              "toString",
              "toLocaleString",
              "valueOf",
              "hasOwnProperty",
              "isPrototypeOf",
              "propertyIsEnumerable",
              "constructor"
            ], dontEnumsLength = dontEnums.length;
            return function(obj) {
              if (typeof obj !== "object" && typeof obj !== "function" || obj === null) {
                throw new TypeError("Object.keys called on non-object");
              }
              var result = [];
              for (var prop in obj) {
                if (hasOwnProperty.call(obj, prop)) {
                  result.push(prop);
                }
              }
              if (hasDontEnumBug) {
                for (var i = 0; i < dontEnumsLength; i++) {
                  if (hasOwnProperty.call(obj, dontEnums[i])) {
                    result.push(dontEnums[i]);
                  }
                }
              }
              return result;
            };
          }();
        }
        if (!Object.create) {
          Object.create = /* @__PURE__ */ function() {
            function F() {
            }
            return function(o) {
              if (arguments.length !== 1) {
                throw new Error("Object.create implementation only accepts one parameter.");
              }
              F.prototype = o;
              return new F();
            };
          }();
        }
        if (!Array.isArray) {
          Array.isArray = function(vArg) {
            return Object.prototype.toString.call(vArg) === "[object Array]";
          };
        }
        if (!Array.prototype.indexOf) {
          Array.prototype.indexOf = function(searchElement) {
            if (this === null) {
              throw new TypeError();
            }
            var t = Object(this);
            var len = t.length >>> 0;
            if (len === 0) {
              return -1;
            }
            var n = 0;
            if (arguments.length > 1) {
              n = Number(arguments[1]);
              if (n !== n) {
                n = 0;
              } else if (n !== 0 && n !== Infinity && n !== -Infinity) {
                n = (n > 0 || -1) * Math.floor(Math.abs(n));
              }
            }
            if (n >= len) {
              return -1;
            }
            var k = n >= 0 ? n : Math.max(len - Math.abs(n), 0);
            for (; k < len; k++) {
              if (k in t && t[k] === searchElement) {
                return k;
              }
            }
            return -1;
          };
        }
        if (!Object.isFrozen) {
          Object.isFrozen = function(obj) {
            var key2 = "tv4_test_frozen_key";
            while (obj.hasOwnProperty(key2)) {
              key2 += Math.random();
            }
            try {
              obj[key2] = true;
              delete obj[key2];
              return false;
            } catch (e) {
              return true;
            }
          };
        }
        var uriTemplateGlobalModifiers = {
          "+": true,
          "#": true,
          ".": true,
          "/": true,
          ";": true,
          "?": true,
          "&": true
        };
        var uriTemplateSuffices = {
          "*": true
        };
        function notReallyPercentEncode(string) {
          return encodeURI(string).replace(/%25[0-9][0-9]/g, function(doubleEncoded) {
            return "%" + doubleEncoded.substring(3);
          });
        }
        function uriTemplateSubstitution(spec) {
          var modifier = "";
          if (uriTemplateGlobalModifiers[spec.charAt(0)]) {
            modifier = spec.charAt(0);
            spec = spec.substring(1);
          }
          var separator = "";
          var prefix = "";
          var shouldEscape = true;
          var showVariables = false;
          var trimEmptyString = false;
          if (modifier === "+") {
            shouldEscape = false;
          } else if (modifier === ".") {
            prefix = ".";
            separator = ".";
          } else if (modifier === "/") {
            prefix = "/";
            separator = "/";
          } else if (modifier === "#") {
            prefix = "#";
            shouldEscape = false;
          } else if (modifier === ";") {
            prefix = ";";
            separator = ";";
            showVariables = true;
            trimEmptyString = true;
          } else if (modifier === "?") {
            prefix = "?";
            separator = "&";
            showVariables = true;
          } else if (modifier === "&") {
            prefix = "&";
            separator = "&";
            showVariables = true;
          }
          var varNames = [];
          var varList = spec.split(",");
          var varSpecs = [];
          var varSpecMap = {};
          for (var i = 0; i < varList.length; i++) {
            var varName = varList[i];
            var truncate = null;
            if (varName.indexOf(":") !== -1) {
              var parts = varName.split(":");
              varName = parts[0];
              truncate = parseInt(parts[1], 10);
            }
            var suffices = {};
            while (uriTemplateSuffices[varName.charAt(varName.length - 1)]) {
              suffices[varName.charAt(varName.length - 1)] = true;
              varName = varName.substring(0, varName.length - 1);
            }
            var varSpec = {
              truncate,
              name: varName,
              suffices
            };
            varSpecs.push(varSpec);
            varSpecMap[varName] = varSpec;
            varNames.push(varName);
          }
          var subFunction = function(valueFunction) {
            var result = "";
            var startIndex = 0;
            for (var i2 = 0; i2 < varSpecs.length; i2++) {
              var varSpec2 = varSpecs[i2];
              var value = valueFunction(varSpec2.name);
              if (value === null || value === void 0 || Array.isArray(value) && value.length === 0 || typeof value === "object" && Object.keys(value).length === 0) {
                startIndex++;
                continue;
              }
              if (i2 === startIndex) {
                result += prefix;
              } else {
                result += separator || ",";
              }
              if (Array.isArray(value)) {
                if (showVariables) {
                  result += varSpec2.name + "=";
                }
                for (var j = 0; j < value.length; j++) {
                  if (j > 0) {
                    result += varSpec2.suffices["*"] ? separator || "," : ",";
                    if (varSpec2.suffices["*"] && showVariables) {
                      result += varSpec2.name + "=";
                    }
                  }
                  result += shouldEscape ? encodeURIComponent(value[j]).replace(/!/g, "%21") : notReallyPercentEncode(value[j]);
                }
              } else if (typeof value === "object") {
                if (showVariables && !varSpec2.suffices["*"]) {
                  result += varSpec2.name + "=";
                }
                var first = true;
                for (var key2 in value) {
                  if (!first) {
                    result += varSpec2.suffices["*"] ? separator || "," : ",";
                  }
                  first = false;
                  result += shouldEscape ? encodeURIComponent(key2).replace(/!/g, "%21") : notReallyPercentEncode(key2);
                  result += varSpec2.suffices["*"] ? "=" : ",";
                  result += shouldEscape ? encodeURIComponent(value[key2]).replace(/!/g, "%21") : notReallyPercentEncode(value[key2]);
                }
              } else {
                if (showVariables) {
                  result += varSpec2.name;
                  if (!trimEmptyString || value !== "") {
                    result += "=";
                  }
                }
                if (varSpec2.truncate != null) {
                  value = value.substring(0, varSpec2.truncate);
                }
                result += shouldEscape ? encodeURIComponent(value).replace(/!/g, "%21") : notReallyPercentEncode(value);
              }
            }
            return result;
          };
          subFunction.varNames = varNames;
          return {
            prefix,
            substitution: subFunction
          };
        }
        function UriTemplate(template) {
          if (!(this instanceof UriTemplate)) {
            return new UriTemplate(template);
          }
          var parts = template.split("{");
          var textParts = [parts.shift()];
          var prefixes = [];
          var substitutions = [];
          var varNames = [];
          while (parts.length > 0) {
            var part = parts.shift();
            var spec = part.split("}")[0];
            var remainder = part.substring(spec.length + 1);
            var funcs = uriTemplateSubstitution(spec);
            substitutions.push(funcs.substitution);
            prefixes.push(funcs.prefix);
            textParts.push(remainder);
            varNames = varNames.concat(funcs.substitution.varNames);
          }
          this.fill = function(valueFunction) {
            var result = textParts[0];
            for (var i = 0; i < substitutions.length; i++) {
              var substitution = substitutions[i];
              result += substitution(valueFunction);
              result += textParts[i + 1];
            }
            return result;
          };
          this.varNames = varNames;
          this.template = template;
        }
        UriTemplate.prototype = {
          toString: function() {
            return this.template;
          },
          fillFromObject: function(obj) {
            return this.fill(function(varName) {
              return obj[varName];
            });
          }
        };
        var ValidatorContext = function ValidatorContext2(parent, collectMultiple, errorReporter, checkRecursive, trackUnknownProperties) {
          this.missing = [];
          this.missingMap = {};
          this.formatValidators = parent ? Object.create(parent.formatValidators) : {};
          this.schemas = parent ? Object.create(parent.schemas) : {};
          this.collectMultiple = collectMultiple;
          this.errors = [];
          this.handleError = collectMultiple ? this.collectError : this.returnError;
          if (checkRecursive) {
            this.checkRecursive = true;
            this.scanned = [];
            this.scannedFrozen = [];
            this.scannedFrozenSchemas = [];
            this.scannedFrozenValidationErrors = [];
            this.validatedSchemasKey = "tv4_validation_id";
            this.validationErrorsKey = "tv4_validation_errors_id";
          }
          if (trackUnknownProperties) {
            this.trackUnknownProperties = true;
            this.knownPropertyPaths = {};
            this.unknownPropertyPaths = {};
          }
          this.errorReporter = errorReporter || defaultErrorReporter("en");
          if (typeof this.errorReporter === "string") {
            throw new Error("debug");
          }
          this.definedKeywords = {};
          if (parent) {
            for (var key2 in parent.definedKeywords) {
              this.definedKeywords[key2] = parent.definedKeywords[key2].slice(0);
            }
          }
        };
        ValidatorContext.prototype.defineKeyword = function(keyword, keywordFunction) {
          this.definedKeywords[keyword] = this.definedKeywords[keyword] || [];
          this.definedKeywords[keyword].push(keywordFunction);
        };
        ValidatorContext.prototype.createError = function(code, messageParams, dataPath, schemaPath, subErrors, data, schema) {
          var error = new ValidationError(code, messageParams, dataPath, schemaPath, subErrors);
          error.message = this.errorReporter(error, data, schema);
          return error;
        };
        ValidatorContext.prototype.returnError = function(error) {
          return error;
        };
        ValidatorContext.prototype.collectError = function(error) {
          if (error) {
            this.errors.push(error);
          }
          return null;
        };
        ValidatorContext.prototype.prefixErrors = function(startIndex, dataPath, schemaPath) {
          for (var i = startIndex; i < this.errors.length; i++) {
            this.errors[i] = this.errors[i].prefixWith(dataPath, schemaPath);
          }
          return this;
        };
        ValidatorContext.prototype.banUnknownProperties = function(data, schema) {
          for (var unknownPath in this.unknownPropertyPaths) {
            var error = this.createError(ErrorCodes.UNKNOWN_PROPERTY, { path: unknownPath }, unknownPath, "", null, data, schema);
            var result = this.handleError(error);
            if (result) {
              return result;
            }
          }
          return null;
        };
        ValidatorContext.prototype.addFormat = function(format, validator) {
          if (typeof format === "object") {
            for (var key2 in format) {
              this.addFormat(key2, format[key2]);
            }
            return this;
          }
          this.formatValidators[format] = validator;
        };
        ValidatorContext.prototype.resolveRefs = function(schema, urlHistory) {
          if (schema["$ref"] !== void 0) {
            urlHistory = urlHistory || {};
            if (urlHistory[schema["$ref"]]) {
              return this.createError(ErrorCodes.CIRCULAR_REFERENCE, { urls: Object.keys(urlHistory).join(", ") }, "", "", null, void 0, schema);
            }
            urlHistory[schema["$ref"]] = true;
            schema = this.getSchema(schema["$ref"], urlHistory);
          }
          return schema;
        };
        ValidatorContext.prototype.getSchema = function(url, urlHistory) {
          var schema;
          if (this.schemas[url] !== void 0) {
            schema = this.schemas[url];
            return this.resolveRefs(schema, urlHistory);
          }
          var baseUrl = url;
          var fragment = "";
          if (url.indexOf("#") !== -1) {
            fragment = url.substring(url.indexOf("#") + 1);
            baseUrl = url.substring(0, url.indexOf("#"));
          }
          if (typeof this.schemas[baseUrl] === "object") {
            schema = this.schemas[baseUrl];
            var pointerPath = decodeURIComponent(fragment);
            if (pointerPath === "") {
              return this.resolveRefs(schema, urlHistory);
            } else if (pointerPath.charAt(0) !== "/") {
              return void 0;
            }
            var parts = pointerPath.split("/").slice(1);
            for (var i = 0; i < parts.length; i++) {
              var component = parts[i].replace(/~1/g, "/").replace(/~0/g, "~");
              if (schema[component] === void 0) {
                schema = void 0;
                break;
              }
              schema = schema[component];
            }
            if (schema !== void 0) {
              return this.resolveRefs(schema, urlHistory);
            }
          }
          if (this.missing[baseUrl] === void 0) {
            this.missing.push(baseUrl);
            this.missing[baseUrl] = baseUrl;
            this.missingMap[baseUrl] = baseUrl;
          }
        };
        ValidatorContext.prototype.searchSchemas = function(schema, url) {
          if (Array.isArray(schema)) {
            for (var i = 0; i < schema.length; i++) {
              this.searchSchemas(schema[i], url);
            }
          } else if (schema && typeof schema === "object") {
            if (typeof schema.id === "string") {
              if (isTrustedUrl(url, schema.id)) {
                if (this.schemas[schema.id] === void 0) {
                  this.schemas[schema.id] = schema;
                }
              }
            }
            for (var key2 in schema) {
              if (key2 !== "enum") {
                if (typeof schema[key2] === "object") {
                  this.searchSchemas(schema[key2], url);
                } else if (key2 === "$ref") {
                  var uri = getDocumentUri(schema[key2]);
                  if (uri && this.schemas[uri] === void 0 && this.missingMap[uri] === void 0) {
                    this.missingMap[uri] = uri;
                  }
                }
              }
            }
          }
        };
        ValidatorContext.prototype.addSchema = function(url, schema) {
          if (typeof url !== "string" || typeof schema === "undefined") {
            if (typeof url === "object" && typeof url.id === "string") {
              schema = url;
              url = schema.id;
            } else {
              return;
            }
          }
          if (url === getDocumentUri(url) + "#") {
            url = getDocumentUri(url);
          }
          this.schemas[url] = schema;
          delete this.missingMap[url];
          normSchema(schema, url);
          this.searchSchemas(schema, url);
        };
        ValidatorContext.prototype.getSchemaMap = function() {
          var map = {};
          for (var key2 in this.schemas) {
            map[key2] = this.schemas[key2];
          }
          return map;
        };
        ValidatorContext.prototype.getSchemaUris = function(filterRegExp) {
          var list = [];
          for (var key2 in this.schemas) {
            if (!filterRegExp || filterRegExp.test(key2)) {
              list.push(key2);
            }
          }
          return list;
        };
        ValidatorContext.prototype.getMissingUris = function(filterRegExp) {
          var list = [];
          for (var key2 in this.missingMap) {
            if (!filterRegExp || filterRegExp.test(key2)) {
              list.push(key2);
            }
          }
          return list;
        };
        ValidatorContext.prototype.dropSchemas = function() {
          this.schemas = {};
          this.reset();
        };
        ValidatorContext.prototype.reset = function() {
          this.missing = [];
          this.missingMap = {};
          this.errors = [];
        };
        ValidatorContext.prototype.validateAll = function(data, schema, dataPathParts, schemaPathParts, dataPointerPath) {
          var topLevel;
          schema = this.resolveRefs(schema);
          if (!schema) {
            return null;
          } else if (schema instanceof ValidationError) {
            this.errors.push(schema);
            return schema;
          }
          var startErrorCount = this.errors.length;
          var frozenIndex, scannedFrozenSchemaIndex = null, scannedSchemasIndex = null;
          if (this.checkRecursive && data && typeof data === "object") {
            topLevel = !this.scanned.length;
            if (data[this.validatedSchemasKey]) {
              var schemaIndex = data[this.validatedSchemasKey].indexOf(schema);
              if (schemaIndex !== -1) {
                this.errors = this.errors.concat(data[this.validationErrorsKey][schemaIndex]);
                return null;
              }
            }
            if (Object.isFrozen(data)) {
              frozenIndex = this.scannedFrozen.indexOf(data);
              if (frozenIndex !== -1) {
                var frozenSchemaIndex = this.scannedFrozenSchemas[frozenIndex].indexOf(schema);
                if (frozenSchemaIndex !== -1) {
                  this.errors = this.errors.concat(this.scannedFrozenValidationErrors[frozenIndex][frozenSchemaIndex]);
                  return null;
                }
              }
            }
            this.scanned.push(data);
            if (Object.isFrozen(data)) {
              if (frozenIndex === -1) {
                frozenIndex = this.scannedFrozen.length;
                this.scannedFrozen.push(data);
                this.scannedFrozenSchemas.push([]);
              }
              scannedFrozenSchemaIndex = this.scannedFrozenSchemas[frozenIndex].length;
              this.scannedFrozenSchemas[frozenIndex][scannedFrozenSchemaIndex] = schema;
              this.scannedFrozenValidationErrors[frozenIndex][scannedFrozenSchemaIndex] = [];
            } else {
              if (!data[this.validatedSchemasKey]) {
                try {
                  Object.defineProperty(data, this.validatedSchemasKey, {
                    value: [],
                    configurable: true
                  });
                  Object.defineProperty(data, this.validationErrorsKey, {
                    value: [],
                    configurable: true
                  });
                } catch (e) {
                  data[this.validatedSchemasKey] = [];
                  data[this.validationErrorsKey] = [];
                }
              }
              scannedSchemasIndex = data[this.validatedSchemasKey].length;
              data[this.validatedSchemasKey][scannedSchemasIndex] = schema;
              data[this.validationErrorsKey][scannedSchemasIndex] = [];
            }
          }
          var errorCount = this.errors.length;
          var error = this.validateBasic(data, schema, dataPointerPath) || this.validateNumeric(data, schema, dataPointerPath) || this.validateString(data, schema, dataPointerPath) || this.validateArray(data, schema, dataPointerPath) || this.validateObject(data, schema, dataPointerPath) || this.validateCombinations(data, schema, dataPointerPath) || this.validateHypermedia(data, schema, dataPointerPath) || this.validateFormat(data, schema, dataPointerPath) || this.validateDefinedKeywords(data, schema, dataPointerPath) || null;
          if (topLevel) {
            while (this.scanned.length) {
              var item = this.scanned.pop();
              delete item[this.validatedSchemasKey];
            }
            this.scannedFrozen = [];
            this.scannedFrozenSchemas = [];
          }
          if (error || errorCount !== this.errors.length) {
            while (dataPathParts && dataPathParts.length || schemaPathParts && schemaPathParts.length) {
              var dataPart = dataPathParts && dataPathParts.length ? "" + dataPathParts.pop() : null;
              var schemaPart = schemaPathParts && schemaPathParts.length ? "" + schemaPathParts.pop() : null;
              if (error) {
                error = error.prefixWith(dataPart, schemaPart);
              }
              this.prefixErrors(errorCount, dataPart, schemaPart);
            }
          }
          if (scannedFrozenSchemaIndex !== null) {
            this.scannedFrozenValidationErrors[frozenIndex][scannedFrozenSchemaIndex] = this.errors.slice(startErrorCount);
          } else if (scannedSchemasIndex !== null) {
            data[this.validationErrorsKey][scannedSchemasIndex] = this.errors.slice(startErrorCount);
          }
          return this.handleError(error);
        };
        ValidatorContext.prototype.validateFormat = function(data, schema) {
          if (typeof schema.format !== "string" || !this.formatValidators[schema.format]) {
            return null;
          }
          var errorMessage = this.formatValidators[schema.format].call(null, data, schema);
          if (typeof errorMessage === "string" || typeof errorMessage === "number") {
            return this.createError(ErrorCodes.FORMAT_CUSTOM, { message: errorMessage }, "", "/format", null, data, schema);
          } else if (errorMessage && typeof errorMessage === "object") {
            return this.createError(ErrorCodes.FORMAT_CUSTOM, { message: errorMessage.message || "?" }, errorMessage.dataPath || "", errorMessage.schemaPath || "/format", null, data, schema);
          }
          return null;
        };
        ValidatorContext.prototype.validateDefinedKeywords = function(data, schema, dataPointerPath) {
          for (var key2 in this.definedKeywords) {
            if (typeof schema[key2] === "undefined") {
              continue;
            }
            var validationFunctions = this.definedKeywords[key2];
            for (var i = 0; i < validationFunctions.length; i++) {
              var func = validationFunctions[i];
              var result = func(data, schema[key2], schema, dataPointerPath);
              if (typeof result === "string" || typeof result === "number") {
                return this.createError(ErrorCodes.KEYWORD_CUSTOM, { key: key2, message: result }, "", "", null, data, schema).prefixWith(null, key2);
              } else if (result && typeof result === "object") {
                var code = result.code;
                if (typeof code === "string") {
                  if (!ErrorCodes[code]) {
                    throw new Error("Undefined error code (use defineError): " + code);
                  }
                  code = ErrorCodes[code];
                } else if (typeof code !== "number") {
                  code = ErrorCodes.KEYWORD_CUSTOM;
                }
                var messageParams = typeof result.message === "object" ? result.message : { key: key2, message: result.message || "?" };
                var schemaPath = result.schemaPath || "/" + key2.replace(/~/g, "~0").replace(/\//g, "~1");
                return this.createError(code, messageParams, result.dataPath || null, schemaPath, null, data, schema);
              }
            }
          }
          return null;
        };
        function recursiveCompare(A, B) {
          if (A === B) {
            return true;
          }
          if (A && B && typeof A === "object" && typeof B === "object") {
            if (Array.isArray(A) !== Array.isArray(B)) {
              return false;
            } else if (Array.isArray(A)) {
              if (A.length !== B.length) {
                return false;
              }
              for (var i = 0; i < A.length; i++) {
                if (!recursiveCompare(A[i], B[i])) {
                  return false;
                }
              }
            } else {
              var key2;
              for (key2 in A) {
                if (B[key2] === void 0 && A[key2] !== void 0) {
                  return false;
                }
              }
              for (key2 in B) {
                if (A[key2] === void 0 && B[key2] !== void 0) {
                  return false;
                }
              }
              for (key2 in A) {
                if (!recursiveCompare(A[key2], B[key2])) {
                  return false;
                }
              }
            }
            return true;
          }
          return false;
        }
        ValidatorContext.prototype.validateBasic = function validateBasic(data, schema, dataPointerPath) {
          var error;
          if (error = this.validateType(data, schema, dataPointerPath)) {
            return error.prefixWith(null, "type");
          }
          if (error = this.validateEnum(data, schema, dataPointerPath)) {
            return error.prefixWith(null, "type");
          }
          return null;
        };
        ValidatorContext.prototype.validateType = function validateType(data, schema) {
          if (schema.type === void 0) {
            return null;
          }
          var dataType = typeof data;
          if (data === null) {
            dataType = "null";
          } else if (Array.isArray(data)) {
            dataType = "array";
          }
          var allowedTypes = schema.type;
          if (!Array.isArray(allowedTypes)) {
            allowedTypes = [allowedTypes];
          }
          for (var i = 0; i < allowedTypes.length; i++) {
            var type = allowedTypes[i];
            if (type === dataType || type === "integer" && dataType === "number" && data % 1 === 0) {
              return null;
            }
          }
          return this.createError(ErrorCodes.INVALID_TYPE, { type: dataType, expected: allowedTypes.join("/") }, "", "", null, data, schema);
        };
        ValidatorContext.prototype.validateEnum = function validateEnum(data, schema) {
          if (schema["enum"] === void 0) {
            return null;
          }
          for (var i = 0; i < schema["enum"].length; i++) {
            var enumVal = schema["enum"][i];
            if (recursiveCompare(data, enumVal)) {
              return null;
            }
          }
          return this.createError(ErrorCodes.ENUM_MISMATCH, { value: typeof JSON !== "undefined" ? JSON.stringify(data) : data }, "", "", null, data, schema);
        };
        ValidatorContext.prototype.validateNumeric = function validateNumeric(data, schema, dataPointerPath) {
          return this.validateMultipleOf(data, schema, dataPointerPath) || this.validateMinMax(data, schema, dataPointerPath) || this.validateNaN(data, schema, dataPointerPath) || null;
        };
        var CLOSE_ENOUGH_LOW = Math.pow(2, -51);
        var CLOSE_ENOUGH_HIGH = 1 - CLOSE_ENOUGH_LOW;
        ValidatorContext.prototype.validateMultipleOf = function validateMultipleOf(data, schema) {
          var multipleOf = schema.multipleOf || schema.divisibleBy;
          if (multipleOf === void 0) {
            return null;
          }
          if (typeof data === "number") {
            var remainder = data / multipleOf % 1;
            if (remainder >= CLOSE_ENOUGH_LOW && remainder < CLOSE_ENOUGH_HIGH) {
              return this.createError(ErrorCodes.NUMBER_MULTIPLE_OF, { value: data, multipleOf }, "", "", null, data, schema);
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateMinMax = function validateMinMax(data, schema) {
          if (typeof data !== "number") {
            return null;
          }
          if (schema.minimum !== void 0) {
            if (data < schema.minimum) {
              return this.createError(ErrorCodes.NUMBER_MINIMUM, { value: data, minimum: schema.minimum }, "", "/minimum", null, data, schema);
            }
            if (schema.exclusiveMinimum && data === schema.minimum) {
              return this.createError(ErrorCodes.NUMBER_MINIMUM_EXCLUSIVE, { value: data, minimum: schema.minimum }, "", "/exclusiveMinimum", null, data, schema);
            }
          }
          if (schema.maximum !== void 0) {
            if (data > schema.maximum) {
              return this.createError(ErrorCodes.NUMBER_MAXIMUM, { value: data, maximum: schema.maximum }, "", "/maximum", null, data, schema);
            }
            if (schema.exclusiveMaximum && data === schema.maximum) {
              return this.createError(ErrorCodes.NUMBER_MAXIMUM_EXCLUSIVE, { value: data, maximum: schema.maximum }, "", "/exclusiveMaximum", null, data, schema);
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateNaN = function validateNaN(data, schema) {
          if (typeof data !== "number") {
            return null;
          }
          if (isNaN(data) === true || data === Infinity || data === -Infinity) {
            return this.createError(ErrorCodes.NUMBER_NOT_A_NUMBER, { value: data }, "", "/type", null, data, schema);
          }
          return null;
        };
        ValidatorContext.prototype.validateString = function validateString(data, schema, dataPointerPath) {
          return this.validateStringLength(data, schema, dataPointerPath) || this.validateStringPattern(data, schema, dataPointerPath) || null;
        };
        ValidatorContext.prototype.validateStringLength = function validateStringLength(data, schema) {
          if (typeof data !== "string") {
            return null;
          }
          if (schema.minLength !== void 0) {
            if (data.length < schema.minLength) {
              return this.createError(ErrorCodes.STRING_LENGTH_SHORT, { length: data.length, minimum: schema.minLength }, "", "/minLength", null, data, schema);
            }
          }
          if (schema.maxLength !== void 0) {
            if (data.length > schema.maxLength) {
              return this.createError(ErrorCodes.STRING_LENGTH_LONG, { length: data.length, maximum: schema.maxLength }, "", "/maxLength", null, data, schema);
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateStringPattern = function validateStringPattern(data, schema) {
          if (typeof data !== "string" || typeof schema.pattern !== "string" && !(schema.pattern instanceof RegExp)) {
            return null;
          }
          var regexp;
          if (schema.pattern instanceof RegExp) {
            regexp = schema.pattern;
          } else {
            var body, flags = "";
            var literal = schema.pattern.match(/^\/(.+)\/([img]*)$/);
            if (literal) {
              body = literal[1];
              flags = literal[2];
            } else {
              body = schema.pattern;
            }
            regexp = new RegExp(body, flags);
          }
          if (!regexp.test(data)) {
            return this.createError(ErrorCodes.STRING_PATTERN, { pattern: schema.pattern }, "", "/pattern", null, data, schema);
          }
          return null;
        };
        ValidatorContext.prototype.validateArray = function validateArray(data, schema, dataPointerPath) {
          if (!Array.isArray(data)) {
            return null;
          }
          return this.validateArrayLength(data, schema, dataPointerPath) || this.validateArrayUniqueItems(data, schema, dataPointerPath) || this.validateArrayItems(data, schema, dataPointerPath) || null;
        };
        ValidatorContext.prototype.validateArrayLength = function validateArrayLength(data, schema) {
          var error;
          if (schema.minItems !== void 0) {
            if (data.length < schema.minItems) {
              error = this.createError(ErrorCodes.ARRAY_LENGTH_SHORT, { length: data.length, minimum: schema.minItems }, "", "/minItems", null, data, schema);
              if (this.handleError(error)) {
                return error;
              }
            }
          }
          if (schema.maxItems !== void 0) {
            if (data.length > schema.maxItems) {
              error = this.createError(ErrorCodes.ARRAY_LENGTH_LONG, { length: data.length, maximum: schema.maxItems }, "", "/maxItems", null, data, schema);
              if (this.handleError(error)) {
                return error;
              }
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateArrayUniqueItems = function validateArrayUniqueItems(data, schema) {
          if (schema.uniqueItems) {
            for (var i = 0; i < data.length; i++) {
              for (var j = i + 1; j < data.length; j++) {
                if (recursiveCompare(data[i], data[j])) {
                  var error = this.createError(ErrorCodes.ARRAY_UNIQUE, { match1: i, match2: j }, "", "/uniqueItems", null, data, schema);
                  if (this.handleError(error)) {
                    return error;
                  }
                }
              }
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateArrayItems = function validateArrayItems(data, schema, dataPointerPath) {
          if (schema.items === void 0) {
            return null;
          }
          var error, i;
          if (Array.isArray(schema.items)) {
            for (i = 0; i < data.length; i++) {
              if (i < schema.items.length) {
                if (error = this.validateAll(data[i], schema.items[i], [i], ["items", i], dataPointerPath + "/" + i)) {
                  return error;
                }
              } else if (schema.additionalItems !== void 0) {
                if (typeof schema.additionalItems === "boolean") {
                  if (!schema.additionalItems) {
                    error = this.createError(ErrorCodes.ARRAY_ADDITIONAL_ITEMS, {}, "/" + i, "/additionalItems", null, data, schema);
                    if (this.handleError(error)) {
                      return error;
                    }
                  }
                } else if (error = this.validateAll(data[i], schema.additionalItems, [i], ["additionalItems"], dataPointerPath + "/" + i)) {
                  return error;
                }
              }
            }
          } else {
            for (i = 0; i < data.length; i++) {
              if (error = this.validateAll(data[i], schema.items, [i], ["items"], dataPointerPath + "/" + i)) {
                return error;
              }
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateObject = function validateObject(data, schema, dataPointerPath) {
          if (typeof data !== "object" || data === null || Array.isArray(data)) {
            return null;
          }
          return this.validateObjectMinMaxProperties(data, schema, dataPointerPath) || this.validateObjectRequiredProperties(data, schema, dataPointerPath) || this.validateObjectProperties(data, schema, dataPointerPath) || this.validateObjectDependencies(data, schema, dataPointerPath) || null;
        };
        ValidatorContext.prototype.validateObjectMinMaxProperties = function validateObjectMinMaxProperties(data, schema) {
          var keys = Object.keys(data);
          var error;
          if (schema.minProperties !== void 0) {
            if (keys.length < schema.minProperties) {
              error = this.createError(ErrorCodes.OBJECT_PROPERTIES_MINIMUM, { propertyCount: keys.length, minimum: schema.minProperties }, "", "/minProperties", null, data, schema);
              if (this.handleError(error)) {
                return error;
              }
            }
          }
          if (schema.maxProperties !== void 0) {
            if (keys.length > schema.maxProperties) {
              error = this.createError(ErrorCodes.OBJECT_PROPERTIES_MAXIMUM, { propertyCount: keys.length, maximum: schema.maxProperties }, "", "/maxProperties", null, data, schema);
              if (this.handleError(error)) {
                return error;
              }
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateObjectRequiredProperties = function validateObjectRequiredProperties(data, schema) {
          if (schema.required !== void 0) {
            for (var i = 0; i < schema.required.length; i++) {
              var key2 = schema.required[i];
              if (data[key2] === void 0) {
                var error = this.createError(ErrorCodes.OBJECT_REQUIRED, { key: key2 }, "", "/required/" + i, null, data, schema);
                if (this.handleError(error)) {
                  return error;
                }
              }
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateObjectProperties = function validateObjectProperties(data, schema, dataPointerPath) {
          var error;
          for (var key2 in data) {
            var keyPointerPath = dataPointerPath + "/" + key2.replace(/~/g, "~0").replace(/\//g, "~1");
            var foundMatch = false;
            if (schema.properties !== void 0 && schema.properties[key2] !== void 0) {
              foundMatch = true;
              if (error = this.validateAll(data[key2], schema.properties[key2], [key2], ["properties", key2], keyPointerPath)) {
                return error;
              }
            }
            if (schema.patternProperties !== void 0) {
              for (var patternKey in schema.patternProperties) {
                var regexp = new RegExp(patternKey);
                if (regexp.test(key2)) {
                  foundMatch = true;
                  if (error = this.validateAll(data[key2], schema.patternProperties[patternKey], [key2], ["patternProperties", patternKey], keyPointerPath)) {
                    return error;
                  }
                }
              }
            }
            if (!foundMatch) {
              if (schema.additionalProperties !== void 0) {
                if (this.trackUnknownProperties) {
                  this.knownPropertyPaths[keyPointerPath] = true;
                  delete this.unknownPropertyPaths[keyPointerPath];
                }
                if (typeof schema.additionalProperties === "boolean") {
                  if (!schema.additionalProperties) {
                    error = this.createError(ErrorCodes.OBJECT_ADDITIONAL_PROPERTIES, { key: key2 }, "", "/additionalProperties", null, data, schema).prefixWith(key2, null);
                    if (this.handleError(error)) {
                      return error;
                    }
                  }
                } else {
                  if (error = this.validateAll(data[key2], schema.additionalProperties, [key2], ["additionalProperties"], keyPointerPath)) {
                    return error;
                  }
                }
              } else if (this.trackUnknownProperties && !this.knownPropertyPaths[keyPointerPath]) {
                this.unknownPropertyPaths[keyPointerPath] = true;
              }
            } else if (this.trackUnknownProperties) {
              this.knownPropertyPaths[keyPointerPath] = true;
              delete this.unknownPropertyPaths[keyPointerPath];
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateObjectDependencies = function validateObjectDependencies(data, schema, dataPointerPath) {
          var error;
          if (schema.dependencies !== void 0) {
            for (var depKey in schema.dependencies) {
              if (data[depKey] !== void 0) {
                var dep = schema.dependencies[depKey];
                if (typeof dep === "string") {
                  if (data[dep] === void 0) {
                    error = this.createError(ErrorCodes.OBJECT_DEPENDENCY_KEY, { key: depKey, missing: dep }, "", "", null, data, schema).prefixWith(null, depKey).prefixWith(null, "dependencies");
                    if (this.handleError(error)) {
                      return error;
                    }
                  }
                } else if (Array.isArray(dep)) {
                  for (var i = 0; i < dep.length; i++) {
                    var requiredKey = dep[i];
                    if (data[requiredKey] === void 0) {
                      error = this.createError(ErrorCodes.OBJECT_DEPENDENCY_KEY, { key: depKey, missing: requiredKey }, "", "/" + i, null, data, schema).prefixWith(null, depKey).prefixWith(null, "dependencies");
                      if (this.handleError(error)) {
                        return error;
                      }
                    }
                  }
                } else {
                  if (error = this.validateAll(data, dep, [], ["dependencies", depKey], dataPointerPath)) {
                    return error;
                  }
                }
              }
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateCombinations = function validateCombinations(data, schema, dataPointerPath) {
          return this.validateAllOf(data, schema, dataPointerPath) || this.validateAnyOf(data, schema, dataPointerPath) || this.validateOneOf(data, schema, dataPointerPath) || this.validateNot(data, schema, dataPointerPath) || null;
        };
        ValidatorContext.prototype.validateAllOf = function validateAllOf(data, schema, dataPointerPath) {
          if (schema.allOf === void 0) {
            return null;
          }
          var error;
          for (var i = 0; i < schema.allOf.length; i++) {
            var subSchema = schema.allOf[i];
            if (error = this.validateAll(data, subSchema, [], ["allOf", i], dataPointerPath)) {
              return error;
            }
          }
          return null;
        };
        ValidatorContext.prototype.validateAnyOf = function validateAnyOf(data, schema, dataPointerPath) {
          if (schema.anyOf === void 0) {
            return null;
          }
          var errors = [];
          var startErrorCount = this.errors.length;
          var oldUnknownPropertyPaths, oldKnownPropertyPaths;
          if (this.trackUnknownProperties) {
            oldUnknownPropertyPaths = this.unknownPropertyPaths;
            oldKnownPropertyPaths = this.knownPropertyPaths;
          }
          var errorAtEnd = true;
          for (var i = 0; i < schema.anyOf.length; i++) {
            if (this.trackUnknownProperties) {
              this.unknownPropertyPaths = {};
              this.knownPropertyPaths = {};
            }
            var subSchema = schema.anyOf[i];
            var errorCount = this.errors.length;
            var error = this.validateAll(data, subSchema, [], ["anyOf", i], dataPointerPath);
            if (error === null && errorCount === this.errors.length) {
              this.errors = this.errors.slice(0, startErrorCount);
              if (this.trackUnknownProperties) {
                for (var knownKey in this.knownPropertyPaths) {
                  oldKnownPropertyPaths[knownKey] = true;
                  delete oldUnknownPropertyPaths[knownKey];
                }
                for (var unknownKey in this.unknownPropertyPaths) {
                  if (!oldKnownPropertyPaths[unknownKey]) {
                    oldUnknownPropertyPaths[unknownKey] = true;
                  }
                }
                errorAtEnd = false;
                continue;
              }
              return null;
            }
            if (error) {
              errors.push(error.prefixWith(null, "" + i).prefixWith(null, "anyOf"));
            }
          }
          if (this.trackUnknownProperties) {
            this.unknownPropertyPaths = oldUnknownPropertyPaths;
            this.knownPropertyPaths = oldKnownPropertyPaths;
          }
          if (errorAtEnd) {
            errors = errors.concat(this.errors.slice(startErrorCount));
            this.errors = this.errors.slice(0, startErrorCount);
            return this.createError(ErrorCodes.ANY_OF_MISSING, {}, "", "/anyOf", errors, data, schema);
          }
        };
        ValidatorContext.prototype.validateOneOf = function validateOneOf(data, schema, dataPointerPath) {
          if (schema.oneOf === void 0) {
            return null;
          }
          var validIndex = null;
          var errors = [];
          var startErrorCount = this.errors.length;
          var oldUnknownPropertyPaths, oldKnownPropertyPaths;
          if (this.trackUnknownProperties) {
            oldUnknownPropertyPaths = this.unknownPropertyPaths;
            oldKnownPropertyPaths = this.knownPropertyPaths;
          }
          for (var i = 0; i < schema.oneOf.length; i++) {
            if (this.trackUnknownProperties) {
              this.unknownPropertyPaths = {};
              this.knownPropertyPaths = {};
            }
            var subSchema = schema.oneOf[i];
            var errorCount = this.errors.length;
            var error = this.validateAll(data, subSchema, [], ["oneOf", i], dataPointerPath);
            if (error === null && errorCount === this.errors.length) {
              if (validIndex === null) {
                validIndex = i;
              } else {
                this.errors = this.errors.slice(0, startErrorCount);
                return this.createError(ErrorCodes.ONE_OF_MULTIPLE, { index1: validIndex, index2: i }, "", "/oneOf", null, data, schema);
              }
              if (this.trackUnknownProperties) {
                for (var knownKey in this.knownPropertyPaths) {
                  oldKnownPropertyPaths[knownKey] = true;
                  delete oldUnknownPropertyPaths[knownKey];
                }
                for (var unknownKey in this.unknownPropertyPaths) {
                  if (!oldKnownPropertyPaths[unknownKey]) {
                    oldUnknownPropertyPaths[unknownKey] = true;
                  }
                }
              }
            } else if (error) {
              errors.push(error);
            }
          }
          if (this.trackUnknownProperties) {
            this.unknownPropertyPaths = oldUnknownPropertyPaths;
            this.knownPropertyPaths = oldKnownPropertyPaths;
          }
          if (validIndex === null) {
            errors = errors.concat(this.errors.slice(startErrorCount));
            this.errors = this.errors.slice(0, startErrorCount);
            return this.createError(ErrorCodes.ONE_OF_MISSING, {}, "", "/oneOf", errors, data, schema);
          } else {
            this.errors = this.errors.slice(0, startErrorCount);
          }
          return null;
        };
        ValidatorContext.prototype.validateNot = function validateNot(data, schema, dataPointerPath) {
          if (schema.not === void 0) {
            return null;
          }
          var oldErrorCount = this.errors.length;
          var oldUnknownPropertyPaths, oldKnownPropertyPaths;
          if (this.trackUnknownProperties) {
            oldUnknownPropertyPaths = this.unknownPropertyPaths;
            oldKnownPropertyPaths = this.knownPropertyPaths;
            this.unknownPropertyPaths = {};
            this.knownPropertyPaths = {};
          }
          var error = this.validateAll(data, schema.not, null, null, dataPointerPath);
          var notErrors = this.errors.slice(oldErrorCount);
          this.errors = this.errors.slice(0, oldErrorCount);
          if (this.trackUnknownProperties) {
            this.unknownPropertyPaths = oldUnknownPropertyPaths;
            this.knownPropertyPaths = oldKnownPropertyPaths;
          }
          if (error === null && notErrors.length === 0) {
            return this.createError(ErrorCodes.NOT_PASSED, {}, "", "/not", null, data, schema);
          }
          return null;
        };
        ValidatorContext.prototype.validateHypermedia = function validateCombinations(data, schema, dataPointerPath) {
          if (!schema.links) {
            return null;
          }
          var error;
          for (var i = 0; i < schema.links.length; i++) {
            var ldo = schema.links[i];
            if (ldo.rel === "describedby") {
              var template = new UriTemplate(ldo.href);
              var allPresent = true;
              for (var j = 0; j < template.varNames.length; j++) {
                if (!(template.varNames[j] in data)) {
                  allPresent = false;
                  break;
                }
              }
              if (allPresent) {
                var schemaUrl = template.fillFromObject(data);
                var subSchema = { "$ref": schemaUrl };
                if (error = this.validateAll(data, subSchema, [], ["links", i], dataPointerPath)) {
                  return error;
                }
              }
            }
          }
        };
        function parseURI(url) {
          var m = String(url).replace(/^\s+|\s+$/g, "").match(/^([^:\/?#]+:)?(\/\/(?:[^:@]*(?::[^:@]*)?@)?(([^:\/?#]*)(?::(\d*))?))?([^?#]*)(\?[^#]*)?(#[\s\S]*)?/);
          return m ? {
            href: m[0] || "",
            protocol: m[1] || "",
            authority: m[2] || "",
            host: m[3] || "",
            hostname: m[4] || "",
            port: m[5] || "",
            pathname: m[6] || "",
            search: m[7] || "",
            hash: m[8] || ""
          } : null;
        }
        function resolveUrl(base, href) {
          function removeDotSegments(input) {
            var output = [];
            input.replace(/^(\.\.?(\/|$))+/, "").replace(/\/(\.(\/|$))+/g, "/").replace(/\/\.\.$/, "/../").replace(/\/?[^\/]*/g, function(p) {
              if (p === "/..") {
                output.pop();
              } else {
                output.push(p);
              }
            });
            return output.join("").replace(/^\//, input.charAt(0) === "/" ? "/" : "");
          }
          href = parseURI(href || "");
          base = parseURI(base || "");
          return !href || !base ? null : (href.protocol || base.protocol) + (href.protocol || href.authority ? href.authority : base.authority) + removeDotSegments(href.protocol || href.authority || href.pathname.charAt(0) === "/" ? href.pathname : href.pathname ? (base.authority && !base.pathname ? "/" : "") + base.pathname.slice(0, base.pathname.lastIndexOf("/") + 1) + href.pathname : base.pathname) + (href.protocol || href.authority || href.pathname ? href.search : href.search || base.search) + href.hash;
        }
        function getDocumentUri(uri) {
          return uri.split("#")[0];
        }
        function normSchema(schema, baseUri) {
          if (schema && typeof schema === "object") {
            if (baseUri === void 0) {
              baseUri = schema.id;
            } else if (typeof schema.id === "string") {
              baseUri = resolveUrl(baseUri, schema.id);
              schema.id = baseUri;
            }
            if (Array.isArray(schema)) {
              for (var i = 0; i < schema.length; i++) {
                normSchema(schema[i], baseUri);
              }
            } else {
              if (typeof schema["$ref"] === "string") {
                schema["$ref"] = resolveUrl(baseUri, schema["$ref"]);
              }
              for (var key2 in schema) {
                if (key2 !== "enum") {
                  normSchema(schema[key2], baseUri);
                }
              }
            }
          }
        }
        function defaultErrorReporter(language) {
          language = language || "en";
          var errorMessages = languages[language];
          return function(error) {
            var messageTemplate = errorMessages[error.code] || ErrorMessagesDefault[error.code];
            if (typeof messageTemplate !== "string") {
              return "Unknown error code " + error.code + ": " + JSON.stringify(error.messageParams);
            }
            var messageParams = error.params;
            return messageTemplate.replace(/\{([^{}]*)\}/g, function(whole, varName) {
              var subValue = messageParams[varName];
              return typeof subValue === "string" || typeof subValue === "number" ? subValue : whole;
            });
          };
        }
        var ErrorCodes = {
          INVALID_TYPE: 0,
          ENUM_MISMATCH: 1,
          ANY_OF_MISSING: 10,
          ONE_OF_MISSING: 11,
          ONE_OF_MULTIPLE: 12,
          NOT_PASSED: 13,
          // Numeric errors
          NUMBER_MULTIPLE_OF: 100,
          NUMBER_MINIMUM: 101,
          NUMBER_MINIMUM_EXCLUSIVE: 102,
          NUMBER_MAXIMUM: 103,
          NUMBER_MAXIMUM_EXCLUSIVE: 104,
          NUMBER_NOT_A_NUMBER: 105,
          // String errors
          STRING_LENGTH_SHORT: 200,
          STRING_LENGTH_LONG: 201,
          STRING_PATTERN: 202,
          // Object errors
          OBJECT_PROPERTIES_MINIMUM: 300,
          OBJECT_PROPERTIES_MAXIMUM: 301,
          OBJECT_REQUIRED: 302,
          OBJECT_ADDITIONAL_PROPERTIES: 303,
          OBJECT_DEPENDENCY_KEY: 304,
          // Array errors
          ARRAY_LENGTH_SHORT: 400,
          ARRAY_LENGTH_LONG: 401,
          ARRAY_UNIQUE: 402,
          ARRAY_ADDITIONAL_ITEMS: 403,
          // Custom/user-defined errors
          FORMAT_CUSTOM: 500,
          KEYWORD_CUSTOM: 501,
          // Schema structure
          CIRCULAR_REFERENCE: 600,
          // Non-standard validation options
          UNKNOWN_PROPERTY: 1e3
        };
        var ErrorCodeLookup = {};
        for (var key in ErrorCodes) {
          ErrorCodeLookup[ErrorCodes[key]] = key;
        }
        var ErrorMessagesDefault = {
          INVALID_TYPE: "Invalid type: {type} (expected {expected})",
          ENUM_MISMATCH: "No enum match for: {value}",
          ANY_OF_MISSING: 'Data does not match any schemas from "anyOf"',
          ONE_OF_MISSING: 'Data does not match any schemas from "oneOf"',
          ONE_OF_MULTIPLE: 'Data is valid against more than one schema from "oneOf": indices {index1} and {index2}',
          NOT_PASSED: 'Data matches schema from "not"',
          // Numeric errors
          NUMBER_MULTIPLE_OF: "Value {value} is not a multiple of {multipleOf}",
          NUMBER_MINIMUM: "Value {value} is less than minimum {minimum}",
          NUMBER_MINIMUM_EXCLUSIVE: "Value {value} is equal to exclusive minimum {minimum}",
          NUMBER_MAXIMUM: "Value {value} is greater than maximum {maximum}",
          NUMBER_MAXIMUM_EXCLUSIVE: "Value {value} is equal to exclusive maximum {maximum}",
          NUMBER_NOT_A_NUMBER: "Value {value} is not a valid number",
          // String errors
          STRING_LENGTH_SHORT: "String is too short ({length} chars), minimum {minimum}",
          STRING_LENGTH_LONG: "String is too long ({length} chars), maximum {maximum}",
          STRING_PATTERN: "String does not match pattern: {pattern}",
          // Object errors
          OBJECT_PROPERTIES_MINIMUM: "Too few properties defined ({propertyCount}), minimum {minimum}",
          OBJECT_PROPERTIES_MAXIMUM: "Too many properties defined ({propertyCount}), maximum {maximum}",
          OBJECT_REQUIRED: "Missing required property: {key}",
          OBJECT_ADDITIONAL_PROPERTIES: "Additional properties not allowed",
          OBJECT_DEPENDENCY_KEY: "Dependency failed - key must exist: {missing} (due to key: {key})",
          // Array errors
          ARRAY_LENGTH_SHORT: "Array is too short ({length}), minimum {minimum}",
          ARRAY_LENGTH_LONG: "Array is too long ({length}), maximum {maximum}",
          ARRAY_UNIQUE: "Array items are not unique (indices {match1} and {match2})",
          ARRAY_ADDITIONAL_ITEMS: "Additional items not allowed",
          // Format errors
          FORMAT_CUSTOM: "Format validation failed ({message})",
          KEYWORD_CUSTOM: "Keyword failed: {key} ({message})",
          // Schema structure
          CIRCULAR_REFERENCE: "Circular $refs: {urls}",
          // Non-standard validation options
          UNKNOWN_PROPERTY: "Unknown property (not in schema)"
        };
        function ValidationError(code, params, dataPath, schemaPath, subErrors) {
          Error.call(this);
          if (code === void 0) {
            throw new Error("No error code supplied: " + schemaPath);
          }
          this.message = "";
          this.params = params;
          this.code = code;
          this.dataPath = dataPath || "";
          this.schemaPath = schemaPath || "";
          this.subErrors = subErrors || null;
          var err = new Error(this.message);
          this.stack = err.stack || err.stacktrace;
          if (!this.stack) {
            try {
              throw err;
            } catch (err2) {
              this.stack = err2.stack || err2.stacktrace;
            }
          }
        }
        ValidationError.prototype = Object.create(Error.prototype);
        ValidationError.prototype.constructor = ValidationError;
        ValidationError.prototype.name = "ValidationError";
        ValidationError.prototype.prefixWith = function(dataPrefix, schemaPrefix) {
          if (dataPrefix !== null) {
            dataPrefix = dataPrefix.replace(/~/g, "~0").replace(/\//g, "~1");
            this.dataPath = "/" + dataPrefix + this.dataPath;
          }
          if (schemaPrefix !== null) {
            schemaPrefix = schemaPrefix.replace(/~/g, "~0").replace(/\//g, "~1");
            this.schemaPath = "/" + schemaPrefix + this.schemaPath;
          }
          if (this.subErrors !== null) {
            for (var i = 0; i < this.subErrors.length; i++) {
              this.subErrors[i].prefixWith(dataPrefix, schemaPrefix);
            }
          }
          return this;
        };
        function isTrustedUrl(baseUrl, testUrl) {
          if (testUrl.substring(0, baseUrl.length) === baseUrl) {
            var remainder = testUrl.substring(baseUrl.length);
            if (testUrl.length > 0 && testUrl.charAt(baseUrl.length - 1) === "/" || remainder.charAt(0) === "#" || remainder.charAt(0) === "?") {
              return true;
            }
          }
          return false;
        }
        var languages = {};
        function createApi(language) {
          var globalContext = new ValidatorContext();
          var currentLanguage;
          var customErrorReporter;
          var api = {
            setErrorReporter: function(reporter) {
              if (typeof reporter === "string") {
                return this.language(reporter);
              }
              customErrorReporter = reporter;
              return true;
            },
            addFormat: function() {
              globalContext.addFormat.apply(globalContext, arguments);
            },
            language: function(code) {
              if (!code) {
                return currentLanguage;
              }
              if (!languages[code]) {
                code = code.split("-")[0];
              }
              if (languages[code]) {
                currentLanguage = code;
                return code;
              }
              return false;
            },
            addLanguage: function(code, messageMap) {
              var key2;
              for (key2 in ErrorCodes) {
                if (messageMap[key2] && !messageMap[ErrorCodes[key2]]) {
                  messageMap[ErrorCodes[key2]] = messageMap[key2];
                }
              }
              var rootCode = code.split("-")[0];
              if (!languages[rootCode]) {
                languages[code] = messageMap;
                languages[rootCode] = messageMap;
              } else {
                languages[code] = Object.create(languages[rootCode]);
                for (key2 in messageMap) {
                  if (typeof languages[rootCode][key2] === "undefined") {
                    languages[rootCode][key2] = messageMap[key2];
                  }
                  languages[code][key2] = messageMap[key2];
                }
              }
              return this;
            },
            freshApi: function(language2) {
              var result = createApi();
              if (language2) {
                result.language(language2);
              }
              return result;
            },
            validate: function(data, schema, checkRecursive, banUnknownProperties) {
              var def = defaultErrorReporter(currentLanguage);
              var errorReporter = customErrorReporter ? function(error2, data2, schema2) {
                return customErrorReporter(error2, data2, schema2) || def(error2, data2, schema2);
              } : def;
              var context = new ValidatorContext(globalContext, false, errorReporter, checkRecursive, banUnknownProperties);
              if (typeof schema === "string") {
                schema = { "$ref": schema };
              }
              context.addSchema("", schema);
              var error = context.validateAll(data, schema, null, null, "");
              if (!error && banUnknownProperties) {
                error = context.banUnknownProperties(data, schema);
              }
              this.error = error;
              this.missing = context.missing;
              this.valid = error === null;
              return this.valid;
            },
            validateResult: function() {
              var result = { toString: function() {
                return this.valid ? "valid" : this.error.message;
              } };
              this.validate.apply(result, arguments);
              return result;
            },
            validateMultiple: function(data, schema, checkRecursive, banUnknownProperties) {
              var def = defaultErrorReporter(currentLanguage);
              var errorReporter = customErrorReporter ? function(error, data2, schema2) {
                return customErrorReporter(error, data2, schema2) || def(error, data2, schema2);
              } : def;
              var context = new ValidatorContext(globalContext, true, errorReporter, checkRecursive, banUnknownProperties);
              if (typeof schema === "string") {
                schema = { "$ref": schema };
              }
              context.addSchema("", schema);
              context.validateAll(data, schema, null, null, "");
              if (banUnknownProperties) {
                context.banUnknownProperties(data, schema);
              }
              var result = { toString: function() {
                return this.valid ? "valid" : this.error.message;
              } };
              result.errors = context.errors;
              result.missing = context.missing;
              result.valid = result.errors.length === 0;
              return result;
            },
            addSchema: function() {
              return globalContext.addSchema.apply(globalContext, arguments);
            },
            getSchema: function() {
              return globalContext.getSchema.apply(globalContext, arguments);
            },
            getSchemaMap: function() {
              return globalContext.getSchemaMap.apply(globalContext, arguments);
            },
            getSchemaUris: function() {
              return globalContext.getSchemaUris.apply(globalContext, arguments);
            },
            getMissingUris: function() {
              return globalContext.getMissingUris.apply(globalContext, arguments);
            },
            dropSchemas: function() {
              globalContext.dropSchemas.apply(globalContext, arguments);
            },
            defineKeyword: function() {
              globalContext.defineKeyword.apply(globalContext, arguments);
            },
            defineError: function(codeName, codeNumber, defaultMessage) {
              if (typeof codeName !== "string" || !/^[A-Z]+(_[A-Z]+)*$/.test(codeName)) {
                throw new Error("Code name must be a string in UPPER_CASE_WITH_UNDERSCORES");
              }
              if (typeof codeNumber !== "number" || codeNumber % 1 !== 0 || codeNumber < 1e4) {
                throw new Error("Code number must be an integer > 10000");
              }
              if (typeof ErrorCodes[codeName] !== "undefined") {
                throw new Error("Error already defined: " + codeName + " as " + ErrorCodes[codeName]);
              }
              if (typeof ErrorCodeLookup[codeNumber] !== "undefined") {
                throw new Error("Error code already used: " + ErrorCodeLookup[codeNumber] + " as " + codeNumber);
              }
              ErrorCodes[codeName] = codeNumber;
              ErrorCodeLookup[codeNumber] = codeName;
              ErrorMessagesDefault[codeName] = ErrorMessagesDefault[codeNumber] = defaultMessage;
              for (var langCode in languages) {
                var language2 = languages[langCode];
                if (language2[codeName]) {
                  language2[codeNumber] = language2[codeNumber] || language2[codeName];
                }
              }
            },
            reset: function() {
              globalContext.reset();
              this.error = null;
              this.missing = [];
              this.valid = true;
            },
            missing: [],
            error: null,
            valid: true,
            normSchema,
            resolveUrl,
            getDocumentUri,
            errorCodes: ErrorCodes
          };
          api.language(language || "en");
          return api;
        }
        var tv4 = createApi();
        tv4.addLanguage("en-gb", ErrorMessagesDefault);
        tv4.tv4 = tv4;
        return tv4;
      });
    }
  });

  // _e6_tv4.js
  globalThis.__pm_tv4 = require_tv4();
})();
