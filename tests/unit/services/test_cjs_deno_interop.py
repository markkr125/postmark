"""Gate 0: Deno CJS interop — namespace shape for ``import *`` from ``.cjs``."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from services.scripting.runtime_settings import RuntimeSettings


def _deno_runtime_available() -> bool:
    """Return True when a valid Deno binary is available."""
    st = RuntimeSettings.validate_deno(RuntimeSettings.deno_path())
    return bool(st.get("available"))


@pytest.mark.skipif(
    not _deno_runtime_available(),
    reason="Deno not available for CJS interop smoke test",
)
def test_cjs_namespace_shapes_for_pm_require_registration() -> None:
    """``module.exports`` and ``exports.foo`` both expose destructurable keys."""
    deno = RuntimeSettings.deno_path()
    assert deno
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "helper1.cjs").write_text("module.exports = { v: 1 };", encoding="utf-8")
        (root / "helper2.cjs").write_text("exports.foo = 2;", encoding="utf-8")
        main = root / "main.js"
        main.write_text(
            "import * as m1 from './helper1.cjs';\n"
            "import * as m2 from './helper2.cjs';\n"
            "console.log(JSON.stringify({"
            "m1: { default: m1.default, v: m1.v, keys: Object.keys(m1) }, "
            "m2: { default: m2.default, foo: m2.foo, keys: Object.keys(m2) }"
            "}));",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [deno, "run", str(main)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload["m1"]["v"] == 1
        assert payload["m1"]["default"] == {"v": 1}
        assert payload["m2"]["foo"] == 2
        assert payload["m2"]["default"] == {"foo": 2}
