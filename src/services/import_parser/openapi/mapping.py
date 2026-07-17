"""Map OpenAPI / Swagger documents to Postmark ``ParsedCollection`` trees."""

from __future__ import annotations

import json
import re
from typing import Any

from services.import_parser.models import ParsedCollection, ParsedFolder, ParsedRequest

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
_PATH_PARAM_RE = re.compile(r"\{([^}/]+)\}")


def build_collection_from_openapi(
    data: dict[str, Any],
    warnings: list[str],
) -> ParsedCollection:
    """Build one collection from an OpenAPI 3 or Swagger 2 document."""
    raw_info = data.get("info")
    info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
    name = str(info.get("title") or "OpenAPI Import").strip() or "OpenAPI Import"
    description = info.get("description")
    if description is not None:
        description = str(description)

    base_url, variables = _base_url_and_variables(data)
    auth = _collection_auth(data, warnings)
    folders = _operations_by_tag(data, base_url, warnings)

    items: list[ParsedFolder | ParsedRequest] = list(folders)
    return ParsedCollection(
        name=name,
        description=description,
        variables=variables or None,
        auth=auth,
        items=items,
    )


def _base_url_and_variables(
    data: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Resolve base URL and collection variables (``baseUrl``)."""
    variables: list[dict[str, Any]] = []
    if "openapi" in data:
        servers = data.get("servers")
        if isinstance(servers, list) and servers:
            first_raw = servers[0]
            first: dict[str, Any] = first_raw if isinstance(first_raw, dict) else {}
            url = str(first.get("url") or "").rstrip("/")
            vars_raw = first.get("variables")
            server_vars: dict[str, Any] = vars_raw if isinstance(vars_raw, dict) else {}
            for key, meta in server_vars.items():
                default = ""
                if isinstance(meta, dict):
                    default = str(meta.get("default") or "")
                url = url.replace("{" + str(key) + "}", default)
                variables.append(
                    {
                        "key": str(key),
                        "value": default,
                        "enabled": True,
                        "type": "default",
                    }
                )
            if url:
                variables.insert(
                    0,
                    {
                        "key": "baseUrl",
                        "value": url,
                        "enabled": True,
                        "type": "default",
                    },
                )
                return "{{baseUrl}}", variables
        return "", variables

    # Swagger 2
    host = str(data.get("host") or "").strip()
    base_path = str(data.get("basePath") or "").rstrip("/")
    schemes = data.get("schemes")
    scheme = "https"
    if isinstance(schemes, list) and schemes:
        scheme = str(schemes[0] or "https")
    if host:
        url = f"{scheme}://{host}{base_path}"
        variables.append(
            {
                "key": "baseUrl",
                "value": url,
                "enabled": True,
                "type": "default",
            }
        )
        return "{{baseUrl}}", variables
    return base_path, variables


def _resolve_ref(
    doc: dict[str, Any],
    node: Any,
    warnings: list[str],
    *,
    depth: int = 0,
) -> Any:
    """Resolve local ``#/…`` refs; leave external refs with a warning."""
    if depth > 32 or not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref:
        return node
    if not ref.startswith("#/"):
        warnings.append(f"Skipped external $ref: {ref}")
        return node
    cur: Any = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(cur, dict) or part not in cur:
            warnings.append(f"Unresolved $ref: {ref}")
            return node
        cur = cur[part]
    if isinstance(cur, dict) and "$ref" in cur:
        return _resolve_ref(doc, cur, warnings, depth=depth + 1)
    return cur


def _operations_by_tag(
    data: dict[str, Any],
    base_url: str,
    warnings: list[str],
) -> list[ParsedFolder]:
    """Group path operations into tag folders (untagged → Default)."""
    paths = data.get("paths")
    if not isinstance(paths, dict):
        return []

    by_tag: dict[str, list[ParsedRequest]] = {}
    for path, path_item in paths.items():
        path_item = _resolve_ref(data, path_item, warnings)
        if not isinstance(path_item, dict):
            continue
        path_params = path_item.get("parameters")
        shared_params = path_params if isinstance(path_params, list) else []
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            operation = _resolve_ref(data, operation, warnings)
            if not isinstance(operation, dict):
                continue
            req = _build_request(
                data,
                path=str(path),
                method=method.upper(),
                operation=operation,
                shared_params=shared_params,
                base_url=base_url,
                warnings=warnings,
            )
            tags = operation.get("tags")
            tag_name = "Default"
            if isinstance(tags, list) and tags:
                tag_name = str(tags[0] or "Default").strip() or "Default"
            by_tag.setdefault(tag_name, []).append(req)

    folders: list[ParsedFolder] = []
    for tag in sorted(by_tag.keys(), key=lambda t: (t == "Default", t.lower())):
        folders.append(
            ParsedFolder(
                type="folder",
                name=tag,
                description=None,
                auth=None,
                events=None,
                children=list(by_tag[tag]),
            )
        )
    return folders


def _build_request(
    doc: dict[str, Any],
    *,
    path: str,
    method: str,
    operation: dict[str, Any],
    shared_params: list[Any],
    base_url: str,
    warnings: list[str],
) -> ParsedRequest:
    """Build one ``ParsedRequest`` from an operation object."""
    name = (
        str(operation.get("summary") or "").strip()
        or str(operation.get("operationId") or "").strip()
        or f"{method} {path}"
    )
    description = operation.get("description")
    if description is not None:
        description = str(description)

    params = list(shared_params)
    op_params = operation.get("parameters")
    if isinstance(op_params, list):
        params.extend(op_params)

    url_path = path
    query: list[dict[str, Any]] = []
    headers: list[dict[str, Any]] = []
    for raw in params:
        param = _resolve_ref(doc, raw, warnings)
        if not isinstance(param, dict):
            continue
        where = str(param.get("in") or "")
        key = str(param.get("name") or "")
        if not key:
            continue
        example = _param_example(param)
        enabled = bool(param.get("required", False)) or example not in ("", None)
        if where == "path":
            url_path = url_path.replace("{" + key + "}", "{{" + key + "}}")
        elif where == "query":
            query.append(
                {
                    "key": key,
                    "value": "" if example is None else str(example),
                    "enabled": enabled,
                    "type": "text",
                }
            )
        elif where == "header":
            headers.append(
                {
                    "key": key,
                    "value": "" if example is None else str(example),
                    "enabled": True,
                    "type": "text",
                }
            )

    # Unreplaced path params → {{name}}
    url_path = _PATH_PARAM_RE.sub(lambda m: "{{" + m.group(1) + "}}", url_path)
    url = f"{base_url}{url_path}" if base_url else url_path

    body, body_mode = _request_body(doc, operation, warnings)
    if (
        body
        and body_mode == "raw"
        and not any(str(h.get("key", "")).lower() == "content-type" for h in headers)
    ):
        headers.append(
            {
                "key": "Content-Type",
                "value": "application/json",
                "enabled": True,
                "type": "text",
            }
        )

    return ParsedRequest(
        type="request",
        name=name,
        method=method,
        url=url,
        headers=headers or None,
        request_parameters=query or None,
        body=body,
        body_mode=body_mode,
        description=description,
    )


def _param_example(param: dict[str, Any]) -> Any:
    """Pick an example value for a parameter object."""
    if "example" in param:
        return param.get("example")
    schema = param.get("schema")
    if isinstance(schema, dict):
        if "example" in schema:
            return schema.get("example")
        if "default" in schema:
            return schema.get("default")
        return _schema_stub(schema)
    return param.get("default")


def _request_body(
    doc: dict[str, Any],
    operation: dict[str, Any],
    warnings: list[str],
) -> tuple[str | None, str | None]:
    """Extract body string and body_mode from OpenAPI 3 or Swagger 2."""
    # OpenAPI 3
    body = operation.get("requestBody")
    body = _resolve_ref(doc, body, warnings) if isinstance(body, dict) else body
    if isinstance(body, dict):
        content = body.get("content")
        if isinstance(content, dict):
            for mime in (
                "application/json",
                "application/xml",
                "text/plain",
                "application/x-www-form-urlencoded",
            ):
                media = content.get(mime)
                if not isinstance(media, dict):
                    continue
                example = _media_example(doc, media, warnings)
                if example is None:
                    continue
                if mime == "application/json":
                    if not isinstance(example, str):
                        example = json.dumps(example, indent=2)
                    return str(example), "raw"
                if mime == "application/x-www-form-urlencoded":
                    return str(example), "urlencoded"
                return str(example), "raw"

    # Swagger 2 body parameter
    params = operation.get("parameters")
    if isinstance(params, list):
        for raw in params:
            param = _resolve_ref(doc, raw, warnings)
            if not isinstance(param, dict) or param.get("in") != "body":
                continue
            schema = param.get("schema")
            schema = _resolve_ref(doc, schema, warnings) if isinstance(schema, dict) else schema
            stub = _schema_stub(schema) if isinstance(schema, dict) else {}
            if param.get("example") is not None:
                stub = param.get("example")
            return json.dumps(stub, indent=2), "raw"
    return None, None


def _media_example(
    doc: dict[str, Any],
    media: dict[str, Any],
    warnings: list[str],
) -> Any:
    """Return example payload for a media type object."""
    if "example" in media:
        return media.get("example")
    examples = media.get("examples")
    if isinstance(examples, dict):
        for ex in examples.values():
            ex = _resolve_ref(doc, ex, warnings) if isinstance(ex, dict) else ex
            if isinstance(ex, dict) and "value" in ex:
                return ex.get("value")
    schema = media.get("schema")
    schema = _resolve_ref(doc, schema, warnings) if isinstance(schema, dict) else schema
    if isinstance(schema, dict):
        if "example" in schema:
            return schema.get("example")
        return _schema_stub(schema)
    return None


def _schema_stub(schema: dict[str, Any], *, depth: int = 0) -> Any:
    """Build a shallow example object from a JSON Schema subset."""
    if depth > 6:
        return None
    if "example" in schema:
        return schema.get("example")
    if "default" in schema:
        return schema.get("default")
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties")
        if not isinstance(props, dict):
            return {}
        out: dict[str, Any] = {}
        for key, prop in list(props.items())[:20]:
            if isinstance(prop, dict):
                out[str(key)] = _schema_stub(prop, depth=depth + 1)
        return out
    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return [_schema_stub(items, depth=depth + 1)]
        return []
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return False
    if schema_type == "string":
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        return "string"
    return None


def _collection_auth(
    data: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any] | None:
    """Map the first security scheme to Postmark auth with placeholders."""
    schemes: dict[str, Any] = {}
    if "openapi" in data:
        components = data.get("components")
        if isinstance(components, dict) and isinstance(components.get("securitySchemes"), dict):
            schemes = components["securitySchemes"]
    else:
        if isinstance(data.get("securityDefinitions"), dict):
            schemes = data["securityDefinitions"]

    if not schemes:
        return None

    security = data.get("security")
    preferred: str | None = None
    if isinstance(security, list) and security:
        first = security[0]
        if isinstance(first, dict) and first:
            preferred = str(next(iter(first.keys())))

    name = preferred if preferred in schemes else next(iter(schemes.keys()))
    scheme = _resolve_ref(data, schemes.get(name), warnings)
    if not isinstance(scheme, dict):
        return None

    stype = str(scheme.get("type") or "").lower()
    if stype == "apiKey" or stype == "apikey":
        key_name = str(scheme.get("name") or "X-Api-Key")
        location = str(scheme.get("in") or "header")
        return {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": key_name, "type": "string"},
                {"key": "value", "value": "{{apiKey}}", "type": "string"},
                {"key": "in", "value": location, "type": "string"},
            ],
        }
    if stype == "http":
        http_scheme = str(scheme.get("scheme") or "").lower()
        if http_scheme == "bearer":
            return {
                "type": "bearer",
                "bearer": [{"key": "token", "value": "{{bearerToken}}", "type": "string"}],
            }
        if http_scheme == "basic":
            return {
                "type": "basic",
                "basic": [
                    {"key": "username", "value": "{{username}}", "type": "string"},
                    {"key": "password", "value": "{{password}}", "type": "string"},
                ],
            }
    if stype == "basic":
        return {
            "type": "basic",
            "basic": [
                {"key": "username", "value": "{{username}}", "type": "string"},
                {"key": "password", "value": "{{password}}", "type": "string"},
            ],
        }
    if stype == "oauth2":
        return {
            "type": "oauth2",
            "oauth2": [
                {"key": "accessToken", "value": "{{oauth_access_token}}", "type": "string"},
                {"key": "headerPrefix", "value": "Bearer", "type": "string"},
                {"key": "addTokenTo", "value": "header", "type": "string"},
            ],
        }
    warnings.append(f"Unsupported security scheme type for collection auth: {stype!r}")
    return None
