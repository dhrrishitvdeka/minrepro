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


def test_yaml_bool_word_keys_stay_strings_after_roundtrip():
    text = "on:\n  push:\n    branches:\n      - main\n"
    data = loads(text, "yaml")
    assert list(data.keys()) == ["on"]
    assert data["on"]["push"]["branches"] == ["main"]
    dumped = dumps(data, "yaml")
    first = dumped.lstrip().splitlines()[0]
    assert first.startswith("on:")
    assert not first.startswith("true:")
    reloaded = loads(dumped, "yaml")
    assert reloaded == data
    assert list(reloaded.keys()) == ["on"]


def test_yaml_bool_word_keys_yes_no_off():
    data = loads("yes: 1\nno: 2\noff: 3\nON: 4\n", "yaml")
    assert data["yes"] == 1
    assert data["no"] == 2
    assert data["off"] == 3
    assert data["ON"] == 4
    dumped = dumps(data, "yaml")
    reloaded = loads(dumped, "yaml")
    assert reloaded == data


def test_yaml_bool_values_still_bools():
    data = loads("enabled: yes\nflag: true\nclosed: off\n", "yaml")
    assert data["enabled"] is True
    assert data["flag"] is True
    assert data["closed"] is False
    dumped = dumps(data, "yaml")
    assert "!!bool" not in dumped
    assert "true" in dumped
    assert "false" in dumped


def test_json_rejects_nan_and_infinity():
    with pytest.raises(ParseError, match="non-finite"):
        loads('{"n": NaN}', "json")
    with pytest.raises(ParseError, match="non-finite"):
        loads('{"n": Infinity}', "json")
    with pytest.raises(ParseError, match="non-finite"):
        loads('{"n": -Infinity}', "json")


def test_yaml_rejects_nan_and_inf():
    with pytest.raises(ParseError, match="non-finite"):
        loads("n: .nan\n", "yaml")
    with pytest.raises(ParseError, match="non-finite"):
        loads("n: .inf\n", "yaml")


def test_finite_json_roundtrip():
    data = loads('{"a": 1.5, "b": [true, null, "on"]}', "json")
    assert data == {"a": 1.5, "b": [True, None, "on"]}
    assert loads(dumps(data, "json"), "json") == data


def test_detect_format_with_text_avoids_disk():
    assert detect_format(Path("unknown.custom"), text='{"key": 1}') == "json"
    assert detect_format(Path("unknown.custom"), text="key: 1") == "yaml"


def test_detect_format_handles_bom(tmp_path: Path):
    p = tmp_path / "data.custom"
    p.write_bytes(b"\xef\xbb\xbf{\"hello\": \"world\"}")
    assert detect_format(p) == "json"
    data, fmt, _ = load(p)
    assert fmt == "json"
    assert data == {"hello": "world"}


def test_dumps_custom_indent():
    data = {"a": {"b": 1}}
    j4 = dumps(data, "json", indent=4)
    assert "    \"b\": 1" in j4
    y4 = dumps(data, "yaml", indent=4)
    assert "    b: 1" in y4

