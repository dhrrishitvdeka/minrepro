"""Tests for Markdown reduction report generation."""

from __future__ import annotations

from pathlib import Path

from minrepro.model import ReductionEvent, ReductionResult
from minrepro.report import render_markdown


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
