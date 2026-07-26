"""Markdown reduction reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from minrepro.model import ReductionResult, count_stats


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
    orig_bytes = len(result.original_text.encode("utf-8"))
    red_bytes = len(result.reduced_text.encode("utf-8"))
    orig_lines = result.original_text.count("\n") + (
        0 if result.original_text.endswith("\n") or not result.original_text else 1
    )
    red_lines = result.reduced_text.count("\n") + (
        0 if result.reduced_text.endswith("\n") or not result.reduced_text else 1
    )

    def pct(before: int, after: int) -> str:
        if before == 0:
            return "n/a"
        removed = 100.0 * (before - after) / before
        return f"{removed:.1f}%"

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
        f"| Bytes | {orig_bytes} | {red_bytes} | {pct(orig_bytes, red_bytes)} |",
        f"| Lines | {orig_lines} | {red_lines} | {pct(orig_lines, red_lines)} |",
        f"| Nodes | {orig_stats.nodes} | {red_stats.nodes} | {pct(orig_stats.nodes, red_stats.nodes)} |",
        f"| Mapping keys | {orig_stats.keys} | {red_stats.keys} | {pct(orig_stats.keys, red_stats.keys)} |",
        f"| Sequence items | {orig_stats.items} | {red_stats.items} | {pct(orig_stats.items, red_stats.items)} |",
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
                f"| {e.step} | {e.kind} | `{e.path}` | {delta} | {e.reason} |"
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
            reason = e.reason.replace("|", "\\|")
            lines.append(f"| {e.step} | {e.kind} | `{e.path}` | {reason} |")
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
