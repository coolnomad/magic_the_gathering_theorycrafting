"""Acceptance gate #8: the frozen Phase-4 core-graph artifacts must stay byte-identical while the
effect-semantics (and any additive) work proceeds. `frozen_manifest.json` pins their sha256.

Protected set (per the freeze at HEAD 8201109 / DECISION 25304f0): the CORE graph —
`data/graph/{nodes,edges,conditions,gates}` + `data/graph_global/{nodes,edges,conditions}`. The
additive projection tiers (equip/completeness/lifecycle/mechanism/repair/audit_repair/effect) are
DERIVED and regenerable, not byte-frozen.

Review PHASE1 pt1 finding 3: the manifest itself is PINNED here by digest, so editing an artifact and
regenerating the manifest cannot silently redefine the baseline. Changing MANIFEST_DIGEST is a
sanctioned re-freeze and must be a deliberate, logged decision (INSTRUCTIONS §3)."""

import hashlib
import json
import io

from hobkg.pipeline import REPO

MANIFEST = REPO / "data/graph_global/frozen_manifest.json"
# pinned digest of frozen_manifest.json — changing this is a SANCTIONED RE-FREEZE (log it)
MANIFEST_DIGEST = "f9daef7d0464d7a7a61162c25eaecf5e281ab1a07b004c5215d98f9df6a00dd5"


def test_manifest_itself_is_pinned():
    # defeats the "edit artifact + regenerate manifest" bypass: the manifest content is pinned
    b = MANIFEST.read_bytes()
    assert hashlib.sha256(b).hexdigest() == MANIFEST_DIGEST, \
        "frozen_manifest.json changed — if intentional, this is a sanctioned re-freeze: update " \
        "MANIFEST_DIGEST and log a DECISION in LABNOTEBOOK."


def test_frozen_artifacts_match_manifest():
    man = json.load(io.open(MANIFEST, encoding="utf-8"))
    assert man, "frozen manifest is empty"
    for rel, rec in sorted(man.items()):
        b = (REPO / rel).read_bytes()
        assert len(b) == rec["bytes"], f"{rel}: size changed ({len(b)} != {rec['bytes']})"
        assert hashlib.sha256(b).hexdigest() == rec["sha256"], f"{rel}: FROZEN ARTIFACT CHANGED"


def test_manifest_covers_the_core_graph():
    man = json.load(io.open(MANIFEST, encoding="utf-8"))
    for rel in ("data/graph/nodes.jsonl", "data/graph/edges.jsonl", "data/graph/conditions.jsonl",
                "data/graph/gates.jsonl", "data/graph_global/nodes.jsonl",
                "data/graph_global/edges.jsonl", "data/graph_global/conditions.jsonl"):
        assert rel in man
