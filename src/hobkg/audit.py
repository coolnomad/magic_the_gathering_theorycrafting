"""Phase 5 Part 2: pairwise LLM audit — Stage A (deterministic candidate selection).

The mechanical projection (Part 1) covers only pairs with an allowed primitive path.
This stage selects the *bounded* set of card pairs that are LIKELY to hide a
relationship the grammar missed, and packages each for a sub-agent adjudication
(Stage B). We never scan all 37,249 pairs; we emit only pairs matching a signal
bucket, tagged with the evidence and the existing mechanical relations.

Buckets (spec §"Pairwise LLM audit"):
  - participant_unresolved : a Part 1 supply flagged non-asserted (cross-participant)
  - named_reference        : A's Oracle text names card B (proper-noun token)
  - replacement_prevention : A REPLACES/PREVENTS an event/op that B produces/causes
  - copy_effect            : A copies objects (copy interactions are grammar-invisible)
  - ambiguous_scope        : A carries "this way"/"that card/creature/permanent" scope
  - shared_vocabulary      : A,B share a moderately-rare functional concept node but
                             have no asserted mechanical path (lower precision)

Output: `data/graph_global/audit_candidates.jsonl` — one record per ORDERED pair
(source_card, target_card) with its buckets, evidence, and mechanical relations.
Directed buckets fix the orientation; `shared_vocabulary` emits both orientations.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_CONCEPT = ("resource:", "event:", "counter:", "token:", "gate:")
_VOCAB_PREDS = {"PRODUCES", "CONSUMES", "CAUSES", "TRIGGERS", "REQUIRES", "PREVENTS",
                "REPLACES", "REFERENCES_RULE", "QUALIFIES_FOR", "ADDS_COUNTER",
                "REMOVES_COUNTER", "CREATES_OBJECT"}
_STOP = {"the", "of", "a", "to", "and", "you", "your", "this", "that", "with", "for",
         "when", "each", "target", "another", "other", "then", "into", "from"}


def _card_of(nid: str) -> str | None:
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


class _Data:
    def __init__(self, repo: Path):
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        self.edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))
        self.cards = {c["id"]: c for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
        self.faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
        self.proj = list(_load_dicts(repo / "data/graph_global/card_pair_projection.jsonl"))
        self.oracle = defaultdict(str)
        for f in self.faces:
            self.oracle[f["card_id"]] += " " + (f.get("oracle_text") or "")
        self.name = {cid: c["name"] for cid, c in self.cards.items()}
        self.asserted = {(m["source_card"], m["target_card"]) for m in self.proj if m["asserted"]}


class _Cands:
    def __init__(self):
        self.rec: dict[tuple, dict] = {}

    def add(self, a: str, b: str, bucket: str, evidence, directed: bool):
        if a == b and bucket not in ("copy_effect", "named_reference"):
            return
        pairs = [(a, b)] if directed else [(a, b), (b, a)]
        for (s, t) in pairs:
            r = self.rec.setdefault((s, t), {"source_card": s, "target_card": t,
                                             "buckets": set(), "evidence": defaultdict(list)})
            r["buckets"].add(bucket)
            if evidence is not None:
                r["evidence"][bucket].append(evidence)


def build_candidates(repo: Path = REPO) -> dict:
    d = _Data(repo)
    C = _Cands()

    # 1. participant_unresolved (directed, from Part 1)
    for m in d.proj:
        if not m["asserted"]:
            C.add(m["source_card"], m["target_card"], "participant_unresolved",
                  {"relation": m["relation"], "status": m["participant_status"]}, directed=True)

    # 2. named_reference: A's Oracle names a distinctive proper-noun token of card B
    shortnames: dict[str, set] = defaultdict(set)
    for cid, nm in d.name.items():
        tok = re.split(r"[ ,]", nm)[0]
        if len(tok) >= 4 and tok[:1].isupper() and tok.lower() not in _STOP:
            shortnames[tok].add(cid)
    for a in d.cards:
        ot = d.oracle[a]
        for tok, targets in shortnames.items():
            if re.search(r"\b" + re.escape(tok) + r"\b", ot):
                for b in targets:
                    if b != a:
                        C.add(a, b, "named_reference", {"token": tok}, directed=True)

    # 3. replacement_prevention: A REPLACES/PREVENTS a concept that B produces/causes
    produced = defaultdict(list)
    for e in d.edges:
        if e["predicate"] in ("PRODUCES", "CAUSES", "CREATES_OBJECT") and e["target"].startswith(_CONCEPT):
            produced[e["target"]].append(e)
    for e in d.edges:
        if e["predicate"] in ("REPLACES", "PREVENTS") and e["target"].startswith(_CONCEPT):
            a = _card_of(e["source"])
            for pe in produced.get(e["target"], []):
                b = _card_of(pe["source"])
                if a and b and a != b:
                    C.add(a, b, "replacement_prevention",
                          {"predicate": e["predicate"], "concept": e["target"]}, directed=True)

    # 4. copy_effect (card-level flag -> self-pair candidate for the audit)
    for cid in d.cards:
        if re.search(r"\bcopy\b|\bcopies\b", d.oracle[cid], re.I):
            C.add(cid, cid, "copy_effect", None, directed=True)

    # 5. ambiguous_scope (attach as evidence to that card's other candidate pairs)
    ambiguous = {cid for cid in d.cards
                 if re.search(r"this way|that card|that creature|that permanent|that player",
                              d.oracle[cid], re.I)}

    # 6. shared_vocabulary: A,B share a moderately-rare functional concept, no asserted path
    touch = defaultdict(set)
    for e in d.edges:
        if e["predicate"] in _VOCAB_PREDS and e["target"].startswith(_CONCEPT):
            c = _card_of(e["source"])
            if c:
                touch[c].add(e["target"])
    by_concept = defaultdict(set)
    for c, ts in touch.items():
        for t in ts:
            by_concept[t].add(c)
    for t, cs in by_concept.items():
        if 2 <= len(cs) <= 8:                          # skip ubiquitous tokens (low signal)
            cs = sorted(cs)
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)):
                    if (cs[i], cs[j]) not in d.asserted and (cs[j], cs[i]) not in d.asserted:
                        C.add(cs[i], cs[j], "shared_vocabulary", {"concept": t}, directed=False)

    # finalize: attach ambiguous_scope evidence, dedup evidence, sort deterministically
    out = []
    for (s, t), r in C.rec.items():
        if s in ambiguous or t in ambiguous:
            r["buckets"].add("ambiguous_scope")
        mech = [m["relation"] for m in d.proj if m["source_card"] == s and m["target_card"] == t]
        ev = {k: sorted({json.dumps(x, sort_keys=True) for x in v}) for k, v in r["evidence"].items()}
        out.append({
            "source_card": s, "target_card": t,
            "source_name": d.name.get(s, s), "target_name": d.name.get(t, t),
            "buckets": sorted(r["buckets"]),
            "evidence": {k: [json.loads(x) for x in vs] for k, vs in ev.items()},
            "mechanical_relations": sorted(set(mech)),
        })
    out.sort(key=lambda r: (r["source_card"], r["target_card"]))

    outdir = repo / "data" / "graph_global"
    with (outdir / "audit_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    bucket_counts = Counter(b for r in out for b in r["buckets"])
    stats = {
        "candidates": len(out),
        "directed_pairs": len(out),
        "by_bucket": dict(bucket_counts),
        "high_signal": sum(1 for r in out if set(r["buckets"]) - {"shared_vocabulary", "ambiguous_scope"}),
        "shared_vocabulary_only": sum(1 for r in out
                                      if set(r["buckets"]) <= {"shared_vocabulary", "ambiguous_scope"}),
    }
    return stats
