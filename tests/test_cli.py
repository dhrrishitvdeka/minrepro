"""CLI entry-point tests: call shipped minrepro.cli.main with real oracles."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from minrepro.cli import main
from minrepro.parse import load, loads


def test_cli_reduces_yaml_and_writes_report(
    tmp_path: Path, broken_yaml: Path, oracle_bad_cmd: str
):
    # Copy input so default outputs land under tmp_path
    src = tmp_path / "broken.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "reduced.yaml"
    report = tmp_path / "report.md"

    rc = main(
        [
            str(src),
            "--test",
            oracle_bad_cmd,
            "--error-contains",
            "BAD_OPTION",
            "--output",
            str(out),
            "--report",
            str(report),
            "--quiet",
        ]
    )
    assert rc == 0
    assert out.is_file()
    assert report.is_file()

    data = loads(out.read_text(encoding="utf-8"), "yaml")
    assert data["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert "frontend" not in data["services"]

    md = report.read_text(encoding="utf-8")
    assert "minrepro reduction report" in md
    assert "BAD_OPTION" in md


def test_cli_json(tmp_path: Path, broken_json: Path, oracle_bad_cmd: str):
    src = tmp_path / "broken.json"
    src.write_text(broken_json.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "reduced.json"

    rc = main(
        [
            str(src),
            "--test",
            oracle_bad_cmd,
            "--error-contains",
            "BAD_OPTION",
            "--output",
            str(out),
            "--no-report",
            "--quiet",
        ]
    )
    assert rc == 0
    data = loads(out.read_text(encoding="utf-8"), "json")
    assert data["services"]["backend"]["environment"]["BAD_OPTION"] is True


def test_cli_baseline_not_interesting(tmp_path: Path, broken_yaml: Path, oracle_ok_cmd: str):
    src = tmp_path / "broken.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "should_not_matter.yaml"

    rc = main(
        [
            str(src),
            "--test",
            oracle_ok_cmd,
            "--output",
            str(out),
            "--no-report",
            "--quiet",
        ]
    )
    assert rc == 1
    assert not out.exists()


def test_cli_missing_placeholder(tmp_path: Path, broken_yaml: Path):
    src = tmp_path / "broken.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    rc = main([str(src), "--test", "echo no-placeholder", "--quiet", "--no-report"])
    assert rc == 2


def test_cli_invalid_regex(tmp_path: Path, broken_yaml: Path, oracle_bad_cmd: str):
    src = tmp_path / "broken.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    rc = main(
        [
            str(src),
            "--test",
            oracle_bad_cmd,
            "--error-regex",
            "[bad",
            "--quiet",
            "--no-report",
        ]
    )
    assert rc == 2


def test_cli_missing_input(tmp_path: Path, oracle_bad_cmd: str):
    rc = main(
        [
            str(tmp_path / "nope.yaml"),
            "--test",
            oracle_bad_cmd,
            "--quiet",
            "--no-report",
        ]
    )
    assert rc == 2


def test_cli_exit_code_predicate(tmp_path: Path, broken_yaml: Path, oracle_bad_cmd: str):
    src = tmp_path / "broken.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "reduced.yaml"
    rc = main(
        [
            str(src),
            "--test",
            oracle_bad_cmd,
            "--exit-code",
            "1",
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


def test_cli_error_regex(tmp_path: Path, broken_yaml: Path, oracle_bad_cmd: str):
    src = tmp_path / "broken.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "reduced.yaml"
    rc = main(
        [
            str(src),
            "--test",
            oracle_bad_cmd,
            "--error-regex",
            r"BAD_OPTION",
            "--output",
            str(out),
            "--no-report",
            "--quiet",
        ]
    )
    assert rc == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["services"]["backend"]["environment"]["BAD_OPTION"] is True


def test_cli_default_output_names(tmp_path: Path, broken_yaml: Path, oracle_bad_cmd: str):
    src = tmp_path / "app.yaml"
    src.write_text(broken_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    rc = main(
        [
            str(src),
            "--test",
            oracle_bad_cmd,
            "--error-contains",
            "BAD_OPTION",
            "--quiet",
        ]
    )
    assert rc == 0
    assert (tmp_path / "app.min.yaml").is_file()
    assert (tmp_path / "app.minrepro.md").is_file()


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_cli_baseline_with_non_utf8_oracle_output(tmp_path: Path):
    """CLI must treat non-UTF-8 oracle output as interesting when token matches."""
    script = tmp_path / "oracle_bytes.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.buffer.write(b'\\xffBAD_OPTION\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    src = tmp_path / "cfg.yaml"
    src.write_text(
        "services:\n  a:\n    x: 1\n  b:\n    BAD_OPTION: true\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.yaml"
    cmd = f'"{sys.executable}" "{script}" {{}}'
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
    assert rc == 0, "non-UTF-8 oracle output must not fail baseline validation"
    assert out.is_file()
