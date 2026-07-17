"""Detect and parse WSDL 1.1 documents into Postmark collections."""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree

from services.import_parser.models import (
    ImportResult,
    ParsedCollection,
    ParsedFolder,
    ParsedRequest,
)
from services.import_parser.wsdl.soap import (
    NSMAP,
    build_soap_envelope,
    local_name,
    soap_content_type,
)

logger = logging.getLogger(__name__)


def detect_wsdl_text(text: str) -> bool:
    """Return True when *text* looks like a WSDL 1.1 definitions document."""
    stripped = text.lstrip()
    if not stripped.startswith("<"):
        return False
    lower = stripped[:500].lower()
    return "definitions" in lower and ("wsdl" in lower or "schemas.xmlsoap.org/wsdl" in lower)


def load_wsdl_text(text: str) -> ImportResult | None:
    """Parse *text* as WSDL when detected; else return None."""
    if not detect_wsdl_text(text):
        return None
    return parse_wsdl_document(text)


def parse_wsdl_document(text: str) -> ImportResult:
    """Parse a WSDL 1.1 XML string into an :class:`ImportResult`."""
    warnings: list[str] = []
    try:
        root = etree.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except etree.XMLSyntaxError as exc:
        return ImportResult(
            collections=[],
            environments=[],
            errors=[f"Invalid WSDL XML: {exc}"],
        )

    if local_name(root.tag).lower() != "definitions":
        return ImportResult(
            collections=[],
            environments=[],
            errors=["Not a WSDL definitions document"],
        )

    # Remote XSD/WSDL imports are out of scope for v1.
    for imp in root.xpath(".//wsdl:import | .//xsd:import", namespaces=NSMAP):
        loc = imp.get("location") or imp.get("schemaLocation")
        if loc and str(loc).startswith(("http://", "https://")):
            warnings.append(f"Skipped remote import: {loc}")

    target_ns = root.get("targetNamespace")
    name = root.get("name") or _first_service_name(root) or "WSDL Import"

    messages = _index_messages(root)
    port_types = _index_port_types(root)
    bindings = _index_bindings(root)
    folders = _services_to_folders(
        root,
        messages=messages,
        port_types=port_types,
        bindings=bindings,
        target_ns=target_ns,
        warnings=warnings,
    )

    if not folders:
        # Binding-only docs: still emit operations under Default.
        folders = _bindings_fallback(
            bindings,
            messages=messages,
            port_types=port_types,
            target_ns=target_ns,
            warnings=warnings,
        )

    collection = ParsedCollection(
        name=str(name),
        description=None,
        items=list(folders),
    )
    return ImportResult(collections=[collection], environments=[], errors=list(warnings))


def _first_service_name(root: etree._Element) -> str | None:
    """Return the first wsdl:service name, if any."""
    services = root.xpath("./wsdl:service", namespaces=NSMAP)
    if services:
        name = services[0].get("name")
        return str(name) if name else None
    return None


def _index_messages(root: etree._Element) -> dict[str, list[dict[str, str]]]:
    """Map message name → list of parts ``{name, element, type}``."""
    out: dict[str, list[dict[str, str]]] = {}
    for msg in root.xpath("./wsdl:message", namespaces=NSMAP):
        name = msg.get("name")
        if not name:
            continue
        parts: list[dict[str, str]] = []
        for part in msg.xpath("./wsdl:part", namespaces=NSMAP):
            parts.append(
                {
                    "name": str(part.get("name") or "part"),
                    "element": str(part.get("element") or ""),
                    "type": str(part.get("type") or ""),
                }
            )
        out[name] = parts
    return out


def _index_port_types(root: etree._Element) -> dict[str, dict[str, dict[str, str]]]:
    """Map portType → operation → {input, output} message qnames."""
    out: dict[str, dict[str, dict[str, str]]] = {}
    for pt in root.xpath("./wsdl:portType", namespaces=NSMAP):
        pt_name = pt.get("name")
        if not pt_name:
            continue
        ops: dict[str, dict[str, str]] = {}
        for op in pt.xpath("./wsdl:operation", namespaces=NSMAP):
            op_name = op.get("name")
            if not op_name:
                continue
            inp = op.find("wsdl:input", namespaces=NSMAP)
            outp = op.find("wsdl:output", namespaces=NSMAP)
            ops[op_name] = {
                "input": _strip_prefix(inp.get("message") if inp is not None else ""),
                "output": _strip_prefix(outp.get("message") if outp is not None else ""),
            }
        out[pt_name] = ops
    return out


def _index_bindings(root: etree._Element) -> dict[str, dict[str, Any]]:
    """Map binding name → {type, operations: {name: soap_action}}."""
    out: dict[str, dict[str, Any]] = {}
    for binding in root.xpath("./wsdl:binding", namespaces=NSMAP):
        b_name = binding.get("name")
        if not b_name:
            continue
        soap_binding = binding.find("soap:binding", namespaces=NSMAP)
        if soap_binding is None:
            # Not a SOAP binding — skip for v1.
            continue
        type_ref = _strip_prefix(binding.get("type") or "")
        ops: dict[str, str] = {}
        for op in binding.xpath("./wsdl:operation", namespaces=NSMAP):
            op_name = op.get("name")
            if not op_name:
                continue
            soap_op = op.find("soap:operation", namespaces=NSMAP)
            action = soap_op.get("soapAction") if soap_op is not None else ""
            ops[op_name] = str(action or "")
        out[b_name] = {"type": type_ref, "operations": ops}
    return out


def _services_to_folders(
    root: etree._Element,
    *,
    messages: dict[str, list[dict[str, str]]],
    port_types: dict[str, dict[str, dict[str, str]]],
    bindings: dict[str, dict[str, Any]],
    target_ns: str | None,
    warnings: list[str],
) -> list[ParsedFolder]:
    """Build folders from wsdl:service / port / binding operations."""
    folders: list[ParsedFolder] = []
    for service in root.xpath("./wsdl:service", namespaces=NSMAP):
        service_name = service.get("name") or "Service"
        children: list[ParsedFolder | ParsedRequest] = []
        for port in service.xpath("./wsdl:port", namespaces=NSMAP):
            address = port.find("soap:address", namespaces=NSMAP)
            location = address.get("location") if address is not None else ""
            binding_ref = _strip_prefix(port.get("binding") or "")
            binding = bindings.get(binding_ref)
            if binding is None:
                warnings.append(f"Unknown or non-SOAP binding: {binding_ref}")
                continue
            pt_name = str(binding.get("type") or "")
            pt_ops = port_types.get(pt_name, {})
            for op_name, soap_action in binding.get("operations", {}).items():
                children.append(
                    _make_request(
                        op_name=str(op_name),
                        location=str(location or ""),
                        soap_action=str(soap_action or ""),
                        input_message=pt_ops.get(str(op_name), {}).get("input", ""),
                        messages=messages,
                        target_ns=target_ns,
                    )
                )
        if children:
            folders.append(
                ParsedFolder(
                    type="folder",
                    name=str(service_name),
                    description=None,
                    auth=None,
                    events=None,
                    children=children,
                )
            )
    return folders


def _bindings_fallback(
    bindings: dict[str, dict[str, Any]],
    *,
    messages: dict[str, list[dict[str, str]]],
    port_types: dict[str, dict[str, dict[str, str]]],
    target_ns: str | None,
    warnings: list[str],
) -> list[ParsedFolder]:
    """Emit operations from bindings when no service section exists."""
    del warnings
    children: list[ParsedFolder | ParsedRequest] = []
    for binding in bindings.values():
        pt_name = str(binding.get("type") or "")
        pt_ops = port_types.get(pt_name, {})
        for op_name, soap_action in binding.get("operations", {}).items():
            children.append(
                _make_request(
                    op_name=str(op_name),
                    location="",
                    soap_action=str(soap_action or ""),
                    input_message=pt_ops.get(str(op_name), {}).get("input", ""),
                    messages=messages,
                    target_ns=target_ns,
                )
            )
    if not children:
        return []
    return [
        ParsedFolder(
            type="folder",
            name="Default",
            description=None,
            auth=None,
            events=None,
            children=children,
        )
    ]


def _make_request(
    *,
    op_name: str,
    location: str,
    soap_action: str,
    input_message: str,
    messages: dict[str, list[dict[str, str]]],
    target_ns: str | None,
) -> ParsedRequest:
    """Build a SOAP POST ``ParsedRequest`` for one operation."""
    parts = messages.get(input_message, [])
    part_names = [p["name"] for p in parts if p.get("name")]
    body_el = None
    for part in parts:
        el = part.get("element") or ""
        if el:
            local = _strip_prefix(el)
            body_el = etree.QName(target_ns, local) if target_ns else etree.QName(local)
            # Prefer element name as wrapper; parts become children when type-style.
            if not part_names or part_names == [part.get("name")]:
                part_names = []
            break

    if body_el is None and target_ns:
        body_el = etree.QName(target_ns, op_name)
        # document/literal style often uses operation name as wrapper
        # Keep part_names as child placeholders when present.

    body = build_soap_envelope(
        body_element_qname=body_el,
        part_names=part_names,
        target_namespace=target_ns,
    )
    headers: list[dict[str, Any]] = [
        {
            "key": "Content-Type",
            "value": soap_content_type(),
            "enabled": True,
            "type": "text",
        }
    ]
    if soap_action is not None:
        headers.append(
            {
                "key": "SOAPAction",
                "value": f'"{soap_action}"',
                "enabled": True,
                "type": "text",
            }
        )
    url = location or "{{baseUrl}}"
    return ParsedRequest(
        type="request",
        name=op_name,
        method="POST",
        url=url,
        headers=headers,
        body=body,
        body_mode="raw",
        description=None,
    )


def _strip_prefix(qname: str | None) -> str:
    """Strip ``ns:`` prefix from a QName string."""
    if not qname:
        return ""
    if ":" in qname:
        return qname.split(":", 1)[1]
    return qname
