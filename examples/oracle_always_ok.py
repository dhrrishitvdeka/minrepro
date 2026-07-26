#!/usr/bin/env python3
"""Oracle that always succeeds. Used to exercise non-interesting baselines."""

from __future__ import annotations

import sys


def main() -> int:
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
