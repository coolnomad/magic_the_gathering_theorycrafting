"""Acceptance gate #8: the frozen Phase-4/Phase-5 artifacts must stay byte-identical while the
effect-semantics (and any additive) work proceeds. `frozen_manifest.json` pins their sha256."""

import hashlib
import json
import io

from hobkg.pipeline import REPO

MANIFEST = REPO / "data/graph_global/frozen_manifest.json"


def test_frozen_artifacts_match_manifest():
    man = json.load(io.open(MANIFEST, encoding="utf-8"))
    assert man, "frozen manifest is empty"
    for rel, rec in sorted(man.items()):
        b = (REPO / rel).read_bytes()
        assert len(b) == rec["bytes"], f"{rel}: size changed ({len(b)} != {rec['bytes']})"
        assert hashlib.sha256(b).hexdigest() == rec["sha256"], f"{rel}: FROZEN ARTIFACT CHANGED"


def test_manifest_covers_the_core_graph():
    man = json.load(io.open(MANIFEST, encoding="utf-8"))
    for rel in ("data/graph_global/nodes.jsonl", "data/graph_global/edges.jsonl",
                "data/graph_global/conditions.jsonl"):
        assert rel in man
