"""Tests for Markdown reduction report generation."""

from __future__ import annotations

from pathlib import Path

from minrepro.model import ReductionEvent, ReductionResult, count_stats
from minrepro.report import line_count, removed_percent, render_markdown, utf8_size


def test_render_markdown_contains_summary_and_reduced():
    original = {"a": 1, "b": {"c": 2}}
    reduced = {"b": {"c": 2}}
    result = ReductionResult(
        original=original,
        reduced=reduced,
        original_text="a: 1\nb:\n  c: 2\n",
        reduced_text="b:\n  c: 2\n",
        format="yaml",
        events=[
            ReductionEvent(
                step=1,
                path="$.a",
                kind="key",
                kept=True,
                reason="non-zero exit code 1",
                exit_code=1,
                bytes_before=20,
                bytes_after=10,
            ),
            ReductionEvent(
                step=2,
                path="$.b.c",
                kind="key",
                kept=False,
                reason="exit code 0 (success)",
                exit_code=0,
                bytes_before=10,
                bytes_after=5,
            ),
        ],
        oracle_runs=3,
        interesting_runs=1,
        duration_seconds=0.12,
        final_exit_code=1,
        final_output="error: boom\n",
        stopped_reason="fixed-point",
    )
    md = render_markdown(
        result,
        input_path=Path("in.yaml"),
        output_path=Path("out.yaml"),
        test_command="tool {}",
        predicates={"exit_code": "any non-zero", "error_contains": None},
    )
    assert md.startswith("# minrepro reduction report")
    assert "## Summary" in md
    assert "in.yaml" in md
    assert "out.yaml" in md
    assert "tool {}" in md
    assert "$.a" in md
    assert "Deletions kept" in md
    assert "Attempts rejected" in md
    assert "```yaml" in md
    assert "b:" in md
    assert "error: boom" in md
    assert "fixed-point" in md

    orig_bytes = utf8_size(result.original_text)
    red_bytes = utf8_size(result.reduced_text)
    orig_lines = line_count(result.original_text)
    red_lines = line_count(result.reduced_text)
    orig_nodes = count_stats(result.original).nodes
    red_nodes = count_stats(result.reduced).nodes
    assert f"| Bytes | {orig_bytes} | {red_bytes} | {removed_percent(orig_bytes, red_bytes)} |" in md
    assert f"| Lines | {orig_lines} | {red_lines} | {removed_percent(orig_lines, red_lines)} |" in md
    assert f"| Nodes | {orig_nodes} | {red_nodes} | {removed_percent(orig_nodes, red_nodes)} |" in md
    expected_bytes_pct = 100.0 * (orig_bytes - red_bytes) / orig_bytes
    assert removed_percent(orig_bytes, red_bytes) == f"{expected_bytes_pct:.1f}%"


def test_removed_percent_arithmetic():
    assert removed_percent(0, 0) == "n/a"
    assert removed_percent(100, 40) == "60.0%"
    assert removed_percent(10, 10) == "0.0%"
    assert removed_percent(8, 10) == "-25.0%"
    assert removed_percent(3, 1) == f"{100.0 * (3 - 1) / 3:.1f}%"


def test_line_count_and_utf8_size():
    assert line_count("") == 0
    assert line_count("a\n") == 1
    assert line_count("a\nb") == 2
    assert line_count("a\nb\n") == 2
    assert utf8_size("é") == len("é".encode("utf-8"))
    assert utf8_size("é") == 2


def test_generate_diff_produces_unified_diff():
    from minrepro.report import generate_diff

    orig = "a: 1\nb: 2\nc: 3\n"
    red = "b: 2\n"
    diff = generate_diff(orig, red, from_file="in.yaml", to_file="out.yaml")
    assert "--- in.yaml" in diff
    assert "+++ out.yaml" in diff
    assert "-a: 1" in diff
    assert "-c: 3" in diff
    assert " b: 2" in diff

