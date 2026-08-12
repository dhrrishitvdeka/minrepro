"""External failure oracle: run a user command against a candidate config."""

from __future__ import annotations

import math
import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_DISTINCTIVE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
_STOPWORDS = frozenset(
    {
        "error",
        "errors",
        "failed",
        "failure",
        "invalid",
        "unknown",
        "unexpected",
        "validating",
        "validation",
        "cannot",
        "could",
        "from",
        "with",
        "this",
        "that",
        "file",
        "line",
        "json",
        "yaml",
        "config",
        "option",
        "field",
        "missing",
        "required",
        "empty",
        "null",
        "none",
        "true",
        "false",
        "command",
        "usage",
        "exit",
        "code",
        "trace",
        "warning",
        "stderr",
        "stdout",
        "exception",
        "value",
        "type",
        "object",
        "mapping",
        "sequence",
        "document",
        "parse",
        "parser",
        "syntax",
        "found",
        "expected",
        "apply",
        "resource",
        "resources",
    }
)


class OracleError(RuntimeError):
    """Oracle configuration or execution problems that are not test failures."""


class BaselineNotInteresting(OracleError):
    """The original document does not match the failure predicates."""


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
        if self.timeout is not None:
            if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)):
                raise OracleError("timeout must be a number of seconds")
            if not math.isfinite(float(self.timeout)) or float(self.timeout) < 0:
                raise OracleError(
                    "timeout must be a non-negative finite number (None = no timeout)"
                )
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
    config_path: str = ""


def quote_path_for_shell(path: Path) -> str:
    """Quote a filesystem path for the host default shell (Windows and POSIX).

    - Resolves to an absolute path so relative names and cwd do not drift.
    - Windows (cmd.exe via CreateProcess shell=True): double quotes, strip
      embedded `"`, and double `%` so `%VAR%` is not expanded.
    - POSIX (sh/bash): shlex.quote (safe single-quote form).
    """
    try:
        absolute = path if path.is_absolute() else path.resolve()
    except OSError:
        absolute = path
    s = os.fspath(absolute)
    if os.name == "nt":
        s = s.replace('"', "")
        s = s.replace("%", "%%")
        return f'"{s}"'
    return shlex.quote(s)


def decode_process_bytes(data: bytes | str | None) -> str:
    """Decode oracle stdout/stderr without raising on invalid UTF-8."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def path_text_variants(path: Path | str) -> list[str]:
    """Spellings of a path that tools commonly echo (full, posix, basename)."""
    raw = os.fspath(path)
    variants = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
    try:
        p = Path(raw)
        variants.add(p.name)
        variants.add(str(p))
        if p.is_absolute():
            variants.add(os.fspath(p))
    except (OSError, ValueError):
        pass
    quoted: set[str] = set()
    for item in variants:
        if not item:
            continue
        quoted.add(item)
        quoted.add(f'"{item}"')
        quoted.add(f"'{item}'")
    # Longest first so a full path is stripped before its basename.
    return sorted((v for v in quoted if v), key=len, reverse=True)


def normalize_oracle_output(output: str, config_path: Path | str | None = None) -> str:
    """Strip the candidate path and collapse whitespace for signature compare."""
    text = output
    if config_path is not None:
        for variant in path_text_variants(config_path):
            text = text.replace(variant, "<PATH>")
    return " ".join(text.split())


def _distinctive_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _DISTINCTIVE_TOKEN.findall(text):
        if match.lower() in _STOPWORDS:
            continue
        tokens.add(match)
    return tokens


def _strong_tokens(tokens: set[str]) -> set[str]:
    strong: set[str] = set()
    for token in tokens:
        if "_" in token or token.isupper():
            strong.add(token)
            continue
        if any(c.isupper() for c in token[1:]) and any(c.islower() for c in token):
            strong.add(token)
    return strong


def is_same_failure(baseline_norm: str, trial_norm: str) -> bool:
    """True when trial output still carries the baseline failure identity."""
    if not baseline_norm:
        return True
    if baseline_norm in trial_norm or trial_norm in baseline_norm:
        return True
    base_tokens = _distinctive_tokens(baseline_norm)
    trial_tokens = _distinctive_tokens(trial_norm)
    strong = _strong_tokens(base_tokens)
    if strong:
        return strong <= trial_tokens
    if base_tokens:
        return bool(base_tokens & trial_tokens)
    return False


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def _run_shell_command(
    cmd: str,
    *,
    shell: bool,
    timeout: float | None,
) -> tuple[int | None, bytes, bytes, bool]:
    """Run the oracle command with stdin closed and a killable process group."""
    popen_kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        create = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen_kwargs["creationflags"] = create
    else:
        popen_kwargs["start_new_session"] = True

    if shell:
        proc = subprocess.Popen(cmd, shell=True, **popen_kwargs)  # type: ignore[call-overload]
    else:
        argv = shlex.split(cmd, posix=(os.name != "nt"))
        proc = subprocess.Popen(argv, shell=False, **popen_kwargs)  # type: ignore[call-overload]

    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(proc)
        stdout, stderr = proc.communicate()
    return proc.returncode, stdout or b"", stderr or b"", timed_out


class Oracle:
    def __init__(self, config: OracleConfig) -> None:
        self.config = config
        config.validate()
        self._regex = config.compiled_regex()
        self.runs = 0
        self._baseline_norm: str | None = None
        self._pinned = False

    def pin_baseline(self, result: OracleResult, config_path: Path | str | None = None) -> None:
        """Remember the baseline failure so later trials must match it."""
        path = config_path if config_path is not None else result.config_path
        self._baseline_norm = normalize_oracle_output(result.output, path)
        self._pinned = True

    def run(self, config_path: Path) -> OracleResult:
        self.runs += 1
        try:
            absolute = config_path if config_path.is_absolute() else config_path.resolve()
        except OSError:
            absolute = config_path
        path_key = os.fspath(absolute)
        cmd = self._render_command(absolute)
        start = time.perf_counter()
        exit_code, stdout, stderr, timed_out = _run_shell_command(
            cmd,
            shell=self.config.shell,
            timeout=self.config.timeout,
        )
        output = _combine(
            decode_process_bytes(stdout),
            decode_process_bytes(stderr),
        )
        if timed_out:
            output = output + ("\n" if output and not output.endswith("\n") else "")
            output += "[minrepro] command timed out"
        duration = time.perf_counter() - start

        if timed_out:
            return OracleResult(
                interesting=False,
                exit_code=exit_code,
                output=output,
                duration=duration,
                timed_out=True,
                reason="timeout (not treated as interesting failure)",
                config_path=path_key,
            )

        interesting, reason = self._is_interesting(exit_code, output, path_key)
        return OracleResult(
            interesting=interesting,
            exit_code=exit_code,
            output=output,
            duration=duration,
            timed_out=False,
            reason=reason,
            config_path=path_key,
        )

    def _render_command(self, config_path: Path) -> str:
        path_str = quote_path_for_shell(config_path)
        # Replace only the first {} so accidental braces in the command stay put.
        return self.config.command.replace("{}", path_str, 1)

    def _is_interesting(
        self, exit_code: int | None, output: str, config_path: str
    ) -> tuple[bool, str]:
        cfg = self.config

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

        if self._pinned:
            trial_norm = normalize_oracle_output(output, config_path)
            if not is_same_failure(self._baseline_norm or "", trial_norm):
                return False, "failure signature differs from baseline"
            parts.append("same failure as baseline")

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
        raise BaselineNotInteresting(
            "baseline config is not interesting under the given predicates.\n"
            f"  exit_code={result.exit_code}\n"
            f"  reason={result.reason}\n"
            f"  output (last 500 chars):\n{result.output[-500:]}"
        )
    oracle.pin_baseline(result, config_path)
    return result
