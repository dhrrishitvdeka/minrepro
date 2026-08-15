"""Markdown reduction reports."""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path

from minrepro.model import ReductionResult, count_stats


def utf8_size(text: str) -> int:
    """Byte length of text encoded as UTF-8."""
    return len(text.encode("utf-8"))


def line_count(text: str) -> int:
    """Number of lines, counting a final partial line without a trailing newline."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def removed_percent(before: int, after: int) -> str:
    """Share of ``before`` removed, ``100 * (before - after) / before``.

    Returns ``n/a`` when ``before`` is 0 so callers never divide by zero.
    """
    if before == 0:
        return "n/a"
    removed = 100.0 * (before - after) / before
    return f"{removed:.1f}%"


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def generate_diff(
    original_text: str,
    reduced_text: str,
    from_file: str = "original",
    to_file: str = "reduced",
) -> str:
    """Generate a unified diff between original and reduced text."""
    orig_lines = original_text.splitlines(keepends=True)
    red_lines = reduced_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        red_lines,
        fromfile=from_file,
        tofile=to_file,
    )
    return "".join(diff)


def render_markdown(
    result: ReductionResult,
    *,
    input_path: Path,
    output_path: Path | None,
    test_command: str,
    predicates: dict[str, str | int | None],
) -> str:
    orig_stats = count_stats(result.original)
    red_stats = count_stats(result.reduced)
    orig_bytes = utf8_size(result.original_text)
    red_bytes = utf8_size(result.reduced_text)
    orig_lines = line_count(result.original_text)
    red_lines = line_count(result.reduced_text)

    kept = [e for e in result.events if e.kept]
    rejected = [e for e in result.events if not e.kept]

    lines: list[str] = [
        "# minrepro reduction report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## Summary",
        "",
        f"| Metric | Original | Reduced | Removed |",
        f"| --- | ---: | ---: | ---: |",
        f"| Bytes | {orig_bytes} | {red_bytes} | {removed_percent(orig_bytes, red_bytes)} |",
        f"| Lines | {orig_lines} | {red_lines} | {removed_percent(orig_lines, red_lines)} |",
        f"| Nodes | {orig_stats.nodes} | {red_stats.nodes} | {removed_percent(orig_stats.nodes, red_stats.nodes)} |",
        f"| Mapping keys | {orig_stats.keys} | {red_stats.keys} | {removed_percent(orig_stats.keys, red_stats.keys)} |",
        f"| Sequence items | {orig_stats.items} | {red_stats.items} | {removed_percent(orig_stats.items, red_stats.items)} |",
        "",
        f"- **Input:** `{input_path}`",
        f"- **Output:** `{output_path if output_path else '(stdout / not written)'}`",
        f"- **Format:** {result.format}",
        f"- **Oracle runs:** {result.oracle_runs} "
        f"({result.interesting_runs} deletions kept)",
        f"- **Wall time:** {result.duration_seconds:.2f}s",
        f"- **Stopped:** {result.stopped_reason}",
        f"- **Final exit code:** {result.final_exit_code}",
        "",
        "## Oracle",
        "",
        "```",
        test_command,
        "```",
        "",
        "### Predicates",
        "",
    ]

    for key, value in predicates.items():
        lines.append(f"- `{key}`: `{value}`")

    diff_text = generate_diff(
        result.original_text,
        result.reduced_text,
        from_file=str(input_path),
        to_file=str(output_path) if output_path else "reduced",
    )
    if diff_text:
        lines.extend(
            [
                "",
                "## Structural Diff",
                "",
                "```diff",
                diff_text.rstrip("\n"),
                "```",
            ]
        )

    lines.extend(
        [
            "",
            "## Deletions kept",
            "",
        ]
    )
    if not kept:
        lines.append("_No structural deletions were accepted._")
    else:
        lines.append("| Step | Kind | Path | Bytes | Reason |")
        lines.append("| ---: | --- | --- | ---: | --- |")
        for e in kept:
            delta = f"{e.bytes_before}->{e.bytes_after}"
            lines.append(
                f"| {e.step} | {e.kind} | `{_md_cell(e.path)}` | {delta} | {_md_cell(e.reason)} |"
            )

    lines.extend(
        [
            "",
            f"## Attempts rejected ({len(rejected)})",
            "",
        ]
    )
    if not rejected:
        lines.append("_None._")
    else:
        # Cap long lists in the report
        show = rejected[:50]
        lines.append("| Step | Kind | Path | Reason |")
        lines.append("| ---: | --- | --- | --- |")
        for e in show:
            lines.append(
                f"| {e.step} | {e.kind} | `{_md_cell(e.path)}` | {_md_cell(e.reason)} |"
            )
        if len(rejected) > 50:
            lines.append(f"| ... | ... | ... | _({len(rejected) - 50} more omitted)_ |")

    lines.extend(
        [
            "",
            "## Reduced configuration",
            "",
            f"```{result.format}",
            result.reduced_text.rstrip("\n"),
            "```",
            "",
            "## Final oracle output (truncated)",
            "",
            "```",
            (result.final_output or "").rstrip()[-2000:] or "(empty)",
            "```",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
