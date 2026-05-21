"""Tests for :mod:`services.scripting.data_loader`."""

from __future__ import annotations

from pathlib import Path

from services.scripting.data_loader import parse_data_file


class TestParseDataFile:
    """Tests for :func:`parse_data_file` CSV/JSON helper."""

    def test_parse_csv(self, tmp_path: Path) -> None:
        """CSV with headers is parsed into list of dicts."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        rows = parse_data_file(csv_file)
        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "age": "30"}
        assert rows[1] == {"name": "Bob", "age": "25"}

    def test_parse_json_array(self, tmp_path: Path) -> None:
        """JSON array of objects is parsed."""
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"x": 1}, {"x": 2}]', encoding="utf-8")
        rows = parse_data_file(json_file)
        assert len(rows) == 2
        assert rows[0] == {"x": 1}

    def test_parse_json_non_array(self, tmp_path: Path) -> None:
        """JSON that is not an array returns an empty list."""
        json_file = tmp_path / "data.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")
        rows = parse_data_file(json_file)
        assert rows == []

    def test_parse_json_filters_non_dicts(self, tmp_path: Path) -> None:
        """Non-dict items in a JSON array are filtered out."""
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"a": 1}, 42, "str", {"b": 2}]', encoding="utf-8")
        rows = parse_data_file(json_file)
        assert len(rows) == 2
        assert rows[1] == {"b": 2}

    def test_parse_empty_csv(self, tmp_path: Path) -> None:
        """Empty CSV with only headers returns no rows."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n", encoding="utf-8")
        rows = parse_data_file(csv_file)
        assert rows == []
