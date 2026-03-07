"""Unit tests for the import service layer."""

from __future__ import annotations

import json
from pathlib import Path

from database.models.collections.collection_query_repository import fetch_all_collections
from database.models.environments.environment_repository import fetch_all_environments
from services.import_service import ImportService


class TestImportServiceFiles:
    """Tests for ImportService.import_files."""

    def test_import_single_collection_file(self, tmp_path: Path) -> None:
        """Importing a single collection file persists to the database."""
        data = {
            "info": {"name": "File Import"},
            "item": [
                {
                    "name": "Get Users",
                    "request": {
                        "method": "GET",
                        "url": "https://api.example.com/users",
                    },
                }
            ],
        }
        f = tmp_path / "coll.json"
        f.write_text(json.dumps(data))

        summary = ImportService.import_files([f])
        assert summary["collections_imported"] == 1
        assert summary["requests_imported"] == 1
        assert not summary["errors"]

        # Verify persistence
        colls = fetch_all_collections()
        assert len(colls) == 1

    def test_import_multiple_files(self, tmp_path: Path) -> None:
        """Importing multiple files persists all of them."""
        for i in range(3):
            data = {
                "info": {"name": f"Coll {i}"},
                "item": [
                    {
                        "name": f"Req {i}",
                        "request": {"method": "GET", "url": f"http://example.com/{i}"},
                    }
                ],
            }
            (tmp_path / f"c{i}.json").write_text(json.dumps(data))

        files = list(tmp_path.glob("*.json"))
        summary = ImportService.import_files(files)
        assert summary["collections_imported"] == 3
        assert summary["requests_imported"] == 3

    def test_import_file_with_bad_json(self, tmp_path: Path) -> None:
        """A file with invalid JSON produces an error but does not crash."""
        f = tmp_path / "bad.json"
        f.write_text("{broken")

        summary = ImportService.import_files([f])
        assert summary["collections_imported"] == 0
        assert len(summary["errors"]) >= 1


class TestImportServiceFolder:
    """Tests for ImportService.import_folder."""

    def test_import_folder_with_archive(self, tmp_path: Path) -> None:
        """Import a structured archive folder."""
        archive_data = {"collection": {"uid-1": True}, "environment": {"uid-2": True}}
        (tmp_path / "archive.json").write_text(json.dumps(archive_data))

        (tmp_path / "collection").mkdir()
        coll_data = {
            "info": {"name": "Folder Coll"},
            "item": [
                {
                    "name": "R",
                    "request": {"method": "POST", "url": "http://example.com"},
                }
            ],
        }
        (tmp_path / "collection" / "uid-1.json").write_text(json.dumps(coll_data))

        (tmp_path / "environment").mkdir()
        env_data = {"name": "Folder Env", "values": [{"key": "k", "value": "v"}]}
        (tmp_path / "environment" / "uid-2.json").write_text(json.dumps(env_data))

        summary = ImportService.import_folder(tmp_path)
        assert summary["collections_imported"] == 1
        assert summary["environments_imported"] == 1
        assert not summary["errors"]


class TestImportServiceText:
    """Tests for ImportService.import_text."""

    def test_import_json_text(self) -> None:
        """Importing collection JSON text persists to database."""
        data = {
            "info": {"name": "Text Coll"},
            "item": [
                {
                    "name": "TR",
                    "request": {"method": "GET", "url": "http://example.com"},
                }
            ],
        }
        summary = ImportService.import_text(json.dumps(data))
        assert summary["collections_imported"] == 1
        assert summary["requests_imported"] == 1

    def test_import_empty_text(self) -> None:
        """Empty text returns an error."""
        summary = ImportService.import_text("")
        assert len(summary["errors"]) >= 1
        assert summary["collections_imported"] == 0


class TestImportServiceCurl:
    """Tests for ImportService.import_curl."""

    def test_import_curl_command(self) -> None:
        """A cURL command becomes a persisted collection with one request."""
        summary = ImportService.import_curl("curl -X GET https://api.example.com/items")
        assert summary["collections_imported"] == 1
        assert summary["requests_imported"] == 1
        assert not summary["errors"]

    def test_import_multi_curl(self) -> None:
        """Multiple cURL commands create multiple requests in one collection."""
        text = (
            "curl https://api.example.com/a\ncurl -X POST https://api.example.com/b -d '{\"x\": 1}'"
        )
        summary = ImportService.import_curl(text)
        assert summary["requests_imported"] == 2


class TestImportServiceEnvironments:
    """Tests for environment import via files."""

    def test_import_environment_file(self, tmp_path: Path) -> None:
        """Importing an environment JSON file persists to the database."""
        data = {
            "name": "Staging",
            "values": [{"key": "host", "value": "staging.example.com", "enabled": True}],
        }
        f = tmp_path / "env.json"
        f.write_text(json.dumps(data))

        summary = ImportService.import_files([f])
        assert summary["environments_imported"] == 1
        assert not summary["errors"]

        envs = fetch_all_environments()
        assert len(envs) == 1
        assert envs[0]["name"] == "Staging"


class TestImportServiceNestedCollections:
    """Tests for nested folders and saved responses."""

    def test_nested_folders_with_responses(self, tmp_path: Path) -> None:
        """A collection with nested folders and saved responses imports fully."""
        data = {
            "info": {"name": "Deep"},
            "item": [
                {
                    "name": "Folder A",
                    "item": [
                        {
                            "name": "Inner Req",
                            "request": {
                                "method": "GET",
                                "url": "http://example.com",
                            },
                            "response": [
                                {
                                    "name": "Success",
                                    "code": 200,
                                    "body": "OK",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        f = tmp_path / "deep.json"
        f.write_text(json.dumps(data))

        summary = ImportService.import_files([f])
        # Root collection + Folder A
        assert summary["collections_imported"] == 2
        assert summary["requests_imported"] == 1
        assert summary["responses_imported"] == 1
