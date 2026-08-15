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
    elif cmd in ("templates", "expand-rules"):
        print(json.dumps(pipeline.build_templates(), indent=2))
    elif cmd == "build":
        pipeline.run()
        print(json.dumps(pipeline.build_templates(), indent=2))
    elif cmd == "validate":
        print(json.dumps(pipeline.validate(), indent=2))
    elif cmd == "schemas":
        print(json.dumps(pipeline.export_schemas(), indent=2))
    elif cmd == "build-tasks":
        from . import phase3
        print(json.dumps(phase3.build_tasks(), indent=2))
    elif cmd == "build-prompt":
        from . import phase3
        print(phase3.build_prompt(argv[1]))
    elif cmd == "ingest":
        from . import phase3
        print(json.dumps(phase3.ingest(), indent=2))
    elif cmd == "reconcile":
        from . import phase3
        print(json.dumps(phase3.reconcile(), indent=2))
    elif cmd == "apply-dispositions":
        from . import phase3
        print(json.dumps(phase3.apply_dispositions(), indent=2))
    elif cmd == "finalize-faces":
        from . import phase3
        print(json.dumps(phase3.finalize_faces(), indent=2))
    elif cmd == "assemble":
        from . import assemble
        stats = assemble.assemble()
        stats.pop("_violations", None)
        print(json.dumps(stats, indent=2))
    elif cmd == "project":
        from . import project
        print(json.dumps(project.project(), indent=2))
    elif cmd == "audit-candidates":
        from . import audit
        print(json.dumps(audit.build_candidates(), indent=2))
    elif cmd == "audit-batches":
        from . import audit
        print(json.dumps(audit.build_batches(), indent=2))
    elif cmd == "audit-ingest":
        from . import audit
        print(json.dumps(audit.ingest(), indent=2))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
