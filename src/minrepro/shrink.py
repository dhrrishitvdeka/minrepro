"""Structure-aware config reduction (mapping keys + sequence items)."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from minrepro.model import (
    ReductionEvent,
    ReductionResult,
    delete_at,
    deep_copy,
    iter_deletion_candidates,
)
from minrepro.oracle import BaselineNotInteresting, Oracle, validate_baseline
from minrepro.parse import Format, dumps


ProgressCallback = Callable[[str], None]


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


class Shrinker:
    """Greedy multi-pass hierarchical deletion guided by an external oracle."""

    def __init__(
        self,
        oracle: Oracle,
        fmt: Format,
        *,
        max_steps: int | None = None,
        progress: ProgressCallback | None = None,
        work_dir: Path | str | None = None,
        suffix: str = ".yaml",
    ) -> None:
        if max_steps is not None and max_steps < 1:
            raise ValueError("max_steps must be >= 1 when set")
        self.oracle = oracle
        self.fmt = fmt
        self.max_steps = max_steps
        self.progress = progress or (lambda _msg: None)
        self.work_dir = str(work_dir) if work_dir is not None else None
        self.suffix = suffix if suffix.startswith(".") else f".{suffix}"

    def shrink(
        self,
        data: Any,
        original_text: str,
        *,
        baseline_path: Path | str | None = None,
    ) -> ReductionResult:
        t0 = time.perf_counter()
        current = deep_copy(data)
        events: list[ReductionEvent] = []
        step = 0
        interesting_runs = 0
        final_exit: int | None = None
        final_output = ""
        stopped = "fixed-point"

        if baseline_path is not None:
            baseline = validate_baseline(self.oracle, Path(baseline_path))
        else:
            baseline = self._test(dumps(data, self.fmt))
            if not baseline.interesting:
                raise BaselineNotInteresting(
                    "baseline config is not interesting under the given predicates.\n"
                    f"  exit_code={baseline.exit_code}\n"
                    f"  reason={baseline.reason}\n"
                    f"  output (last 500 chars):\n{baseline.output[-500:]}"
                )
            self.oracle.pin_baseline(baseline)

        final_exit = baseline.exit_code
        final_output = baseline.output

        # Pass until no more deletions succeed (re-scan after each successful delete).
        while True:
            self.progress("scanning for removable keys/items...")
            candidates = list(iter_deletion_candidates(current))
            if not candidates:
                stopped = "nothing-left-to-remove"
                break

            made_progress = False
            i = 0
            while i < len(candidates):
                if self.max_steps is not None and step >= self.max_steps:
                    stopped = "max-steps"
                    break

                cand = candidates[i]
                step += 1
                before_text = dumps(current, self.fmt)
                try:
                    trial = delete_at(current, cand.path)
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    events.append(
                        ReductionEvent(
                            step=step,
                            path=cand.label,
                            kind=cand.kind,
                            kept=False,
                            reason=f"stale path ({exc})",
                            bytes_before=_utf8_len(before_text),
                        )
                    )
                    i += 1
                    continue

                after_text = dumps(trial, self.fmt)
                result = self._test(after_text)

                if result.interesting:
                    # Track the last *interesting* oracle outcome for the report
                    # (rejected trials often exit 0 and would mislead "final exit").
                    final_exit = result.exit_code
                    final_output = result.output
                    interesting_runs += 1
                    current = trial
                    made_progress = True
                    events.append(
                        ReductionEvent(
                            step=step,
                            path=cand.label,
                            kind=cand.kind,
                            kept=True,
                            reason=result.reason,
                            exit_code=result.exit_code,
                            bytes_before=_utf8_len(before_text),
                            bytes_after=_utf8_len(after_text),
                        )
                    )
                    self.progress(
                        f"  step {step}: removed {cand.kind} {cand.label} "
                        f"({_utf8_len(before_text)}->{_utf8_len(after_text)} bytes)"
                    )
                    # Paths changed; rescan from current tree
                    candidates = list(iter_deletion_candidates(current))
                    i = 0
                else:
                    events.append(
                        ReductionEvent(
                            step=step,
                            path=cand.label,
                            kind=cand.kind,
                            kept=False,
                            reason=result.reason,
                            exit_code=result.exit_code,
                            bytes_before=_utf8_len(before_text),
                            bytes_after=_utf8_len(after_text),
                        )
                    )
                    i += 1

            if stopped == "max-steps":
                break
            if not made_progress:
                stopped = "fixed-point"
                break

        reduced_text = dumps(current, self.fmt)
        # Re-check the dumped reduced tree so we never report success for a
        # document that no longer reproduces the pinned baseline failure.
        confirm = self._test(reduced_text)
        if not confirm.interesting:
            raise BaselineNotInteresting(
                "reduced config is no longer interesting under the given predicates.\n"
                f"  exit_code={confirm.exit_code}\n"
                f"  reason={confirm.reason}\n"
                f"  output (last 500 chars):\n{confirm.output[-500:]}"
            )
        final_exit = confirm.exit_code
        final_output = confirm.output

        return ReductionResult(
            original=data,
            reduced=current,
            original_text=original_text,
            reduced_text=reduced_text,
            format=self.fmt,
            events=events,
            oracle_runs=self.oracle.runs,
            interesting_runs=interesting_runs,
            duration_seconds=time.perf_counter() - t0,
            final_exit_code=final_exit,
            final_output=final_output,
            stopped_reason=stopped,
        )

    def _test(self, text: str):
        """Write candidate to a closed temp file, then run the oracle.

        Uses binary UTF-8 writes so Windows and Linux get the same bytes (no
        locale newline translation). File is fully closed before the oracle
        re-opens it (required on Windows exclusive locks).
        """
        fd, name = tempfile.mkstemp(suffix=self.suffix, dir=self.work_dir)
        tmp_path = Path(name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(text.encode("utf-8"))
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            return self.oracle.run(tmp_path)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
