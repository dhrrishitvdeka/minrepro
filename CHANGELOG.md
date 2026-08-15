# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-08-16

### Added

- `--inplace` (`-i`) CLI flag to overwrite the input file directly with the reduced configuration.
- `--diff` (`-d`) CLI flag to display a syntax-highlighted unified diff of all removed structure.
- `--check` CLI flag for dry-run baseline validation without running the shrink loop.
- `--env` (`-e KEY=VALUE`) CLI option and `extra_env` API parameter to pass custom environment variables to test subprocesses.
- `generate_diff` exported in public API and automated `## Structural Diff` section added to Markdown reduction reports.
- `detect_format` optimized to accept optional `text` to prevent redundant file reads and handle UTF-8 BOMs consistently.
- `dumps` now supports custom `indent` parameter across both JSON and YAML.

### Fixed

- Same-failure matching token overlap logic refined to prevent rejection of valid sub-structure prunings.
- Same-failure matching no longer treats empty or generic trial output (`""`, `"error"`) as a match just because it is a substring of the baseline message. A silent exit-1 empty document is rejected; the original failure identity must still appear.


## [0.2.0] - 2026-08-13

### Changed

- Library API: `reduce_file` and `reduce_data` run the same load → oracle → shrink path as the CLI.
- Baseline is required on the library shrink path (`BaselineNotInteresting` if the original does not match).
- Trials are kept only when they still show the **same** failure as the baseline (an emptied document with a different error is rejected).
- YAML 1.1 bool-word mapping keys (`on`, `off`, `yes`, `no`, …) stay those string keys after load+dump (GitHub Actions `on:` is not rewritten as `true:`).
- Non-finite JSON/YAML numbers (`NaN`, `Infinity`, `.nan`, `.inf`) are rejected at parse time.
- Oracle child processes inherit a closed stdin; Windows `%VAR%` in `{}` paths is not expanded by `cmd.exe`.
- Timeouts kill the oracle process tree. Timeouts remain non-interesting.
- Report “removed” percents use `100 * (before - after) / before` on the same UTF-8 byte, line, and node counts printed in the table.
- Package version is `0.2.0`.

### Notes

- Prefer `--error-contains` / `--error-regex` to pin the message you want minimized.
- YAML anchors/aliases/merge keys are still not preserved (resolved into a plain tree).

## [0.1.0] - 2026-07-26

### Added

- CLI `minrepro` for structure-aware reduction of failing JSON and YAML configs.
- External failure oracle via `--test` with `{}` path placeholder.
- Predicates: default any non-zero exit, exact `--exit-code`, `--error-contains`, `--error-regex`.
- Structural deletions only: mapping keys and sequence items (any nesting depth).
- Multi-pass greedy shrink preferring larger subtrees first; keep only interesting trials.
- Markdown reduction report (default `<input>.minrepro.md`) with sizes, kept and rejected steps, and reduced document.
- Library API: `parse`, `oracle`, `shrink`, `report`.
- Examples: `examples/broken.yaml`, `examples/broken.json`, `examples/oracle_bad_option.py`.
- Pytest suite covering model, parse, oracle, shrink, report, and CLI entry paths.

### Notes

- Timeouts are never treated as interesting failures.
- v0.1 does not support TOML/XML, YAML anchors/merge keys, multi-doc streams, or comment preservation.
- Inputs must be JSON-compatible YAML/JSON (no date/datetime/binary/sets/custom tags).
- Oracle stdout/stderr is decoded as UTF-8 with replacement (invalid bytes do not crash predicates).

## Links

- Repository: https://github.com/dhrrishitvdeka/minrepro
- Releases: https://github.com/dhrrishitvdeka/minrepro/releases
- Tag for this version: `v0.2.1`
