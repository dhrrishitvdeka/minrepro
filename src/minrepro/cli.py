"""Command-line interface for minrepro."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from minrepro import __version__
from minrepro.api import reduce_data
from minrepro.oracle import BaselineNotInteresting, OracleError
from minrepro.parse import ParseError, dump, load
from minrepro.report import render_markdown, utf8_size

console = Console(stderr=True)
out = Console(file=sys.stdout)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="minrepro",
        description=(
            "Shrink a failing JSON/YAML configuration to the smallest structure "
            "that still reproduces the same failure under your test command."
        ),
        epilog=(
            "Example:\n"
            '  minrepro broken.yaml --test "kubectl apply --dry-run=server -f {}" '
            '--error-contains "unknown field"\n'
            '  minrepro app.json --test "my-app --config {}" '
            '--error-contains "unknown option"\n'
            '  minrepro examples/broken.yaml '
            '--test "python examples/oracle_bad_option.py {}" '
            '--error-contains BAD_OPTION'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", type=Path, help="Path to the failing JSON or YAML config")
    p.add_argument(
        "--test",
        "-t",
        required=True,
        metavar="CMD",
        help="Shell command to run; use {} as the config path placeholder",
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write reduced config here (default: <input>.min.<ext>)",
    )
    p.add_argument(
        "--report",
        "-r",
        type=Path,
        default=None,
        help="Write a Markdown reduction report here (default: <input>.minrepro.md)",
    )
    p.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write a Markdown report",
    )
    p.add_argument(
        "--format",
        choices=("json", "yaml"),
        default=None,
        help="Force input format (default: detect from extension/content)",
    )
    p.add_argument(
        "--exit-code",
        type=int,
        default=None,
        metavar="N",
        help="Require this exact exit code (default: any non-zero)",
    )
    p.add_argument(
        "--error-contains",
        metavar="TEXT",
        default=None,
        help="Require this substring in command stdout+stderr",
    )
    p.add_argument(
        "--error-regex",
        metavar="PATTERN",
        default=None,
        help="Require this regex to match command stdout+stderr",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        metavar="SEC",
        help="Per-oracle-run timeout in seconds (default: 60; 0 = no timeout)",
    )
    p.add_argument(
        "--max-steps",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N deletion attempts (for debugging)",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print reduced config to stdout (still writes --output unless --no-output)",
    )
    p.add_argument(
        "--no-output",
        action="store_true",
        help="Do not write a reduced config file",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Less progress output",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"minrepro {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path: Path = args.input
    if not input_path.is_file():
        console.print(f"[red]error:[/red] input not found: {input_path}")
        return 2

    if args.max_steps is not None and args.max_steps < 1:
        console.print("[red]error:[/red] --max-steps must be >= 1")
        return 2

    try:
        data, fmt, original_text = load(input_path, args.format)
    except (ParseError, OSError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        return 2

    timeout = None if args.timeout == 0 else args.timeout

    def progress(msg: str) -> None:
        if not args.quiet:
            console.print(f"[dim]{msg}[/dim]")

    if not args.quiet:
        console.print(
            Panel.fit(
                f"[bold]minrepro[/bold] v{__version__}\n"
                f"input: {input_path}\n"
                f"format: {fmt}\n"
                f"test: {args.test}",
                title="structure-aware config shrinker",
                border_style="cyan",
            )
        )
        console.print("[cyan]validating baseline...[/cyan]")

    suffix = input_path.suffix if input_path.suffix else f".{fmt}"
    try:
        result = reduce_data(
            data,
            args.test,
            fmt=fmt,
            original_text=original_text,
            exit_code=args.exit_code,
            error_contains=args.error_contains,
            error_regex=args.error_regex,
            timeout=timeout,
            max_steps=args.max_steps,
            progress=progress,
            suffix=suffix,
            baseline_path=input_path.resolve(),
        )
    except BaselineNotInteresting as exc:
        console.print(f"[red]error:[/red] {exc}")
        return 1
    except (OracleError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        return 2

    if not args.quiet:
        console.print(
            f"[green]baseline interesting[/green] "
            f"(exit {result.final_exit_code}; shrinking finished)"
        )

    # Default output paths
    if args.no_output:
        output_path = None
    elif args.output is not None:
        output_path = args.output
    else:
        default_ext = input_path.suffix or (".json" if fmt == "json" else ".yaml")
        output_path = input_path.with_name(f"{input_path.stem}.min{default_ext}")

    if output_path is not None:
        try:
            dump(output_path, result.reduced, fmt)
        except OSError as exc:
            console.print(f"[red]error:[/red] could not write output: {exc}")
            return 2
        if not args.quiet:
            console.print(f"[green]wrote reduced config:[/green] {output_path}")

    # Auto-print only when no config file is written and no report is written,
    # or when the user explicitly asked for --stdout.
    write_report = not args.no_report
    if args.stdout or (output_path is None and not write_report):
        text = result.reduced_text
        if not text.endswith("\n"):
            text += "\n"
        sys.stdout.write(text)

    if write_report:
        report_path = args.report
        if report_path is None:
            report_path = input_path.with_name(f"{input_path.stem}.minrepro.md")
        predicates: dict[str, str | int | None] = {
            "exit_code": args.exit_code if args.exit_code is not None else "any non-zero",
            "error_contains": args.error_contains,
            "error_regex": args.error_regex,
            "timeout": timeout,
        }
        md = render_markdown(
            result,
            input_path=input_path,
            output_path=output_path,
            test_command=args.test,
            predicates=predicates,
        )
        try:
            report_path.write_text(md, encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] could not write report: {exc}")
            return 2
        if not args.quiet:
            console.print(f"[green]wrote report:[/green] {report_path}")

    if not args.quiet:
        o_bytes = utf8_size(result.original_text)
        r_bytes = utf8_size(result.reduced_text)
        kept = sum(1 for e in result.events if e.kept)
        console.print(
            f"[bold green]done[/bold green] in {result.duration_seconds:.2f}s - "
            f"{o_bytes}->{r_bytes} bytes, {kept} deletions kept, "
            f"{result.oracle_runs} oracle runs ({result.stopped_reason})"
        )
        if not args.stdout and output_path is None and write_report:
            console.print(
                Syntax(result.reduced_text, fmt, theme="monokai", line_numbers=False)
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
