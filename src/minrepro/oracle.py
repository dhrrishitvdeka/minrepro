"""External failure oracle: run a user command against a candidate config."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class OracleError(RuntimeError):
    """Oracle configuration or execution problems that are not test failures."""


@dataclass(frozen=True)
class OracleConfig:
    """How to decide whether a candidate still exhibits the target failure."""

    command: str
    """Shell command with `{}` placeholder for the config path."""

    exit_code: int | None = None
    """If set, require this exact exit code. If None, any non-zero is a failure."""

    error_contains: str | None = None
    """If set, require this substring in combined stdout+stderr (case-sensitive)."""

    error_regex: str | None = None
    """If set, require this regex to match combined stdout+stderr."""

    timeout: float | None = 60.0
    """Seconds before killing the command. None = no timeout."""

    shell: bool = True
    """Run via the system shell (cmd.exe on Windows, /bin/sh on Linux/macOS)."""

    def compiled_regex(self) -> re.Pattern[str] | None:
        if self.error_regex is None:
            return None
        try:
            return re.compile(self.error_regex)
        except re.error as exc:
            raise OracleError(f"invalid --error-regex: {exc}") from exc

    def validate(self) -> None:
        """Raise OracleError if the command string is not usable."""
        if "{}" not in self.command:
            raise OracleError(
                "--test command must contain {} as a placeholder for the config path"
            )
        # Compile regex early so bad patterns fail before any oracle run.
        self.compiled_regex()


@dataclass
class OracleResult:
    interesting: bool
    """True when the candidate still shows the same failure (keep deletion)."""

    exit_code: int | None
    output: str
    duration: float
    timed_out: bool = False
    reason: str = ""


def quote_path_for_shell(path: Path) -> str:
    """Quote a filesystem path for the host default shell (Windows and POSIX).

    - Resolves to an absolute path so relative names and cwd do not drift.
    - Windows (cmd.exe / PowerShell via CreateProcess shell): double quotes.
    - POSIX (sh/bash): shlex.quote (safe single-quote form).
    """
    try:
        absolute = path if path.is_absolute() else path.resolve()
    except OSError:
        absolute = path
    s = os.fspath(absolute)
    if os.name == "nt":
        # cmd.exe quoting: wrap in ", strip embedded " (rare in real paths).
        s = s.replace('"', "")
        return f'"{s}"'
    return shlex.quote(s)


def decode_process_bytes(data: bytes | str | None) -> str:
    """Decode oracle stdout/stderr without raising on invalid UTF-8."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


class Oracle:
    def __init__(self, config: OracleConfig) -> None:
        self.config = config
        config.validate()
        self._regex = config.compiled_regex()
        self.runs = 0

    def run(self, config_path: Path) -> OracleResult:
        self.runs += 1
        cmd = self._render_command(config_path)
        start = time.perf_counter()
        timed_out = False
        try:
            # Capture raw bytes so non-UTF-8 tool output never raises
            # UnicodeDecodeError (which would empty output and false-negative
            # --error-contains / --error-regex).
            if self.config.shell:
                completed = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=False,
                    timeout=self.config.timeout,
                    # Inherit env; use host shell (COMSPEC on Windows, /bin/sh on Unix).
                )
            else:
                # argv form: split with the correct platform rules.
                argv = shlex.split(cmd, posix=(os.name != "nt"))
                completed = subprocess.run(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=False,
                    timeout=self.config.timeout,
                )
            exit_code = completed.returncode
            output = _combine(
                decode_process_bytes(completed.stdout),
                decode_process_bytes(completed.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            output = (
                _combine(
                    decode_process_bytes(exc.stdout),
                    decode_process_bytes(exc.stderr),
                )
                + "\n[minrepro] command timed out"
            )
        duration = time.perf_counter() - start

        if timed_out:
            return OracleResult(
                interesting=False,
                exit_code=exit_code,
                output=output,
                duration=duration,
                timed_out=True,
                reason="timeout (not treated as interesting failure)",
            )

        interesting, reason = self._is_interesting(exit_code, output)
        return OracleResult(
            interesting=interesting,
            exit_code=exit_code,
            output=output,
            duration=duration,
            timed_out=False,
            reason=reason,
        )

    def _render_command(self, config_path: Path) -> str:
        path_str = quote_path_for_shell(config_path)
        # Replace only the first {} so accidental braces in the command stay put.
        return self.config.command.replace("{}", path_str, 1)

    def _is_interesting(self, exit_code: int, output: str) -> tuple[bool, str]:
        cfg = self.config

        # Exit-code predicate
        if cfg.exit_code is not None:
            if exit_code != cfg.exit_code:
                return False, f"exit code {exit_code} != required {cfg.exit_code}"
            exit_reason = f"exit code {exit_code}"
        else:
            if exit_code == 0:
                return False, "exit code 0 (success)"
            exit_reason = f"non-zero exit code {exit_code}"

        parts: list[str] = [exit_reason]

        if cfg.error_contains is not None:
            if cfg.error_contains not in output:
                return False, f"output missing required text {cfg.error_contains!r}"
            parts.append(f"contains {cfg.error_contains!r}")

        if self._regex is not None:
            if not self._regex.search(output):
                return False, f"output does not match /{cfg.error_regex}/"
            parts.append(f"matches /{cfg.error_regex}/")

        return True, "; ".join(parts)


def _combine(stdout: str, stderr: str) -> str:
    chunks: list[str] = []
    if stdout:
        chunks.append(stdout if stdout.endswith("\n") else stdout + "\n")
    if stderr:
        chunks.append(stderr if stderr.endswith("\n") else stderr + "\n")
    return "".join(chunks)


def validate_baseline(oracle: Oracle, config_path: Path) -> OracleResult:
    """Ensure the original input is interesting before shrinking."""
    result = oracle.run(config_path)
    if not result.interesting:
        raise OracleError(
            "baseline config is not interesting under the given predicates.\n"
            f"  exit_code={result.exit_code}\n"
            f"  reason={result.reason}\n"
            f"  output (last 500 chars):\n{result.output[-500:]}"
        )
    return result
