"""Tests for the advanced-feature detection utility."""

from __future__ import annotations

from services.scripting.feature_detect import (
    FEATURE_ASYNC,
    FEATURE_NPM,
    detect_advanced_features,
)


class TestDetectAdvancedFeatures:
    """Test suite for detect_advanced_features()."""

    # -- Empty / non-JS inputs -----------------------------------------

    def test_empty_string_returns_empty(self) -> None:
        assert detect_advanced_features("", "javascript") == set()

    def test_whitespace_only_returns_empty(self) -> None:
        assert detect_advanced_features("   \n\t  ", "javascript") == set()

    def test_python_always_returns_empty(self) -> None:
        assert detect_advanced_features("async def foo(): await bar()", "python") == set()

    # -- Async detection -----------------------------------------------

    def test_async_function_declaration(self) -> None:
        script = "async function fetchData() { return 1; }"
        assert FEATURE_ASYNC in detect_advanced_features(script)

    def test_async_arrow_function(self) -> None:
        script = "const fn = async () => { return 1; };"
        assert FEATURE_ASYNC in detect_advanced_features(script)

    def test_async_arrow_with_param(self) -> None:
        script = "const fn = async (x) => x + 1;"
        assert FEATURE_ASYNC in detect_advanced_features(script)

    def test_await_expression(self) -> None:
        script = "const resp = await fetch('https://example.com');"
        assert FEATURE_ASYNC in detect_advanced_features(script)

    def test_no_async_in_sync_script(self) -> None:
        script = "pm.test('ok', function() { pm.expect(1).to.equal(1); });"
        assert FEATURE_ASYNC not in detect_advanced_features(script)

    def test_async_substring_not_matched(self) -> None:
        # "asyncStorage" should not trigger — the regex requires a word
        # boundary before "async".
        script = "var asyncStorage = {};"
        assert FEATURE_ASYNC not in detect_advanced_features(script)

    # -- npm detection -------------------------------------------------

    def test_require_npm(self) -> None:
        script = 'const axios = require("npm:axios");'
        assert FEATURE_NPM in detect_advanced_features(script)

    def test_require_npm_single_quotes(self) -> None:
        script = "const _ = require('npm:lodash');"
        assert FEATURE_NPM in detect_advanced_features(script)

    def test_import_from_npm(self) -> None:
        script = 'import axios from "npm:axios";'
        assert FEATURE_NPM in detect_advanced_features(script)

    def test_import_from_npm_single_quotes(self) -> None:
        script = "import _ from 'npm:lodash';"
        assert FEATURE_NPM in detect_advanced_features(script)

    def test_regular_require_not_npm(self) -> None:
        script = 'const _ = require("lodash");'
        assert FEATURE_NPM not in detect_advanced_features(script)

    # -- Combined features ---------------------------------------------

    def test_async_and_npm_together(self) -> None:
        script = """
const axios = require("npm:axios");
async function run() {
    const resp = await axios.get("https://example.com");
    pm.test("status", () => pm.expect(resp.status).to.equal(200));
}
"""
        features = detect_advanced_features(script)
        assert FEATURE_ASYNC in features
        assert FEATURE_NPM in features

    def test_normal_vendor_require_no_features(self) -> None:
        script = """
const _ = require("lodash");
const moment = require("moment");
pm.test("ok", () => {
    pm.expect(_.isArray([])).to.be.true;
});
"""
        assert detect_advanced_features(script) == set()
