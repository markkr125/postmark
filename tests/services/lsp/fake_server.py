#!/usr/bin/env python3
"""Minimal JSON-RPC LSP fake server for integration tests."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _get_path(obj: Any, dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _match(spec: dict[str, Any], req: dict[str, Any]) -> bool:
    for k, want in spec.items():
        got = _get_path(req, k)
        if got != want:
            return False
    return True


def _write_json(obj: dict[str, Any]) -> None:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()


def main() -> None:
    """Read *scenario* JSON and replay scripted LSP responses on stdin."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()
    with open(args.scenario, encoding="utf-8") as f:
        scenario = json.load(f)

    responses: list[dict[str, Any]] = scenario.get("responses", [])
    notifications: list[dict[str, Any]] = scenario.get("notifications", [])

    buf = b""
    while True:
        stdin_buf = sys.stdin.buffer
        read_chunk = getattr(stdin_buf, "read1", stdin_buf.read)
        chunk = read_chunk(4096)
        if not chunk:
            break
        buf += chunk
        while True:
            sep = buf.find(b"\r\n\r\n")
            if sep < 0:
                break
            headers = buf[:sep].decode("ascii", errors="replace")
            rest = buf[sep + 4 :]
            length = 0
            for line in headers.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1].strip())
            if len(rest) < length:
                break
            body = rest[:length]
            buf = rest[length:]
            try:
                req = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            method = str(req.get("method", ""))
            req_id = req.get("id")

            if req_id is None:
                for note in notifications:
                    aft = note.get("after") or {}
                    if aft.get("method") == method:
                        _write_json(
                            {
                                "jsonrpc": "2.0",
                                "method": note["method"],
                                "params": note.get("params") or {},
                            }
                        )
                continue

            matched: dict[str, Any] | None = None
            for resp in responses:
                mspec = resp.get("match") or {}
                if _match(mspec, req):
                    matched = resp
                    break

            if matched:
                result = matched.get("result")
                out = {"jsonrpc": "2.0", "id": req_id, "result": result}
            else:
                out = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "method not found"},
                }
            _write_json(out)

            for note in notifications:
                aft = note.get("after") or {}
                if aft.get("method") == method:
                    _write_json(
                        {
                            "jsonrpc": "2.0",
                            "method": note["method"],
                            "params": note.get("params") or {},
                        }
                    )


if __name__ == "__main__":
    main()
