"""Build SOAP 1.1 envelope templates for WSDL operations."""

from __future__ import annotations

from typing import Any

from lxml import etree

SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSDL_NS = "http://schemas.xmlsoap.org/wsdl/"
SOAP_NS = "http://schemas.xmlsoap.org/wsdl/soap/"
XSD_NS = "http://www.w3.org/2001/XMLSchema"

NSMAP = {
    "wsdl": WSDL_NS,
    "soap": SOAP_NS,
    "xsd": XSD_NS,
    "soapenv": SOAP_ENV_NS,
}


def soap_content_type() -> str:
    """Return the Content-Type header value for SOAP 1.1."""
    return "text/xml; charset=utf-8"


def build_soap_envelope(
    *,
    body_element_qname: etree.QName | None,
    part_names: list[str],
    target_namespace: str | None,
) -> str:
    """Build a SOAP 1.1 Envelope/Body XML string with placeholder children."""
    envelope = etree.Element(
        etree.QName(SOAP_ENV_NS, "Envelope"),
        nsmap={"soapenv": SOAP_ENV_NS},
    )
    etree.SubElement(envelope, etree.QName(SOAP_ENV_NS, "Header"))
    body = etree.SubElement(envelope, etree.QName(SOAP_ENV_NS, "Body"))

    if body_element_qname is not None:
        nsmap: dict[str, str] = {}
        prefix = "tns"
        if body_element_qname.namespace:
            nsmap[prefix] = body_element_qname.namespace
            op_el = etree.SubElement(
                body,
                etree.QName(body_element_qname.namespace, body_element_qname.localname),
                nsmap=nsmap,
            )
        else:
            op_el = etree.SubElement(body, body_element_qname.localname)
        for part in part_names:
            child = etree.SubElement(op_el, part)
            child.text = "{{" + part + "}}"
    elif part_names:
        wrapper_ns = target_namespace or ""
        if wrapper_ns:
            op_el = etree.SubElement(
                body,
                etree.QName(wrapper_ns, "Request"),
                nsmap={"tns": wrapper_ns},
            )
        else:
            op_el = etree.SubElement(body, "Request")
        for part in part_names:
            child = etree.SubElement(op_el, part)
            child.text = "{{" + part + "}}"
    else:
        etree.SubElement(body, "Request")

    xml_bytes = etree.tostring(
        envelope,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )
    return xml_bytes.decode("utf-8")


def local_name(tag: Any) -> str:
    """Return the local name of an lxml tag."""
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    if isinstance(tag, etree.QName):
        return tag.localname
    return str(tag)
