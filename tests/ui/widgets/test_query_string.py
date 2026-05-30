"""Unit tests for :mod:`ui.widgets.query_string`."""

from __future__ import annotations

from ui.widgets.query_string import (
    build_query,
    build_url_with_query,
    parse_query,
    split_url,
    url_has_query,
)


def _pairs_to_rows(pairs: list[tuple[str, str | None]]) -> list[dict]:
    """Build table row dicts from :func:`parse_query` pairs."""
    rows: list[dict] = []
    for key, value in pairs:
        row: dict = {"key": key, "value": "" if value is None else value, "enabled": True}
        if value is None:
            row["flag"] = True
        rows.append(row)
    return rows


def test_parse_query_two_pairs() -> None:
    """``parse_query`` splits ``&``-joined key=value segments."""
    assert parse_query("https://h/p?a=1&b=2") == [("a", "1"), ("b", "2")]


def test_parse_query_flag_and_pair() -> None:
    """A segment without ``=`` is a flag-style param (``None`` value)."""
    assert parse_query("https://h/p?flag&a=1") == [("flag", None), ("a", "1")]


def test_parse_query_empty_value() -> None:
    """Trailing ``=`` preserves an empty value (not a flag)."""
    assert parse_query("https://h/p?a=") == [("a", "")]


def test_parse_query_duplicate_keys() -> None:
    """Duplicate keys preserve order."""
    assert parse_query("https://h/p?a=1&a=2") == [("a", "1"), ("a", "2")]


def test_parse_query_skips_empty_key_segment() -> None:
    """``=skip`` segments with empty keys are dropped."""
    assert parse_query("https://h/p?a=1&=skip&flag") == [("a", "1"), ("flag", None)]


def test_parse_query_value_contains_equals() -> None:
    """Only the first ``=`` outside ``{{…}}`` splits key from value."""
    assert parse_query("https://h/p?a=b=c") == [("a", "b=c")]


def test_parse_query_variable_placeholder_not_encoded() -> None:
    """``{{…}}`` placeholders pass through unchanged."""
    assert parse_query("https://h/p?token={{api_key}}") == [("token", "{{api_key}}")]


def test_parse_query_ampersand_inside_mustache() -> None:
    """``&`` inside ``{{…}}`` does not split the query."""
    assert parse_query("https://h/p?token={{a&b}}") == [("token", "{{a&b}}")]


def test_split_url_hash_inside_mustache() -> None:
    """``#`` inside ``{{…}}`` does not start a URL fragment."""
    assert split_url("https://h/p?token={{a#b}}") == ("https://h/p", "token={{a#b}}", "")


def test_split_url_with_fragment() -> None:
    """``split_url`` separates base, query, and fragment."""
    assert split_url("https://h/p?a=1#frag") == ("https://h/p", "a=1", "#frag")


def test_url_has_query_with_value_containing_underscore() -> None:
    """``url_has_query`` must not confuse base URL with the query segment."""
    assert url_has_query("https://h/p?token=from_url") is True


def test_split_url_fragment_before_query() -> None:
    """A ``#`` before ``?`` means there is no query segment."""
    assert split_url("https://h/p#f?x=1") == ("https://h/p", "", "#f?x=1")
    assert url_has_query("https://h/p#f?x=1") is False


def test_build_url_with_query_clears_empty_rows() -> None:
    """An empty row list removes the query but keeps the fragment."""
    assert build_url_with_query("https://h/p?a=1#f", []) == "https://h/p#f"


def test_build_url_with_query_adds_query() -> None:
    """Enabled rows become a ``?`` query on a bare base URL."""
    assert build_url_with_query("https://h/p", [{"key": "a", "value": "1"}]) == "https://h/p?a=1"


def test_build_query_skips_disabled() -> None:
    """Disabled rows are omitted from the query string."""
    rows = [
        {"key": "a", "value": "1", "enabled": True},
        {"key": "b", "value": "2", "enabled": False},
    ]
    assert build_query(rows) == "a=1"


def test_build_query_flag_style() -> None:
    """Flag rows emit the key without ``=``."""
    rows = [{"key": "verbose", "value": "", "enabled": True, "flag": True}]
    assert build_query(rows) == "verbose"


def test_round_trip_preserves_placeholders() -> None:
    """Parse then build leaves ``{{…}}`` and values unchanged."""
    url = "https://h/p?token={{x}}&a=1"
    rows = _pairs_to_rows(parse_query(url))
    rebuilt = build_url_with_query("https://h/p", rows)
    assert rebuilt == url
    assert "%" not in rebuilt


def test_round_trip_flag_param_unchanged_when_editing_sibling() -> None:
    """Editing one param must not add ``=`` to a flag-style sibling."""
    url = "https://h/p?verbose&a=1"
    rows = _pairs_to_rows(parse_query(url))
    rows[1]["value"] = "2"
    assert build_url_with_query("https://h/p", rows) == "https://h/p?verbose&a=2"
