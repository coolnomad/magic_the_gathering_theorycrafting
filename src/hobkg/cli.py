"""Minimal CLI for the Phase 1 pipeline.

Usage:
    python -m hobkg.cli normalize   # run normalization + extraction + reports
    python -m hobkg.cli validate    # reload and re-validate all emitted jsonl
    python -m hobkg.cli schemas      # (re)export JSON Schemas only
"""

from __future__ import annotations

import json
import sys

from . import pipeline


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "normalize"

    if cmd == "normalize":
        stats = pipeline.run()
        print(json.dumps(stats, indent=2))
    elif cmd == "validate":
        print(json.dumps(pipeline.validate(), indent=2))
    elif cmd == "schemas":
        print(json.dumps(pipeline.export_schemas(), indent=2))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
