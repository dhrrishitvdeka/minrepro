# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Tag for this version: `v0.1.0`
