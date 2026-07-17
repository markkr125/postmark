"""Tests for WSDL 1.1 → SOAP collection import."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from services.import_parser import parse_collection_file
from services.import_parser.models import ParsedFolder, ParsedRequest
from services.import_parser.url_parser import fetch_and_parse_url
from services.import_parser.wsdl import load_wsdl_text, parse_wsdl_document


_MINIMAL_WSDL = """<?xml version="1.0" encoding="UTF-8"?>
<definitions name="Calculator"
  targetNamespace="http://example.com/calc"
  xmlns="http://schemas.xmlsoap.org/wsdl/"
  xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
  xmlns:tns="http://example.com/calc"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <message name="AddRequest">
    <part name="a" type="xsd:int"/>
    <part name="b" type="xsd:int"/>
  </message>
  <message name="AddResponse">
    <part name="result" type="xsd:int"/>
  </message>
  <portType name="CalculatorPortType">
    <operation name="Add">
      <input message="tns:AddRequest"/>
      <output message="tns:AddResponse"/>
    </operation>
  </portType>
  <binding name="CalculatorSoap" type="tns:CalculatorPortType">
    <soap:binding style="rpc" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="Add">
      <soap:operation soapAction="http://example.com/calc/Add"/>
      <input><soap:body use="encoded"/></input>
      <output><soap:body use="encoded"/></output>
    </operation>
  </binding>
  <service name="CalculatorService">
    <port name="CalculatorPort" binding="tns:CalculatorSoap">
      <soap:address location="https://example.com/calc"/>
    </port>
  </service>
</definitions>
"""


class TestWsdlParser:
    """WSDL 1.1 SOAP bindings become POST requests."""

    def test_operations_become_soap_posts(self) -> None:
        """Service folder contains Add as SOAP POST with envelope + SOAPAction."""
        result = parse_wsdl_document(_MINIMAL_WSDL)
        assert result["errors"] == [] or all(
            "remote" in e.lower() or "skipped" in e.lower() for e in result["errors"]
        )
        assert len(result["collections"]) == 1
        coll = result["collections"][0]
        assert "Calculator" in coll["name"] or coll["name"] == "CalculatorService"
        folder = cast(ParsedFolder, coll["items"][0])
        assert folder["type"] == "folder"
        assert len(folder["children"]) == 1
        req = cast(ParsedRequest, folder["children"][0])
        assert req["name"] == "Add"
        assert req["method"] == "POST"
        assert req["url"] == "https://example.com/calc"
        assert req["body"] is not None
        assert "Envelope" in (req["body"] or "")
        assert "soapenv" in (req["body"] or "").lower() or "Envelope" in (req["body"] or "")
        headers = {
            str(h["key"]): str(h["value"])
            for h in cast(list[dict[str, Any]], req.get("headers") or [])
        }
        assert "text/xml" in headers.get("Content-Type", "")
        assert "Add" in headers.get("SOAPAction", "")

    def test_load_wsdl_text_detect(self) -> None:
        """load_wsdl_text returns None for non-WSDL."""
        assert load_wsdl_text("not xml") is None
        assert load_wsdl_text(_MINIMAL_WSDL) is not None

    def test_parse_collection_file_wsdl(self, tmp_path: Path) -> None:
        """``.wsdl`` files import via parse_collection_file."""
        path = tmp_path / "calc.wsdl"
        path.write_text(_MINIMAL_WSDL, encoding="utf-8")
        result = parse_collection_file(path)
        assert result["collections"]
        folder = cast(ParsedFolder, result["collections"][0]["items"][0])
        req = cast(ParsedRequest, folder["children"][0])
        assert req["method"] == "POST"

    def test_fetch_url_wsdl(self) -> None:
        """fetch_and_parse_url accepts WSDL XML bodies."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = _MINIMAL_WSDL.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_and_parse_url("https://example.com/calc?wsdl")
        folder = cast(ParsedFolder, result["collections"][0]["items"][0])
        req = cast(ParsedRequest, folder["children"][0])
        assert req["name"] == "Add"
