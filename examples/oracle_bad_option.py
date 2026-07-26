#!/usr/bin/env python3
"""Demo failure oracle for minrepro.

Fails (exit 1) when the config still contains BAD_OPTION under any nested mapping.
Succeeds (exit 0) once BAD_OPTION has been removed. Used by the README quick start
and automated tests. Portable on Windows and POSIX.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_config(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError:
        # Fallback: treat as JSON if PyYAML is missing
        return json.loads(text)
    return yaml.safe_load(text)


def contains_bad_option(node) -> bool:
    if isinstance(node, dict):
        if "BAD_OPTION" in node:
            return True
        return any(contains_bad_option(v) for v in node.values())
    if isinstance(node, list):
        return any(contains_bad_option(v) for v in node)
    return False


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: oracle_bad_option.py CONFIG", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        data = load_config(path)
    except Exception as exc:  # noqa: BLE001 - surface parse errors to the tool
        print(f"oracle: failed to load {path}: {exc}", file=sys.stderr)
        return 2
    if contains_bad_option(data):
        print("error: unknown option BAD_OPTION", file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
