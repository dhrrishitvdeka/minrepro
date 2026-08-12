"""Tests for oracle interestingness and command rendering (shipped code)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from minrepro.oracle import (
    Oracle,
    OracleConfig,
    OracleError,
    is_same_failure,
    normalize_oracle_output,
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


def test_oracle_does_not_read_parent_stdin(tmp_path: Path):
    script = tmp_path / "echo_stdin.py"
    script.write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "sys.stderr.write('SAW=' + repr(data) + '\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "c.yaml"
    cfg.write_text("a: 1\n", encoding="utf-8")
    token = "PARENT_STDIN_TOKEN_9f3a"
    cmd = f'"{sys.executable}" "{script}" {{}}'

    import subprocess

    driver = tmp_path / "driver.py"
    driver.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'src')!r})\n"
        "from pathlib import Path\n"
        "from minrepro.oracle import Oracle, OracleConfig\n"
        f"oracle = Oracle(OracleConfig(command={cmd!r}, error_contains='SAW'))\n"
        f"r = oracle.run(Path({str(cfg)!r}))\n"
        "sys.stdout.write(r.output)\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(driver)],
        input=token + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert token not in proc.stdout
    assert "SAW=''" in proc.stdout or "SAW=" in proc.stdout
    assert token not in proc.stdout


def test_timeout_is_not_interesting(tmp_path: Path):
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("a: 1\n", encoding="utf-8")
    cmd = f'"{sys.executable}" "{script}" {{}}'
    oracle = Oracle(OracleConfig(command=cmd, timeout=0.3))
    result = oracle.run(cfg)
    assert result.timed_out is True
    assert result.interesting is False
    assert "timeout" in result.reason


def test_invalid_timeout_rejected():
    with pytest.raises(OracleError, match="timeout"):
        Oracle(OracleConfig(command="echo {}", timeout=-1))
    with pytest.raises(OracleError, match="timeout"):
        Oracle(OracleConfig(command="echo {}", timeout=float("nan")))


def test_same_failure_keeps_named_token_rejects_unrelated():
    assert is_same_failure("error unknown option BAD_OPTION", "error unknown option BAD_OPTION")
    assert is_same_failure("error: real-bug", "real-bug extra")
    assert not is_same_failure("error: real-bug", "missing-required")
    assert not is_same_failure("unknown option BAD_OPTION", "missing required field")
    assert not is_same_failure("error: unknown option BUG", "")
    assert not is_same_failure("error: unknown option BUG", "error")
    assert is_same_failure("error: unknown option BUG", "error: unknown option BUG")


def test_normalize_strips_path(tmp_path: Path):
    path = tmp_path / "cfg.yaml"
    raw = f"error validating {path}: unknown field BAD_OPTION\n"
    norm = normalize_oracle_output(raw, path)
    assert path.name not in norm or "<PATH>" in norm
    assert "BAD_OPTION" in norm


def test_validate_baseline_pins_failure(oracle_bad_cmd: str, broken_yaml: Path):
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    r = validate_baseline(oracle, broken_yaml.resolve())
    assert r.interesting is True
    assert oracle._pinned is True


def test_quote_percent_on_windows():
    import os

    if os.name != "nt":
        pytest.skip("Windows % escaping")
    q = quote_path_for_shell(Path(r"C:\Users\x\%PATH%.yaml"))
    assert "%%PATH%%" in q
    assert q.startswith('"') and q.endswith('"')
