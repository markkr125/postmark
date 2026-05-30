"""Postman-style dynamic variable resolution for host substitution and RP runtime."""

from __future__ import annotations

import json
import os
import random
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "scripts"
_DYNVAR_PATH = _SCRIPTS_DIR / "dynamic_variables.json"

_data: dict[str, Any] | None = None


def dynvar_json_for_subprocess() -> str:
    """Serialized rules for sandbox children (avoids opening the JSON file there)."""
    return json.dumps(_load_data())


def _load_data() -> dict[str, Any]:
    global _data
    if _data is None:
        embedded = os.environ.get("PM_DYNVAR_JSON")
        if embedded:
            _data = json.loads(embedded)
        else:
            _data = json.loads(_DYNVAR_PATH.read_text(encoding="utf-8"))
    return _data


def _normalize_name(name: str) -> str:
    n = name.strip()
    if not n.startswith("$"):
        n = f"${n}"
    return n


def _pick(pool: str, pools: dict[str, list[str]]) -> str:
    items = pools.get(pool, [])
    if not items:
        return ""
    return random.choice(items)


def _apply_rule(rule: dict[str, Any], pools: dict[str, list[str]]) -> str:
    kind = rule.get("rule", "")
    if kind == "uuid":
        return str(uuid.uuid4())
    if kind == "unixTime":
        return str(int(datetime.now(UTC).timestamp()))
    if kind == "isoTime":
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if kind == "intRange":
        lo = int(rule.get("min", 0))
        hi = int(rule.get("max", 1000))
        return str(secrets.randbelow(hi - lo + 1) + lo)
    if kind == "floatRange":
        lo_f = float(rule.get("min", 0))
        hi_f = float(rule.get("max", 1))
        dec = int(rule.get("decimals", 2))
        val = lo_f + (hi_f - lo_f) * random.random()
        return f"{val:.{dec}f}"
    if kind == "boolean":
        return secrets.choice(["true", "false"])
    if kind == "pick":
        return _pick(str(rule.get("pool", "")), pools)
    if kind == "picks":
        pool = str(rule.get("pool", ""))
        mn = int(rule.get("min", 1))
        mx = int(rule.get("max", mn))
        count = secrets.randbelow(mx - mn + 1) + mn
        return " ".join(_pick(pool, pools) for _ in range(count))
    if kind == "template":
        parts_out: list[str] = []
        for part in rule.get("parts", []):
            if isinstance(part, str):
                parts_out.append(part)
            elif isinstance(part, dict) and "pool" in part:
                parts_out.append(_pick(str(part["pool"]), pools))
        return "".join(parts_out)
    if kind == "hexColor":
        return f"#{secrets.token_hex(3)}"
    if kind == "ipv4":
        return ".".join(str(secrets.randbelow(256)) for _ in range(4))
    if kind == "ipv6":
        return ":".join(secrets.token_hex(2) for _ in range(8))
    if kind == "mac":
        return ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6))
    if kind == "alphaNumeric":
        return secrets.choice(string.ascii_lowercase + string.digits)
    if kind == "password":
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        return "".join(secrets.choice(alphabet) for _ in range(16))
    if kind == "semver":
        return f"{secrets.randbelow(10)}.{secrets.randbelow(20)}.{secrets.randbelow(100)}"
    if kind == "phone":
        return f"+1{secrets.randbelow(9000000000) + 1000000000:010d}"
    if kind == "phoneExt":
        return (
            f"+1{secrets.randbelow(9000000000) + 1000000000:010d} x{secrets.randbelow(9000) + 1000}"
        )
    if kind == "streetAddress":
        return f"{secrets.randbelow(9999) + 1} {_pick('streets', pools)}"
    if kind == "latitude":
        return f"{(random.random() * 180 - 90):.6f}"
    if kind == "longitude":
        return f"{(random.random() * 360 - 180):.6f}"
    if kind == "imageUrl":
        cat = str(rule.get("pool", "abstract"))
        return f"https://picsum.photos/seed/{secrets.token_hex(8)}/400/300?{cat}"
    if kind == "imageDataUri":
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    if kind == "bankAccount":
        return "".join(str(secrets.randbelow(10)) for _ in range(10))
    if kind == "creditCardMask":
        return f"****-****-****-{secrets.randbelow(9000) + 1000:04d}"
    if kind == "bic":
        return "".join(secrets.choice(string.ascii_uppercase) for _ in range(8)) + "XX"
    if kind == "iban":
        return "GB" + "".join(str(secrets.randbelow(10)) for _ in range(20))
    if kind == "bitcoin":
        return "bc1" + secrets.token_hex(16)
    if kind == "companyName":
        return f"{_pick('lastNames', pools)} {_pick('companySuffixes', pools)}"
    if kind == "dateFuture":
        d = datetime.now(UTC) + timedelta(days=secrets.randbelow(365) + 1)
        return d.strftime("%Y-%m-%d")
    if kind == "datePast":
        d = datetime.now(UTC) - timedelta(days=secrets.randbelow(3650) + 1)
        return d.strftime("%Y-%m-%d")
    if kind == "dateRecent":
        d = datetime.now(UTC) - timedelta(days=secrets.randbelow(30))
        return d.strftime("%Y-%m-%d")
    if kind == "domainName":
        return f"{_pick('words', pools)}.{_pick('domains', pools)}"
    if kind == "exampleEmail":
        return f"user{secrets.randbelow(99999)}@example.com"
    if kind == "userName":
        return f"{_pick('firstNames', pools).lower()}{secrets.randbelow(999)}"
    if kind == "url":
        return f"https://{_pick('words', pools)}.{_pick('domains', pools)}"
    if kind == "fileName":
        return f"file_{secrets.token_hex(4)}.{_pick('fileExts', pools)}"
    if kind == "filePath":
        return f"/tmp/{_pick('words', pools)}.{_pick('fileExts', pools)}"
    if kind == "directoryPath":
        return f"/var/data/{_pick('words', pools)}"
    if kind == "price":
        return f"{secrets.randbelow(10000) / 100:.2f}"
    if kind == "ingVerb":
        v = _pick("hackerVerbs", pools)
        return v + "ing" if not v.endswith("ing") else v
    if kind == "loremSentence":
        return (
            " ".join(
                _pick("loremWords", pools) for _ in range(secrets.randbelow(8) + 3)
            ).capitalize()
            + "."
        )
    if kind == "loremSentences":
        return " ".join(
            " ".join(_pick("loremWords", pools) for _ in range(5)).capitalize() + "."
            for _ in range(secrets.randbelow(3) + 1)
        )
    if kind == "loremParagraph":
        return _apply_rule({"rule": "loremSentences"}, pools)
    if kind == "loremParagraphs":
        return "\n\n".join(_apply_rule({"rule": "loremParagraph"}, pools) for _ in range(2))
    if kind == "loremText":
        return _apply_rule({"rule": "loremParagraphs"}, pools)
    if kind == "loremSlug":
        return "-".join(_pick("loremWords", pools) for _ in range(3))
    if kind == "loremLines":
        return "\n".join(_apply_rule({"rule": "loremSentence"}, pools) for _ in range(3))
    if kind == "hackerAbbr":
        return "".join(c[0].upper() for c in _pick("hackerAdj", pools).split()[:3]) or "IO"
    if kind == "hackerPhrase":
        return f"If we {_pick('hackerVerbs', pools)} the {_pick('hackerNouns', pools)}, we can get to the {_pick('hackerNouns', pools)} through the {_pick('hackerAdj', pools)} {_pick('hackerNouns', pools)}."
    return ""


def resolve(name: str) -> str | None:
    """Return a generated value for a ``$...`` dynamic-variable name, or None if unknown."""
    key = _normalize_name(name)
    data = _load_data()
    pools = data.get("pools", {})
    vars_map = data.get("vars", {})
    rule = vars_map.get(key)
    if not rule:
        return None
    return _apply_rule(rule, pools)
