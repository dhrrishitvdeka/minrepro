"""Tests for oracle interestingness and command rendering (shipped code)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from minrepro.oracle import (
    Oracle,
    OracleConfig,
    OracleError,
    quote_path_for_shell,
    validate_baseline,
)


def test_quote_path_for_shell_wraps(tmp_path: Path):
    import os

    target = tmp_path / "my file.yaml"
    target.write_text("x: 1\n", encoding="utf-8")
    q = quote_path_for_shell(target)
    assert "my file.yaml" in q
    # Host-native quoting: double quotes on Windows, shlex on POSIX.
    if os.name == "nt":
        assert q.startswith('"') and q.endswith('"')
    else:
        assert q.startswith("'") and q.endswith("'")



def test_missing_placeholder_raises():
    with pytest.raises(OracleError, match=r"\{\}"):
        Oracle(OracleConfig(command="echo hi"))


def test_invalid_regex_raises():
    with pytest.raises(OracleError, match="invalid --error-regex"):
        Oracle(OracleConfig(command="echo {}", error_regex="[unterminated"))


def test_default_nonzero_is_interesting(tmp_path: Path, oracle_bad_cmd: str, broken_yaml: Path):
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = oracle.run(broken_yaml.resolve())
    assert result.interesting is True
    assert result.exit_code == 1
    assert "BAD_OPTION" in result.output


def test_success_not_interesting(tmp_path: Path, oracle_ok_cmd: str, broken_yaml: Path):
    oracle = Oracle(OracleConfig(command=oracle_ok_cmd))
    result = oracle.run(broken_yaml.resolve())
    assert result.interesting is False
    assert result.exit_code == 0
    assert "exit code 0" in result.reason


def test_error_contains_required(tmp_path: Path, oracle_bad_cmd: str, broken_yaml: Path):
    oracle = Oracle(
        OracleConfig(command=oracle_bad_cmd, error_contains="THIS_STRING_IS_NEVER_PRINTED")
    )
    result = oracle.run(broken_yaml.resolve())
    assert result.interesting is False
    assert "missing required text" in result.reason


def test_error_regex(tmp_path: Path, oracle_bad_cmd: str, broken_yaml: Path):
    oracle = Oracle(
        OracleConfig(command=oracle_bad_cmd, error_regex=r"unknown option BAD_OPTION")
    )
    result = oracle.run(broken_yaml.resolve())
    assert result.interesting is True


def test_exit_code_exact(tmp_path: Path, oracle_bad_cmd: str, broken_yaml: Path):
    # Oracle returns 1 on bad option
    ok = Oracle(OracleConfig(command=oracle_bad_cmd, exit_code=1))
    assert ok.run(broken_yaml.resolve()).interesting is True

    bad = Oracle(OracleConfig(command=oracle_bad_cmd, exit_code=42))
    r = bad.run(broken_yaml.resolve())
    assert r.interesting is False
    assert "!= required 42" in r.reason


def test_validate_baseline_rejects_ok(oracle_ok_cmd: str, broken_yaml: Path):
    oracle = Oracle(OracleConfig(command=oracle_ok_cmd))
    with pytest.raises(OracleError, match="not interesting"):
        validate_baseline(oracle, broken_yaml.resolve())


def test_validate_baseline_accepts_failure(oracle_bad_cmd: str, broken_yaml: Path):
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    r = validate_baseline(oracle, broken_yaml.resolve())
    assert r.interesting is True


def test_placeholder_substituted_once():
    cfg = OracleConfig(command="tool --cfg {} --note braces-ok")
    oracle = Oracle(cfg)
    rendered = oracle._render_command(Path("/tmp/x.yaml"))
    assert rendered.count("/tmp/x.yaml") == 1 or "x.yaml" in rendered
    assert "braces-ok" in rendered


def test_non_utf8_oracle_output_still_matches_error_contains(tmp_path: Path):
    """Regression: invalid UTF-8 in oracle output must not false-negative predicates.

    Demonstrates the bug class where text=True without errors='replace' can
    raise UnicodeDecodeError and leave --error-contains unmatched.
    """
    script = tmp_path / "oracle_latin1.py"
    # Emit raw non-UTF-8 bytes around the token BAD_OPTION, then exit 1.
    script.write_text(
        "import sys\n"
        "sys.stdout.buffer.write(b'\\xff\\xfeBAD_OPTION\\n')\n"
        "sys.stderr.buffer.write(b'\\x80unknown option\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("a: 1\n", encoding="utf-8")
    cmd = f'"{sys.executable}" "{script}" {{}}'
    oracle = Oracle(OracleConfig(command=cmd, error_contains="BAD_OPTION"))
    result = oracle.run(cfg_path)
    assert result.exit_code == 1
    assert "BAD_OPTION" in result.output
    assert result.interesting is True, result.reason


def test_non_utf8_oracle_matches_error_regex(tmp_path: Path):
    script = tmp_path / "oracle_binary_msg.py"
    script.write_text(
        "import sys\n"
        "sys.stderr.buffer.write(b'\\xff error: BAD_OPTION invalid\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("{}\n", encoding="utf-8")
    cmd = f'"{sys.executable}" "{script}" {{}}'
    oracle = Oracle(OracleConfig(command=cmd, error_regex=r"BAD_OPTION"))
    result = oracle.run(cfg_path)
    assert result.interesting is True, result.reason


def test_decode_process_bytes_replaces_invalid():
    from minrepro.oracle import decode_process_bytes

    assert "BAD_OPTION" in decode_process_bytes(b"\xffBAD_OPTION")
    assert decode_process_bytes(None) == ""
    assert decode_process_bytes("already") == "already"
