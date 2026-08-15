"""Public library entry: load → oracle → shrink → reduced text."""

from __future__ import annotations

from pathlib import Path

import pytest

from minrepro import (
    BaselineNotInteresting,
    ParseError,
    __version__,
    loads,
    reduce_data,
    reduce_file,
)
from minrepro.parse import dumps, load


def test_version_matches_package_metadata():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in text


def test_reduce_file_broken_yaml(broken_yaml: Path, oracle_bad_cmd: str):
    result = reduce_file(
        broken_yaml,
        oracle_bad_cmd,
        error_contains="BAD_OPTION",
    )
    reduced = result.reduced
    assert reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert "frontend" not in reduced["services"]
    reparsed = loads(result.reduced_text, "yaml")
    assert reparsed == reduced


def test_reduce_file_broken_json(broken_json: Path, oracle_bad_cmd: str):
    result = reduce_file(
        broken_json,
        oracle_bad_cmd,
        error_contains="BAD_OPTION",
    )
    assert result.format == "json"
    assert result.reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert "frontend" not in result.reduced["services"]


def test_reduce_data_matches_reduce_file(broken_yaml: Path, oracle_bad_cmd: str):
    data, fmt, text = load(broken_yaml)
    via_data = reduce_data(
        data,
        oracle_bad_cmd,
        fmt=fmt,
        original_text=text,
        error_contains="BAD_OPTION",
    )
    via_file = reduce_file(broken_yaml, oracle_bad_cmd, error_contains="BAD_OPTION")
    assert via_data.reduced == via_file.reduced


def test_reduce_data_refuses_passing_baseline(oracle_ok_cmd: str, broken_yaml: Path):
    data, fmt, text = load(broken_yaml)
    with pytest.raises(BaselineNotInteresting):
        reduce_data(data, oracle_ok_cmd, fmt=fmt, original_text=text)


def test_public_parse_error_is_exported():
    with pytest.raises(ParseError):
        loads("{", "json")


def test_reduce_data_dumps_when_original_text_omitted(
    broken_yaml: Path, oracle_bad_cmd: str
):
    data, fmt, _text = load(broken_yaml)
    result = reduce_data(data, oracle_bad_cmd, fmt=fmt, error_contains="BAD_OPTION")
    assert result.reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert loads(result.reduced_text, fmt) == result.reduced
    assert dumps(result.reduced, fmt) == result.reduced_text


def test_reduce_file_with_extra_env(tmp_path: Path):
    script = tmp_path / "env_oracle.py"
    script.write_text(
        "import os, sys\n"
        "if os.environ.get('CHECK_VAR') == 'ACTIVE':\n"
        "    sys.stderr.write('FOUND_ENV\\n')\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    src = tmp_path / "test.yaml"
    src.write_text("keep: 1\ndrop: 2\n", encoding="utf-8")
    cmd = f'"{sys.executable}" "{script}" {{}}'
    res = reduce_file(src, cmd, error_contains="FOUND_ENV", extra_env={"CHECK_VAR": "ACTIVE"})
    assert res.final_exit_code == 1

