"""Tests for additional vendor libraries in the V8 sandbox.

Covers lodash, moment, chai, tv4, ajv, xml2js, csv-parse, and the
lazy-loading detection/resolution used by ``js_runtime``.

Requires ``py_mini_racer`` — skipped when unavailable.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    response: dict | None = None,
    variables: dict | None = None,
    environment_vars: dict | None = None,
) -> dict:
    """Return a minimal ``ScriptInput``."""
    return {
        "request": {
            "url": "https://example.com",
            "method": "GET",
            "headers": {},
            "body": "",
        },
        "response": response,
        "variables": variables or {},
        "environment_vars": environment_vars or {},
        "collection_vars": {},
        "info": {"requestName": "vendor-test"},
    }


# ===================================================================
# Lodash tests
# ===================================================================


class TestLodash:
    """``require('lodash')`` must provide lodash utilities."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_lodash_map(self):
        """_.map transforms an array."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var _ = require("lodash");
pm.test("lodash map", function() {
    var result = _.map([1, 2, 3], function(n) { return n * 2; });
    pm.expect(result).to.eql([2, 4, 6]);
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_lodash_get(self):
        """_.get retrieves nested values with defaults."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var _ = require("lodash");
pm.test("lodash get", function() {
    var obj = { a: { b: { c: 42 } } };
    pm.expect(_.get(obj, "a.b.c")).to.equal(42);
    pm.expect(_.get(obj, "a.b.x", "default")).to.equal("default");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# Moment tests
# ===================================================================


class TestMoment:
    """``require('moment')`` must provide moment.js date library."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_moment_format(self):
        """moment().format() returns a formatted date string."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var moment = require("moment");
pm.test("moment format", function() {
    var year = moment().format("YYYY");
    pm.expect(parseInt(year)).to.be.above(2020);
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_moment_parse(self):
        """Moment parses and formats a date string."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var moment = require("moment");
pm.test("moment parse", function() {
    var d = moment("2024-06-15", "YYYY-MM-DD");
    pm.expect(d.format("DD/MM/YYYY")).to.equal("15/06/2024");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# Chai tests
# ===================================================================


class TestChai:
    """``require('chai')`` must provide the chai assertion library."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_chai_expect(self):
        """chai.expect assertions work inside pm.test."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var chai = require("chai");
pm.test("chai expect", function() {
    chai.expect(42).to.equal(42);
    chai.expect([1, 2]).to.have.length(2);
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_chai_assert(self):
        """chai.assert style works."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var chai = require("chai");
pm.test("chai assert", function() {
    chai.assert.isTrue(true);
    chai.assert.typeOf("hello", "string");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# tv4 tests
# ===================================================================


class TestTv4:
    """``require('tv4')`` must provide JSON Schema validation."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_tv4_validate_pass(self):
        """tv4 validates a conforming object."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var tv4 = require("tv4");
pm.test("tv4 valid", function() {
    var schema = { type: "object", properties: { name: { type: "string" } } };
    var result = tv4.validate({ name: "test" }, schema);
    pm.expect(result).to.be.true;
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_tv4_validate_fail(self):
        """tv4 rejects a non-conforming object."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var tv4 = require("tv4");
pm.test("tv4 invalid", function() {
    var schema = { type: "object", properties: { age: { type: "number" } } };
    var result = tv4.validate({ age: "not a number" }, schema);
    pm.expect(result).to.be.false;
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# Ajv tests
# ===================================================================


class TestAjv:
    """``require('ajv')`` must provide JSON Schema validation (draft-07)."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_ajv_validate_pass(self):
        """Ajv validates a conforming object."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var Ajv = require("ajv");
var ajv = new Ajv();
pm.test("ajv valid", function() {
    var schema = { type: "object", properties: { x: { type: "number" } } };
    var valid = ajv.validate(schema, { x: 1 });
    pm.expect(valid).to.be.true;
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True

    def test_ajv_validate_fail(self):
        """Ajv rejects a non-conforming object."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var Ajv = require("ajv");
var ajv = new Ajv();
pm.test("ajv invalid", function() {
    var schema = { type: "object", properties: { x: { type: "number" } },
                   required: ["x"] };
    var valid = ajv.validate(schema, {});
    pm.expect(valid).to.be.false;
    pm.expect(ajv.errors.length).to.be.above(0);
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# xml2js tests
# ===================================================================


class TestXml2js:
    """``require('xml2js')`` must parse XML strings."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_xml2js_parse(self):
        """xml2js.parseString extracts tag values."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var xml2js = require("xml2js");
xml2js.parseString("<root><name>hello</name></root>", function(err, result) {
    pm.test("xml parsed", function() {
        pm.expect(err).to.be.null;
        pm.expect(result.root.name[0]).to.equal("hello");
    });
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# csv-parse tests
# ===================================================================


class TestCsvParse:
    """``require('csv-parse/sync')`` must parse CSV strings."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_csv_parse(self):
        """csv-parse/sync parses CSV with headers."""
        from services.scripting.js_runtime import JSRuntime

        script = """
var parse = require("csv-parse/sync").parse;
pm.test("csv parsed", function() {
    var data = parse("name,age\\nAlice,30\\nBob,25", { columns: true });
    pm.expect(data).to.have.length(2);
    pm.expect(data[0].name).to.equal("Alice");
    pm.expect(data[1].age).to.equal("25");
});
"""
        result = JSRuntime.execute(script, _make_context())
        assert result["test_results"][0]["passed"] is True


# ===================================================================
# Lazy loading tests
# ===================================================================


class TestLazyLoading:
    """Vendor modules load only when required by the script."""

    @pytest.fixture(autouse=True)
    def _require_mini_racer(self) -> None:
        pytest.importorskip("py_mini_racer")

    def test_no_require_no_vendor(self):
        """A script without require() loads no vendor libraries."""
        from services.scripting.js_runtime import _detect_required_modules

        assert _detect_required_modules("pm.test('ok', function(){});") == set()

    def test_detect_single_require(self):
        """Detects a single require call."""
        from services.scripting.js_runtime import _detect_required_modules

        mods = _detect_required_modules('var _ = require("lodash");')
        assert mods == {"lodash"}

    def test_detect_multiple_requires(self):
        """Detects multiple require calls."""
        from services.scripting.js_runtime import _detect_required_modules

        script = """
var _ = require("lodash");
var moment = require('moment');
"""
        mods = _detect_required_modules(script)
        assert mods == {"lodash", "moment"}

    def test_detect_global_crypto_js(self):
        """CryptoJS global usage implies crypto-js module."""
        from services.scripting.js_runtime import _detect_required_modules

        mods = _detect_required_modules("var hash = CryptoJS.SHA256('x');")
        assert "crypto-js" in mods

    def test_resolve_with_dependencies(self):
        """csv-parse/sync resolves buffer-polyfill first."""
        from services.scripting.js_runtime import _resolve_vendor_files

        files = _resolve_vendor_files({"csv-parse/sync"})
        assert files == ["buffer-polyfill.js", "csv-parse.js"]

    def test_resolve_deduplicates(self):
        """Shared dependencies are not duplicated."""
        from services.scripting.js_runtime import _resolve_vendor_files

        files = _resolve_vendor_files({"lodash", "moment"})
        assert len(files) == len(set(files))
