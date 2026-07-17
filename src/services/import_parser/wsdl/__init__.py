"""WSDL 1.1 import parsers."""

from __future__ import annotations

from services.import_parser.wsdl.parser import detect_wsdl_text, load_wsdl_text, parse_wsdl_document

__all__ = [
    "detect_wsdl_text",
    "load_wsdl_text",
    "parse_wsdl_document",
]
