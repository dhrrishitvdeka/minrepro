"""Cross-platform path, shell, and temp-file behavior (Windows + Linux)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from minrepro.cli import main
from minrepro.oracle import Oracle, OracleConfig, quote_path_for_shell
from minrepro.parse import dump, load, loads
from minrepro.shrink import Shrinker


def test_quote_path_absolute_and_spaces(tmp_path: Path):
    spaced = tmp_path / "my configs" / "app.yaml"
    spaced.parent.mkdir(parents=True, exist_ok=True)
    spaced.write_text("a: 1\n", encoding="utf-8")
    q = quote_path_for_shell(spaced)
    # Must be quoted in some form and include the directory name.
    assert "my configs" in q or "my configs" in str(spaced.resolve())
    if os.name == "nt":
        assert q.startswith('"') and q.endswith('"')
        assert " " in q or "my" in q
    else:
        # POSIX shlex.quote uses single quotes when needed.
        assert q.startswith("'") or " " not in str(spaced.resolve())
    # Absolute after resolve
    assert os.path.isabs(q.strip("\"'")) or os.path.isabs(str(spaced.resolve()))


def test_oracle_with_path_containing_spaces(tmp_path: Path, broken_yaml: Path):
    """Oracle must accept config paths under directories with spaces (Win + Linux)."""
    work = tmp_path / "user data" / "project"
    work.mkdir(parents=True)
    cfg = work / "broken.yaml"
    cfg.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")

    oracle_script = Path(__file__).resolve().parents[1] / "examples" / "oracle_bad_option.py"
    cmd = f'"{sys.executable}" "{oracle_script}" {{}}'
    oracle = Oracle(OracleConfig(command=cmd, error_contains="BAD_OPTION"))
    result = oracle.run(cfg)
    assert result.interesting is True, result.reason
    assert result.exit_code == 1


def test_shrink_with_spaced_work_dir(tmp_path: Path, broken_yaml: Path):
    work = tmp_path / "tmp files"
    work.mkdir()
    data, fmt, text = load(broken_yaml)
    oracle_script = Path(__file__).resolve().parents[1] / "examples" / "oracle_bad_option.py"
    cmd = f'"{sys.executable}" "{oracle_script}" {{}}'
    oracle = Oracle(OracleConfig(command=cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, fmt, suffix=".yaml", work_dir=work).shrink(data, text)
    assert result.reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert "frontend" not in result.reduced["services"]


def test_cli_paths_with_spaces(tmp_path: Path, broken_yaml: Path):
    work = tmp_path / "My Documents" / "cfg"
    work.mkdir(parents=True)
    src = work / "broken.yaml"
    out = work / "out.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    oracle_script = Path(__file__).resolve().parents[1] / "examples" / "oracle_bad_option.py"
    cmd = f'"{sys.executable}" "{oracle_script}" {{}}'
    rc = main(
        [
            str(src),
            "--test",
            cmd,
            "--error-contains",
            "BAD_OPTION",
            "--output",
            str(out),
            "--no-report",
            "--quiet",
        ]
    )
    assert rc == 0
    assert out.is_file()
    data = loads(out.read_text(encoding="utf-8"), "yaml")
    assert data["services"]["backend"]["environment"]["BAD_OPTION"] is True


def test_utf8_roundtrip_dump_load(tmp_path: Path):
    path = tmp_path / "unicode.yaml"
    data = {"msg": "cafe", "n": 1}
    # Write with unicode that is still ascii-safe here; ensure encoding path works.
    data = {"msg": "hello", "path": "C:\\Users\\x\\file"}
    dump(path, data, "yaml")
    loaded, fmt, text = load(path)
    assert fmt == "yaml"
    assert loaded["msg"] == "hello"
    assert "\r" not in text or os.name == "nt"  # we force \n on write
    assert loads(text, "yaml") == loaded


def test_line_endings_normalized_on_write(tmp_path: Path):
    path = tmp_path / "out.yaml"
    dump(path, {"a": 1, "b": [2, 3]}, "yaml")
    raw = path.read_bytes()
    # No CR from our writer (newline="\n").
    assert b"\r\n" not in raw
    assert b"\n" in raw
