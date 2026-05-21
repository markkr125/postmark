"""Tests for additional vendor libraries in the JS (Deno) script bundle.

Covers lodash, moment, chai, tv4, ajv, xml2js, csv-parse, and the
lazy-loading detection/resolution used by ``js_runtime``.  Also covers
``pm.require('npm:…'|'jsr:…')`` literal detection and the generated ESM import
block (no subprocess).

Requires **Deno** — tests skip when the runtime is unavailable.
"""

from __future__ import annotations

import pytest

from services.scripting import ScriptInput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    response: dict | None = None,
    variables: dict | None = None,
    environment_vars: dict | None = None,
) -> ScriptInput:
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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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
        from services.scripting.runtime_settings import RuntimeSettings

        st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
        if not st.get("available"):
            import pytest

            pytest.skip("Deno not available")

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


# ===================================================================
# pm.require (npm:/jsr:) — static detection + bundle preamble
# ===================================================================


class TestPmRequireDetector:
    """``_detect_pm_require_specs`` — string-literal ``pm.require`` calls only."""

    def test_empty_script(self) -> None:
        """No calls yields an empty list."""
        from services.scripting.js_runtime import _detect_pm_require_specs

        assert _detect_pm_require_specs("") == []
        assert _detect_pm_require_specs("console.log(1);") == []

    def test_single_npm_exact_version(self) -> None:
        """Parses npm name and exact semver."""
        from services.scripting.js_runtime import PmRequireSpec, _detect_pm_require_specs

        specs = _detect_pm_require_specs("const _ = pm.require('npm:lodash@4.17.21');")
        assert specs == [PmRequireSpec("npm", "lodash", "4.17.21")]

    def test_double_quoted_literal(self) -> None:
        """Double-quoted string literals are recognised."""
        from services.scripting.js_runtime import PmRequireSpec, _detect_pm_require_specs

        specs = _detect_pm_require_specs('pm.require("npm:lodash@4.17.21");')
        assert specs == [PmRequireSpec("npm", "lodash", "4.17.21")]

    def test_deduplicates_identical_calls(self) -> None:
        """Duplicate literals collapse to one spec."""
        from services.scripting.js_runtime import PmRequireSpec, _detect_pm_require_specs

        script = """
pm.require('npm:lodash@4.17.21');
pm.require("npm:lodash@4.17.21");
"""
        assert _detect_pm_require_specs(script) == [PmRequireSpec("npm", "lodash", "4.17.21")]

    def test_scoped_npm_package(self) -> None:
        """Scoped npm names are allowed."""
        from services.scripting.js_runtime import PmRequireSpec, _detect_pm_require_specs

        specs = _detect_pm_require_specs("pm.require('npm:@types/node@20.1.0');")
        assert specs == [PmRequireSpec("npm", "@types/node", "20.1.0")]

    def test_jsr_registry(self) -> None:
        """jsr: prefix is accepted."""
        from services.scripting.js_runtime import PmRequireSpec, _detect_pm_require_specs

        specs = _detect_pm_require_specs("pm.require('jsr:@std/assert@1.0.0');")
        assert specs == [PmRequireSpec("jsr", "@std/assert", "1.0.0")]

    def test_unversioned_specifier(self) -> None:
        """Omitted @version yields empty version string."""
        from services.scripting.js_runtime import PmRequireSpec, _detect_pm_require_specs

        specs = _detect_pm_require_specs("pm.require('npm:lodash');")
        assert specs == [PmRequireSpec("npm", "lodash", "")]

    def test_invalid_package_name_raises(self) -> None:
        """Names that fail npm/jsr naming rules raise ``ValueError``."""
        from services.scripting.js_runtime import _detect_pm_require_specs

        with pytest.raises(ValueError, match="invalid"):
            _detect_pm_require_specs("pm.require('npm:_bad@1.0.0');")

    def test_version_range_not_allowed(self) -> None:
        """Caret/range versions are rejected."""
        from services.scripting.js_runtime import _detect_pm_require_specs

        with pytest.raises(ValueError, match="exact"):
            _detect_pm_require_specs("pm.require('npm:lodash@^4.17.21');")


class TestPmRequireImportsBlock:
    """``_pm_require_imports_block`` output shape."""

    def test_empty_list_returns_empty_string(self) -> None:
        """No specs → no preamble."""
        from services.scripting.js_runtime import _pm_require_imports_block

        assert _pm_require_imports_block([]) == ""

    def test_emits_static_import_and_registry(self) -> None:
        """Import line plus ``globalThis.__pm_require_modules`` map."""
        from services.scripting.js_runtime import PmRequireSpec, _pm_require_imports_block

        out = _pm_require_imports_block([PmRequireSpec("npm", "lodash", "4.17.21")])
        assert 'from "npm:lodash@4.17.21"' in out
        assert "import * as __pm_req_" in out
        assert "globalThis.__pm_require_modules" in out
        assert '"npm:lodash":' in out


class TestPmRequireBundleText:
    """``deno_runtime._build_bundle_text`` includes pm.require preamble."""

    def test_bundle_contains_pm_require_import(self) -> None:
        """Bundling injects ESM import before vendor polyfills."""
        from services.scripting.deno_runtime import _build_bundle_text

        ctx = _make_context()
        script = "pm.require('npm:lodash@4.17.21');"
        bundle, _needs_net, _local = _build_bundle_text(script, ctx)
        assert 'from "npm:lodash@4.17.21"' in bundle
        assert "__pm_require_modules" in bundle

    def test_invalid_pm_require_surfaces_as_runtime_error_string(self) -> None:
        """``ValueError`` from detection is wrapped for callers."""
        from services.scripting.deno_runtime import _build_bundle_text

        ctx = _make_context()
        with pytest.raises(RuntimeError, match="Script bundling failed"):
            _build_bundle_text("pm.require('npm:lodash@^1');", ctx)
