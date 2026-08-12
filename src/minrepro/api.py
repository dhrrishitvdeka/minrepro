"""Public end-to-end library entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from minrepro.oracle import Oracle, OracleConfig
from minrepro.parse import Format, dumps, load
from minrepro.shrink import ProgressCallback, Shrinker
from minrepro.model import ReductionResult


def reduce_data(
    data: Any,
    command: str,
    *,
    fmt: Format = "yaml",
    original_text: str | None = None,
    exit_code: int | None = None,
    error_contains: str | None = None,
    error_regex: str | None = None,
    timeout: float | None = 60.0,
    max_steps: int | None = None,
    progress: ProgressCallback | None = None,
    suffix: str | None = None,
    work_dir: Path | str | None = None,
    baseline_path: Path | str | None = None,
    oracle: Oracle | None = None,
) -> ReductionResult:
    """Shrink an already-parsed JSON/YAML tree using a test command.

    The original document must be interesting under the predicates. Trials
    are kept only when they still exhibit that same failure.
    """
    if oracle is None:
        oracle = Oracle(
            OracleConfig(
                command=command,
                exit_code=exit_code,
                error_contains=error_contains,
                error_regex=error_regex,
                timeout=timeout,
            )
        )
    text = original_text if original_text is not None else dumps(data, fmt)
    ext = suffix if suffix is not None else (".json" if fmt == "json" else ".yaml")
    shrinker = Shrinker(
        oracle,
        fmt,
        max_steps=max_steps,
        progress=progress,
        work_dir=work_dir,
        suffix=ext,
    )
    return shrinker.shrink(data, text, baseline_path=baseline_path)


def reduce_file(
    path: Path | str,
    command: str,
    *,
    fmt: Format | None = None,
    exit_code: int | None = None,
    error_contains: str | None = None,
    error_regex: str | None = None,
    timeout: float | None = 60.0,
    max_steps: int | None = None,
    progress: ProgressCallback | None = None,
    suffix: str | None = None,
    work_dir: Path | str | None = None,
    oracle: Oracle | None = None,
) -> ReductionResult:
    """Load a JSON/YAML file and shrink it to the smallest same-failure tree."""
    input_path = Path(path)
    data, resolved, text = load(input_path, fmt)
    ext = suffix
    if ext is None:
        ext = input_path.suffix if input_path.suffix else f".{resolved}"
    return reduce_data(
        data,
        command,
        fmt=resolved,
        original_text=text,
        exit_code=exit_code,
        error_contains=error_contains,
        error_regex=error_regex,
        timeout=timeout,
        max_steps=max_steps,
        progress=progress,
        suffix=ext,
        work_dir=work_dir,
        baseline_path=input_path.resolve(),
        oracle=oracle,
    )
