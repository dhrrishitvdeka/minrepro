#!/usr/bin/env python3
"""Cross-platform CI smoke: install assumed; run minrepro via the same interpreter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from minrepro.cli import main as cli_main

    broken = ROOT / "examples" / "broken.yaml"
    oracle = ROOT / "examples" / "oracle_bad_option.py"
    out = ROOT / "reduced.yaml"
    cmd = f'"{sys.executable}" "{oracle}" {{}}'
    print(f"platform={sys.platform} os.name={__import__('os').name}")
    print(f"python={sys.executable}")
    print(f"test-cmd={cmd}")
    rc = cli_main(
        [
            str(broken),
            "--test",
            cmd,
            "--error-contains",
            "BAD_OPTION",
            "--output",
            str(out),
            "--no-report",
            "--quiet",
        ]
    )
    if rc != 0:
        print(f"minrepro failed with exit {rc}", file=sys.stderr)
        return rc
    text = out.read_text(encoding="utf-8")
    print(text)
    if "BAD_OPTION" not in text:
        print("reduced output missing BAD_OPTION", file=sys.stderr)
        return 1
    if "frontend" in text:
        print("reduced output still has frontend", file=sys.stderr)
        return 1
    print("ci_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
