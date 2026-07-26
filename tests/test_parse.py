"""Tests for JSON/YAML load and dump (shipped minrepro.parse)."""

from __future__ import annotations

from pathlib import Path

import pytest

from minrepro.parse import ParseError, detect_format, dump, dumps, load, loads


def test_loads_yaml_and_json_roundtrip():
    y = "services:\n  backend:\n    x: 1\n"
    data = loads(y, "yaml")
    assert data == {"services": {"backend": {"x": 1}}}
    text = dumps(data, "yaml")
    assert loads(text, "yaml") == data

    j = '{"a": [1, 2], "b": true}'
    data_j = loads(j, "json")
    assert data_j == {"a": [1, 2], "b": True}
    assert loads(dumps(data_j, "json"), "json") == data_j


def test_root_must_be_mapping_or_sequence():
    with pytest.raises(ParseError, match="root must be"):
        loads("just a string\n", "yaml")
    with pytest.raises(ParseError, match="empty"):
        loads("", "yaml")
    with pytest.raises(ParseError, match="empty"):
        loads("null\n", "yaml")


def test_invalid_json():
    with pytest.raises(ParseError, match="invalid JSON"):
        loads("{not json", "json")


def test_detect_format(tmp_path: Path):
    y = tmp_path / "c.yaml"
    y.write_text("a: 1\n", encoding="utf-8")
    assert detect_format(y) == "yaml"
    j = tmp_path / "c.json"
    j.write_text('{"a": 1}\n', encoding="utf-8")
    assert detect_format(j) == "json"
    bare = tmp_path / "c.conf"
    bare.write_text('{"a": 1}\n', encoding="utf-8")
    assert detect_format(bare) == "json"
    bare2 = tmp_path / "d.conf"
    bare2.write_text("a: 1\n", encoding="utf-8")
    assert detect_format(bare2) == "yaml"
    assert detect_format(y, "json") == "json"  # explicit override


def test_load_and_dump_file(tmp_path: Path, broken_yaml: Path):
    data, fmt, text = load(broken_yaml)
    assert fmt == "yaml"
    assert "BAD_OPTION" in text
    out = tmp_path / "out.yaml"
    dump(out, data, fmt)
    data2, _, _ = load(out)
    assert data2 == data


def test_sequence_root():
    data = loads("- a\n- b\n", "yaml")
    assert data == ["a", "b"]
    assert loads(dumps(data, "yaml"), "yaml") == data


def test_yaml_datetime_rejected_as_non_json_compatible():
    # Bare YAML dates become datetime.date under PyYAML safe_load.
    with pytest.raises(ParseError, match="JSON-compatible|date|unsupported value type"):
        loads("created: 2024-01-15\n", "yaml")


def test_yaml_timestamp_string_accepted():
    data = loads('created: "2024-01-15"\n', "yaml")
    assert data == {"created": "2024-01-15"}
