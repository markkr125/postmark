"""Tests for the Postman and cURL import parsers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.import_parser.curl_parser import is_curl, parse_curl
from services.import_parser.postman_parser import (
    detect_postman_type,
    parse_archive_folder,
    parse_collection_file,
    parse_environment_file,
    parse_json_text,
)
from services.import_parser.url_parser import parse_raw_text


# ------------------------------------------------------------------
# detect_postman_type
# ------------------------------------------------------------------
class TestDetectPostmanType:
    """Tests for auto-detecting Postman JSON types."""

    def test_detects_collection(self) -> None:
        """A dict with 'info' and 'item' keys is a collection."""
        data: dict[str, Any] = {"info": {"name": "Test"}, "item": []}
        assert detect_postman_type(data) == "collection"

    def test_detects_environment(self) -> None:
        """A dict with 'name' and 'values' keys is an environment."""
        data = {"name": "Prod", "values": []}
        assert detect_postman_type(data) == "environment"

    def test_detects_archive(self) -> None:
        """A dict with 'collection' and 'environment' keys is an archive."""
        data: dict[str, Any] = {"collection": {}, "environment": {}}
        assert detect_postman_type(data) == "archive"

    def test_unknown_format(self) -> None:
        """An unrecognised dict returns 'unknown'."""
        data = {"foo": "bar"}
        assert detect_postman_type(data) == "unknown"


# ------------------------------------------------------------------
# parse_collection_file
# ------------------------------------------------------------------
class TestParseCollectionFile:
    """Tests for parsing Postman collection JSON files."""

    def test_simple_collection(self, tmp_path: Path) -> None:
        """Parse a minimal collection with one request."""
        data = {
            "info": {"name": "My API", "schema": "..."},
            "item": [
                {
                    "name": "Get Users",
                    "request": {
                        "method": "GET",
                        "url": {"raw": "https://api.example.com/users"},
                    },
                }
            ],
        }
        f = tmp_path / "coll.json"
        f.write_text(json.dumps(data))

        result = parse_collection_file(f)
        assert len(result["collections"]) == 1
        assert not result["errors"]

        coll = result["collections"][0]
        assert coll["name"] == "My API"
        assert len(coll["items"]) == 1
        item: Any = coll["items"][0]
        assert item["method"] == "GET"
        assert item["url"] == "https://api.example.com/users"

    def test_nested_folders(self, tmp_path: Path) -> None:
        """Parse a collection with nested folder hierarchy."""
        data = {
            "info": {"name": "Nested"},
            "item": [
                {
                    "name": "Outer",
                    "item": [
                        {
                            "name": "Inner Request",
                            "request": {
                                "method": "POST",
                                "url": "https://example.com/inner",
                                "body": {"mode": "raw", "raw": '{"key": "val"}'},
                            },
                        }
                    ],
                }
            ],
        }
        f = tmp_path / "nested.json"
        f.write_text(json.dumps(data))

        result = parse_collection_file(f)
        coll = result["collections"][0]
        folder: Any = coll["items"][0]
        assert folder["type"] == "folder"
        assert folder["name"] == "Outer"
        children: list[Any] = folder["children"]
        assert len(children) == 1
        assert children[0]["method"] == "POST"

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty files produce an error, not a crash."""
        f = tmp_path / "empty.json"
        f.write_text("")
        result = parse_collection_file(f)
        assert len(result["errors"]) == 1
        assert not result["collections"]

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Malformed JSON produces an error."""
        f = tmp_path / "bad.json"
        f.write_text("{not valid json}")
        result = parse_collection_file(f)
        assert len(result["errors"]) == 1

    def test_request_with_auth_and_headers(self, tmp_path: Path) -> None:
        """Auth and structured headers are preserved."""
        data = {
            "info": {"name": "Auth Test"},
            "item": [
                {
                    "name": "Authed",
                    "request": {
                        "method": "GET",
                        "url": "https://api.example.com",
                        "auth": {
                            "type": "bearer",
                            "bearer": [{"key": "token", "value": "abc123"}],
                        },
                        "header": [{"key": "X-Custom", "value": "yes", "type": "text"}],
                    },
                }
            ],
        }
        f = tmp_path / "auth.json"
        f.write_text(json.dumps(data))

        result = parse_collection_file(f)
        req: Any = result["collections"][0]["items"][0]
        assert req["auth"]["type"] == "bearer"
        assert req["headers"][0]["key"] == "X-Custom"

    def test_saved_responses(self, tmp_path: Path) -> None:
        """Saved responses (examples) are parsed correctly."""
        data = {
            "info": {"name": "Responses Test"},
            "item": [
                {
                    "name": "With Response",
                    "request": {"method": "GET", "url": "https://example.com"},
                    "response": [
                        {
                            "name": "200 OK",
                            "status": "OK",
                            "code": 200,
                            "body": '{"result": true}',
                            "_postman_previewlanguage": "json",
                        }
                    ],
                }
            ],
        }
        f = tmp_path / "resp.json"
        f.write_text(json.dumps(data))

        result = parse_collection_file(f)
        req: Any = result["collections"][0]["items"][0]
        assert len(req["saved_responses"]) == 1
        assert req["saved_responses"][0]["code"] == 200
        assert req["saved_responses"][0]["preview_language"] == "json"

    def test_collection_variables_and_events(self, tmp_path: Path) -> None:
        """Collection-level variables and events are preserved."""
        data = {
            "info": {"name": "Vars"},
            "item": [],
            "variable": [{"key": "host", "value": "localhost"}],
            "event": [{"listen": "prerequest", "script": {"exec": ["console.log('hi')"]}}],
        }
        f = tmp_path / "vars.json"
        f.write_text(json.dumps(data))

        result = parse_collection_file(f)
        coll = result["collections"][0]
        assert coll["variables"] is not None
        assert coll["variables"][0]["key"] == "host"
        assert coll["events"] is not None
        assert coll["events"][0]["listen"] == "prerequest"

    def test_body_modes(self, tmp_path: Path) -> None:
        """Different body modes are handled (raw, formdata, graphql)."""
        data = {
            "info": {"name": "Body modes"},
            "item": [
                {
                    "name": "Raw JSON",
                    "request": {
                        "method": "POST",
                        "url": "https://example.com",
                        "body": {
                            "mode": "raw",
                            "raw": '{"a": 1}',
                            "options": {"raw": {"language": "json"}},
                        },
                    },
                },
                {
                    "name": "GraphQL",
                    "request": {
                        "method": "POST",
                        "url": "https://example.com/graphql",
                        "body": {
                            "mode": "graphql",
                            "graphql": {"query": "{ users { id } }"},
                        },
                    },
                },
            ],
        }
        f = tmp_path / "body.json"
        f.write_text(json.dumps(data))

        result = parse_collection_file(f)
        items: list[Any] = result["collections"][0]["items"]
        assert items[0]["body_mode"] == "raw"
        assert items[0]["body_options"] == {"raw": {"language": "json"}}
        assert items[1]["body_mode"] == "graphql"


# ------------------------------------------------------------------
# parse_environment_file
# ------------------------------------------------------------------
class TestParseEnvironmentFile:
    """Tests for parsing Postman environment JSON files."""

    def test_basic_environment(self, tmp_path: Path) -> None:
        """Parse a simple environment with variables."""
        data = {
            "name": "Production",
            "values": [
                {"key": "base_url", "value": "https://api.prod.com", "enabled": True},
                {"key": "api_key", "value": "secret", "type": "secret"},
            ],
        }
        f = tmp_path / "env.json"
        f.write_text(json.dumps(data))

        result = parse_environment_file(f)
        assert len(result["environments"]) == 1
        assert not result["errors"]
        env = result["environments"][0]
        assert env["name"] == "Production"
        assert len(env["values"]) == 2
        assert env["values"][0]["key"] == "base_url"
        assert env["values"][1]["type"] == "secret"

    def test_not_an_environment(self, tmp_path: Path) -> None:
        """A collection file passed to parse_environment_file returns an error."""
        data = {"info": {"name": "Not env"}, "item": []}
        f = tmp_path / "coll.json"
        f.write_text(json.dumps(data))

        result = parse_environment_file(f)
        assert not result["environments"]
        assert len(result["errors"]) == 1


# ------------------------------------------------------------------
# parse_archive_folder
# ------------------------------------------------------------------
class TestParseArchiveFolder:
    """Tests for parsing Postman data-dump folders."""

    def test_archive_with_index(self, tmp_path: Path) -> None:
        """Parse a folder with archive.json and collection/environment sub-dirs."""
        # Create archive.json
        archive_data = {
            "collection": {"uuid-1": True},
            "environment": {"uuid-2": True},
        }
        (tmp_path / "archive.json").write_text(json.dumps(archive_data))

        # Collection file
        coll_dir = tmp_path / "collection"
        coll_dir.mkdir()
        coll_data = {
            "info": {"name": "Archived Coll"},
            "item": [{"name": "Req", "request": {"method": "GET", "url": "https://example.com"}}],
        }
        (coll_dir / "uuid-1.json").write_text(json.dumps(coll_data))

        # Environment file
        env_dir = tmp_path / "environment"
        env_dir.mkdir()
        env_data = {"name": "Archived Env", "values": [{"key": "k", "value": "v"}]}
        (env_dir / "uuid-2.json").write_text(json.dumps(env_data))

        result = parse_archive_folder(tmp_path)
        assert len(result["collections"]) == 1
        assert len(result["environments"]) == 1
        assert not result["errors"]

    def test_missing_collection_file(self, tmp_path: Path) -> None:
        """Missing collection files produce errors without crashing."""
        archive_data = {"collection": {"missing-uuid": True}, "environment": {}}
        (tmp_path / "archive.json").write_text(json.dumps(archive_data))
        (tmp_path / "collection").mkdir()

        result = parse_archive_folder(tmp_path)
        assert not result["collections"]
        assert len(result["errors"]) == 1

    def test_folder_without_archive_json(self, tmp_path: Path) -> None:
        """A folder without archive.json scans all JSON files."""
        coll_data = {
            "info": {"name": "Loose Coll"},
            "item": [{"name": "R", "request": {"method": "GET", "url": "http://example.com"}}],
        }
        (tmp_path / "coll1.json").write_text(json.dumps(coll_data))

        result = parse_archive_folder(tmp_path)
        assert len(result["collections"]) == 1

    def test_real_archive_folder(self) -> None:
        """Parse the real archive folder from the project."""
        archive_path = Path(__file__).resolve().parents[2] / "archive"
        if not archive_path.exists():
            pytest.skip("Archive folder not available")

        result = parse_archive_folder(archive_path)
        # Should find at least some collections and environments
        assert len(result["collections"]) > 0
        assert len(result["environments"]) > 0


# ------------------------------------------------------------------
# parse_json_text
# ------------------------------------------------------------------
class TestParseJsonText:
    """Tests for parsing raw JSON text."""

    def test_collection_json(self) -> None:
        """JSON text that looks like a collection is parsed."""
        data = {"info": {"name": "Text Coll"}, "item": []}
        result = parse_json_text(json.dumps(data))
        assert len(result["collections"]) == 1

    def test_environment_json(self) -> None:
        """JSON text that looks like an environment is parsed."""
        data = {"name": "Text Env", "values": []}
        result = parse_json_text(json.dumps(data))
        assert len(result["environments"]) == 1

    def test_invalid_json(self) -> None:
        """Invalid JSON returns an error."""
        result = parse_json_text("{broken")
        assert len(result["errors"]) == 1

    def test_unknown_json(self) -> None:
        """Valid JSON that is neither collection nor environment returns error."""
        result = parse_json_text('{"random": "data"}')
        assert len(result["errors"]) == 1


# ------------------------------------------------------------------
# cURL parser
# ------------------------------------------------------------------
class TestCurlParser:
    """Tests for cURL command parsing."""

    def test_is_curl(self) -> None:
        """is_curl detects cURL commands."""
        assert is_curl("curl https://example.com")
        assert is_curl("  curl -X GET http://api.com")
        assert not is_curl("wget https://example.com")
        assert not is_curl("just some text")

    def test_simple_get(self) -> None:
        """Parse a simple GET cURL command."""
        result = parse_curl("curl https://api.example.com/users")
        assert len(result["collections"]) == 1
        items: list[Any] = result["collections"][0]["items"]
        assert len(items) == 1
        assert items[0]["method"] == "GET"
        assert items[0]["url"] == "https://api.example.com/users"

    def test_post_with_data(self) -> None:
        """Parse a POST with --data and headers."""
        cmd = (
            "curl -X POST https://api.example.com/login "
            '-H "Content-Type: application/json" '
            '-d \'{"user": "admin", "pass": "secret"}\''
        )
        result = parse_curl(cmd)
        items: list[Any] = result["collections"][0]["items"]
        assert items[0]["method"] == "POST"
        assert items[0]["body"] is not None
        assert items[0]["body_mode"] == "raw"
        assert items[0]["headers"][0]["key"] == "Content-Type"

    def test_basic_auth(self) -> None:
        """Parse cURL with -u (basic auth)."""
        result = parse_curl("curl -u admin:password https://api.example.com")
        items: list[Any] = result["collections"][0]["items"]
        assert items[0]["auth"]["type"] == "basic"
        assert items[0]["auth"]["basic"][0]["value"] == "admin"

    def test_multiple_commands(self) -> None:
        """Multiple cURL commands are parsed into separate requests."""
        text = (
            "curl https://api.example.com/users\n"
            'curl -X POST https://api.example.com/users -d \'{"name": "test"}\''
        )
        result = parse_curl(text)
        items: list[Any] = result["collections"][0]["items"]
        assert len(items) == 2
        assert items[0]["method"] == "GET"
        assert items[1]["method"] == "POST"

    def test_no_curl_found(self) -> None:
        """Non-cURL text returns an error."""
        result = parse_curl("not a curl command")
        assert not result["collections"]
        assert len(result["errors"]) == 1

    def test_infer_post_from_body(self) -> None:
        """POST method is inferred when body is present but no -X flag."""
        result = parse_curl('curl https://example.com -d "data"')
        items: list[Any] = result["collections"][0]["items"]
        assert items[0]["method"] == "POST"

    def test_line_continuations(self) -> None:
        """Line continuation backslashes are handled."""
        cmd = "curl \\\n  -X PUT \\\n  https://api.example.com/resource"
        result = parse_curl(cmd)
        items: list[Any] = result["collections"][0]["items"]
        assert items[0]["method"] == "PUT"


# ------------------------------------------------------------------
# parse_raw_text (auto-detection)
# ------------------------------------------------------------------
class TestParseRawText:
    """Tests for auto-detecting and parsing raw text input."""

    def test_detects_curl(self) -> None:
        """Curl commands are detected and parsed."""
        result = parse_raw_text("curl https://example.com")
        assert len(result["collections"]) == 1
        item: Any = result["collections"][0]["items"][0]
        assert item["method"] == "GET"

    def test_detects_json_collection(self) -> None:
        """Postman collection JSON is detected and parsed."""
        data = {"info": {"name": "Auto"}, "item": []}
        result = parse_raw_text(json.dumps(data))
        assert len(result["collections"]) == 1

    def test_detects_url(self) -> None:
        """A plain URL is wrapped as a GET request."""
        result = parse_raw_text("https://api.example.com/health")
        assert len(result["collections"]) == 1
        item: Any = result["collections"][0]["items"][0]
        assert item["method"] == "GET"
        assert item["url"] == "https://api.example.com/health"

    def test_empty_input(self) -> None:
        """Empty input returns an error."""
        result = parse_raw_text("")
        assert len(result["errors"]) == 1

    def test_unrecognised_input(self) -> None:
        """Random text that is not cURL/JSON/URL returns an error."""
        result = parse_raw_text("just some random text")
        assert len(result["errors"]) == 1
