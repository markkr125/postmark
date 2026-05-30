"""Safe builtins and stdlib shims for RestrictedPython execution."""

from __future__ import annotations

import hmac
import json
import math
import re
import uuid
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from hashlib import md5, sha256
from typing import Any
from urllib.parse import quote, urlencode


def _safe_type(obj: object) -> type:
    """Single-argument ``type()`` — blocks metaclass creation via 3-arg form."""
    return type(obj)


# fmt: off
_SAFE_BUILTINS: dict[str, Any] = {
    "True": True, "False": False, "None": None,
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "isinstance": isinstance, "len": len, "list": list, "map": map,
    "max": max, "min": min, "range": range, "reversed": reversed,
    "round": round, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "type": _safe_type, "zip": zip,
    # Common exception types so user scripts can ``try/except`` (Postman parity).
    "Exception": Exception, "ValueError": ValueError, "RuntimeError": RuntimeError,
    "KeyError": KeyError, "TypeError": TypeError, "IndexError": IndexError,
    "AssertionError": AssertionError, "AttributeError": AttributeError,
}
# fmt: on

# fmt: off
_SAFE_STDLIB: dict[str, Any] = {
    "json_loads": json.loads, "json_dumps": json.dumps,
    "re_match": re.match, "re_search": re.search,
    "re_findall": re.findall, "re_sub": re.sub,
    "re_compile": re.compile,
    "math_ceil": math.ceil, "math_floor": math.floor,
    "math_sqrt": math.sqrt, "math_pow": math.pow, "math_log": math.log,
    "math_pi": math.pi, "math_e": math.e,
    "b64encode": b64encode, "b64decode": b64decode,
    "hashlib_md5": lambda d: md5(d.encode() if isinstance(d, str) else d).hexdigest(),
    "hashlib_sha256": lambda d: sha256(d.encode() if isinstance(d, str) else d).hexdigest(),
    "hashlib_hmac_sha256": lambda d, k: hmac.new(
        k.encode() if isinstance(k, str) else k,
        d.encode() if isinstance(d, str) else d,
        "sha256",
    ).hexdigest(),
    "uuid_v4": lambda: str(uuid.uuid4()),
    "datetime_now": lambda: datetime.now(tz=UTC).isoformat(),
    "datetime_utcnow": lambda: datetime.now(tz=UTC).isoformat(),
    "url_quote": quote, "url_urlencode": urlencode,
}
# fmt: on
