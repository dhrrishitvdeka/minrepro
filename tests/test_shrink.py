"""Tests for structure-aware shrinker keep/reject logic (shipped Shrinker)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from minrepro import reduce_data
from minrepro.model import count_stats
from minrepro.oracle import BaselineNotInteresting, Oracle, OracleConfig
from minrepro.parse import dumps, load, loads
from minrepro.shrink import Shrinker


def test_shrink_yaml_keeps_bad_option_removes_unrelated(
    broken_yaml: Path, oracle_bad_cmd: str
):
    data, fmt, text = load(broken_yaml)
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, fmt, suffix=".yaml").shrink(data, text)

    reduced = result.reduced
    assert isinstance(reduced, dict)
    # Still valid YAML when dumped
    reparsed = loads(result.reduced_text, "yaml")
    assert reparsed == reduced

    # BAD_OPTION remains
    env = reduced["services"]["backend"]["environment"]
    assert env.get("BAD_OPTION") is True

    # Unrelated service gone
    assert "frontend" not in reduced["services"]

    # Unrelated keys under backend/environment preferably gone
    assert "DATABASE_URL" not in env
    assert "CACHE_URL" not in env
    assert "volumes" not in reduced["services"]["backend"]
    assert "image" not in reduced["services"]["backend"]

    # Smaller structurally
    assert count_stats(reduced).nodes < count_stats(data).nodes
    assert len(result.reduced_text.encode("utf-8")) < len(text.encode("utf-8"))
    assert result.interesting_runs >= 1
    assert result.oracle_runs >= result.interesting_runs
    assert any(e.kept for e in result.events)
    assert result.stopped_reason in {"fixed-point", "nothing-left-to-remove"}


def test_shrink_json(broken_json: Path, oracle_bad_cmd: str):
    data, fmt, text = load(broken_json)
    assert fmt == "json"
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, fmt, suffix=".json").shrink(data, text)
    reduced = loads(result.reduced_text, "json")
    assert reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert "frontend" not in reduced["services"]


def test_reject_deletion_that_removes_failure(tmp_path: Path, oracle_bad_cmd: str):
    """When only BAD_OPTION remains, further deletions must be rejected."""
    data = {"services": {"backend": {"environment": {"BAD_OPTION": True}}}}
    text = dumps(data, "yaml")
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, "yaml", suffix=".yaml").shrink(data, text)
    # Cannot remove BAD_OPTION or the path that holds it without losing the failure
    assert result.reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    # Either no kept deletions, or kept only truly optional structure (none here)
    assert result.reduced_text  # non-empty


def test_max_steps_stops_early(broken_yaml: Path, oracle_bad_cmd: str):
    data, fmt, text = load(broken_yaml)
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, fmt, suffix=".yaml", max_steps=1).shrink(data, text)
    assert result.stopped_reason == "max-steps"
    assert len(result.events) == 1


def test_final_exit_reflects_last_interesting_not_last_reject(
    broken_yaml: Path, oracle_bad_cmd: str
):
    data, fmt, text = load(broken_yaml)
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, fmt, suffix=".yaml").shrink(data, text)
    # After fixpoint, many rejects are exit 0; final_* must stay on interesting failure.
    assert result.interesting_runs >= 1
    assert result.final_exit_code == 1
    assert "BAD_OPTION" in (result.final_output or "")


def test_root_kind_preserved_sequence(tmp_path: Path):
    """List root stays a list after item deletion."""
    # Fail if list still contains the string "bad"
    oracle_script = tmp_path / "list_oracle.py"
    oracle_script.write_text(
        "import sys, json, pathlib\n"
        "p = pathlib.Path(sys.argv[1])\n"
        "text = p.read_text(encoding='utf-8')\n"
        "try:\n"
        "  import yaml\n"
        "  data = yaml.safe_load(text)\n"
        "except Exception:\n"
        "  data = json.loads(text)\n"
        "if isinstance(data, list) and 'bad' in data:\n"
        "  print('found bad', file=sys.stderr); sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    cmd = f'"{sys.executable}" "{oracle_script}" {{}}'
    data = ["good", "bad", "also-good"]
    text = dumps(data, "yaml")
    oracle = Oracle(OracleConfig(command=cmd, error_contains="found bad"))
    result = Shrinker(oracle, "yaml", suffix=".yaml").shrink(data, text)
    assert isinstance(result.reduced, list)
    assert result.reduced == ["bad"]


def test_passing_config_does_not_invent_empty_failure(tmp_path: Path):
    script = tmp_path / "fail_empty.py"
    script.write_text(
        "import sys, pathlib\n"
        "text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').strip()\n"
        "if text in ('{}', '[]', ''):\n"
        "    print('empty-fail', file=sys.stderr); sys.exit(1)\n"
        "print('ok'); sys.exit(0)\n",
        encoding="utf-8",
    )
    cmd = f'"{sys.executable}" "{script}" {{}}'
    data = {"only": 1}
    oracle = Oracle(OracleConfig(command=cmd, error_contains="empty-fail"))
    with pytest.raises(BaselineNotInteresting):
        Shrinker(oracle, "yaml", suffix=".yaml").shrink(data, dumps(data, "yaml"))


def test_does_not_keep_mode_switched_empty_failure(tmp_path: Path):
    script = tmp_path / "two_failures.py"
    script.write_text(
        "import sys, pathlib\n"
        "try:\n"
        "    import yaml\n"
        "    data = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "except Exception as exc:\n"
        "    print('parse', exc); sys.exit(2)\n"
        "if not isinstance(data, dict):\n"
        "    print('not-dict'); sys.exit(1)\n"
        "if data.get('BUG'):\n"
        "    print('real-bug'); sys.exit(1)\n"
        "if 'required' not in data:\n"
        "    print('missing-required'); sys.exit(1)\n"
        "print('ok'); sys.exit(0)\n",
        encoding="utf-8",
    )
    cmd = f'"{sys.executable}" "{script}" {{}}'
    data = {"required": True, "BUG": True, "noise": 1}
    text = dumps(data, "yaml")
    oracle = Oracle(OracleConfig(command=cmd))
    result = Shrinker(oracle, "yaml", suffix=".yaml").shrink(data, text)
    assert result.reduced.get("BUG") is True
    assert result.reduced != {}
    assert "real-bug" in (result.final_output or "")
    assert "missing-required" not in (result.final_output or "")


def test_silent_empty_exit_is_not_same_failure(tmp_path: Path):
    """Default any-nonzero must not keep {} just because it exits 1 with no text.

    Oracle prints ``unknown option BUG`` while BUG is present, then silent
    exit 1 on an empty document. The reduced tree must still contain BUG.
    """
    script = tmp_path / "silent_empty.py"
    script.write_text(
        "import sys, pathlib\n"
        "try:\n"
        "    import yaml\n"
        "    data = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "except Exception:\n"
        "    sys.exit(1)\n"
        "if isinstance(data, dict) and data.get('BUG'):\n"
        "    print('unknown option BUG', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "if data == {} or data == [] or data is None:\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    cmd = f'"{sys.executable}" "{script}" {{}}'
    data = {"required": True, "BUG": True, "noise": 1}
    text = dumps(data, "yaml")
    result = reduce_data(data, cmd, fmt="yaml", original_text=text)
    assert result.reduced.get("BUG") is True
    assert result.reduced != {}
    assert "BUG" in (result.final_output or "")


def test_broken_yaml_keeps_bad_option_drops_frontend(
    broken_yaml: Path, oracle_bad_cmd: str
):
    data, fmt, text = load(broken_yaml)
    oracle = Oracle(OracleConfig(command=oracle_bad_cmd, error_contains="BAD_OPTION"))
    result = Shrinker(oracle, fmt, suffix=".yaml").shrink(data, text)
    assert result.reduced["services"]["backend"]["environment"]["BAD_OPTION"] is True
    assert "frontend" not in result.reduced.get("services", {})
