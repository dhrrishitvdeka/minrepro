# Contributing to minrepro

Thanks for improving minrepro.

## Development setup

```bash
# from the repository root
python -m venv .venv

# Windows
.venv\Scripts\activate
# POSIX
# source .venv/bin/activate

pip install -e ".[dev]"
pytest
```

Requires Python 3.10 or newer.

## Project layout

```
src/minrepro/     # installable package (CLI + library)
  cli.py          # argparse entry point
  parse.py        # JSON/YAML load and dump
  model.py        # tree paths, delete key/item, candidates
  oracle.py       # external command and predicates
  shrink.py       # multi-pass greedy structural reduction
  report.py       # Markdown reduction report
examples/         # demo configs and portable Python oracles
tests/            # pytest suite against shipped code
```

## Running the demo

```bash
minrepro examples/broken.yaml \
  --test "python examples/oracle_bad_option.py {}" \
  --error-contains BAD_OPTION
```

Use `py` or `python3` if that is how your platform invokes Python.

## Coding guidelines

- Prefer pure functions for tree ops and predicates so tests can call them directly.
- Keep the CLI thin: parse args, validate baseline, shrink, write artifacts.
- Do not mock the unit under test. External oracle scripts are fine.
- Support Windows and Linux natively: close temp files before the oracle re-opens them; quote `{}` with host rules (`cmd` vs `sh`); write UTF-8 with LF; use `scripts/ci_smoke.py` for shell-free smoke tests.

- Stay in v0.1 scope unless fixing a bug: JSON-compatible JSON/YAML only; key and list-item deletion; exit-code and message predicates; Markdown report.
- Decode oracle process output as UTF-8 with `errors="replace"` so invalid bytes never wipe the message stream.

## Pull requests

1. Add or update tests that fail without your change and pass with it.
2. Run `pytest` and keep it green.
3. Update `README.md` and `CHANGELOG.md` when behavior or flags change.
4. Keep commits focused; explain why in the PR description.

## Reporting bugs

Include:

- minrepro version (`minrepro --version`)
- OS and Python version
- A minimal config (or the reduced output from the tool)
- The exact `--test` command and predicates
- Full stderr from minrepro

## License

By contributing, you agree that your contributions are licensed under the MIT License (see `LICENSE`).
