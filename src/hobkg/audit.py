"""Phase 5 Part 2: pairwise LLM audit (control plane).

The mechanical projection (Part 1) covers only pairs with an allowed primitive path.
This module (a) deterministically selects the bounded set of pairs likely to hide a
missed relationship, (b) packages each for sub-agent adjudication with each card's
Oracle text AND functional primitive subgraph, and (c) reconciles an EXTRACTOR pass
against an independent CRITIC pass, validates the grounding against exact per-face
Oracle spans, normalizes direction, rejects anything already represented mechanically,
and builds a TYPED, edge-id-bearing path — stored in a SEPARATE augmented layer
(`origin: llm_audit`), never merged into the canonical Part 1 projection.

Two-plane, no-API: sub-agents are the "LLM" (see phase3-llm-via-subagents memory).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import project
from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_CONCEPT = ("resource:", "event:", "counter:", "token:", "gate:", "state:")
_FUNC = {"PRODUCES", "CONSUMES", "CAUSES", "TRIGGERS", "REQUIRES", "PREVENTS", "REPLACES",
         "MODIFIES", "ADDS_COUNTER", "REMOVES_COUNTER", "CREATES_OBJECT", "ENABLES",
         "REFERENCES_RULE", "SCALES_WITH"}
_ENABLE_PREDS = {"PRODUCES", "CAUSES", "CREATES_OBJECT", "REPLACES", "MODIFIES", "ADDS_COUNTER"}
_BENEFIT_PREDS = {"CONSUMES", "TRIGGERS", "REQUIRES", "PRODUCES", "CAUSES", "SCALES_WITH"}
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
        self.face_oracle = {}
        self.faces_of = defaultdict(list)
        for f in self.faces:
            self.oracle[f["card_id"]] += " " + (f.get("oracle_text") or "")
            self.face_oracle[f["id"]] = f.get("oracle_text") or ""
            self.faces_of[f["card_id"]].append(f["id"])
        self.name = {cid: c["name"] for cid, c in self.cards.items()}
        # functional edges + concepts per card (by uuid substring)
        self.func = defaultdict(list)
        self.concepts = defaultdict(set)
        for e in self.edges:
            if e["predicate"] in _FUNC and e["target"].startswith(_CONCEPT):
                c = _card_of(e["source"])
                if c:
                    self.func[c].append(e)
                    self.concepts[c].add(e["target"])
        self.asserted = {(m["source_card"], m["target_card"]) for m in self.proj if m["asserted"]}
        self.mech = defaultdict(set)   # (a,b) -> {relation}
        self.mech_concepts = defaultdict(set)
        for m in self.proj:
            self.mech[(m["source_card"], m["target_card"])].add(m["relation"])


# --------------------------------------------------------------------------- #
#  Stage A: candidate selection                                                #
# --------------------------------------------------------------------------- #
class _Cands:
    def __init__(self):
        self.rec: dict[tuple, dict] = {}

    def add(self, a, b, bucket, evidence, directed):
        if a == b and bucket not in ("copy_effect",):
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

    # 1. participant_unresolved (directed)
    for m in d.proj:
        if not m["asserted"]:
            C.add(m["source_card"], m["target_card"], "participant_unresolved",
                  {"relation": m["relation"]}, directed=True)

    # 2. named_reference (exclude creature-type words)
    type_words = {(n["data"].get("name") or n["label"]).lower()
                  for nid, n in d.nodes.items()
                  if nid.startswith(("obj:type:", "obj:subtype:", "obj:supertype:"))}
    shortnames = defaultdict(set)
    for cid, nm in d.name.items():
        tok = re.split(r"[ ,]", nm)[0]
        if len(tok) >= 4 and tok[:1].isupper() and tok.lower() not in _STOP and tok.lower() not in type_words:
            shortnames[tok].add(cid)
    for a in d.cards:
        for tok, targets in shortnames.items():
            if re.search(r"\b" + re.escape(tok) + r"\b", d.oracle[a]):
                for b in targets:
                    if b != a:
                        C.add(a, b, "named_reference", {"token": tok}, directed=True)

    # 3. replacement_prevention: A REPLACES/PREVENTS a concept B produces/causes
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
                    C.add(a, b, "replacement_prevention", {"predicate": e["predicate"], "concept": e["target"]},
                          directed=True)

    # 4. copy_effect (output-aware): derive WHAT the copier produces, then pair it only
    # with cards that care about that output — the copied object's subtype (tribal
    # payoff / count), or triggers on extra creatures/permanents entering.
    card_subtypes = defaultdict(set)
    for e in d.edges:
        if e["predicate"] == "HAS_TYPE" and e["target"].startswith("obj:subtype:"):
            c = _card_of(e["source"])
            if c:
                card_subtypes[c].add(e["target"].split(":")[-1])
    for cp in d.cards:
        ot = d.oracle[cp]
        if not re.search(r"\bcopy\b|\bcopies\b", ot, re.I):
            continue
        if re.search(r"copies of (them|it)|copy of it", ot, re.I):
            outputs = card_subtypes.get(cp, set())            # copies itself -> its own subtypes
        else:
            outputs = {"creature"}                            # copies a creature/permanent
        for b in d.cards:
            if b == cp:
                continue
            ob = d.oracle[b].lower()
            hits = [w for w in outputs if re.search(r"\b" + re.escape(w) + r"\b", ob)]
            enters = re.search(r"(another |a )?(creature|permanent|token)s?( you control)? enters?"
                               r"|whenever .*enters the battlefield", ob)
            if hits or enters:
                C.add(cp, b, "copy_effect",
                      {"copy_output": sorted(outputs), "matched": hits or ["enters-trigger"]}, directed=True)

    # 5. ambiguous_scope: OPERATIONAL — an ambiguous-referent card paired with cards that
    # share a moderately-rare functional concept (so it independently enters the audit).
    ambiguous = {cid for cid in d.cards
                 if re.search(r"this way|that card|that creature|that permanent|that player",
                              d.oracle[cid], re.I)}
    by_concept = defaultdict(set)
    for c, cs in d.concepts.items():
        for t in cs:
            by_concept[t].add(c)
    for t, cs in by_concept.items():
        if 2 <= len(cs) <= 8:
            cs = sorted(cs)
            for i in range(len(cs)):
                for j in range(len(cs)):
                    if i == j:
                        continue
                    if (cs[i] in ambiguous or cs[j] in ambiguous) and (cs[i], cs[j]) not in d.asserted:
                        C.add(cs[i], cs[j], "ambiguous_scope", {"concept": t}, directed=True)

    # 6. shared_vocabulary: rare shared functional concept, no asserted path (both orientations)
    for t, cs in by_concept.items():
        if 2 <= len(cs) <= 8:
            cs = sorted(cs)
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)):
                    if (cs[i], cs[j]) not in d.asserted and (cs[j], cs[i]) not in d.asserted:
                        C.add(cs[i], cs[j], "shared_vocabulary", {"concept": t}, directed=False)

    out = []
    for (s, t), r in C.rec.items():
        shared = sorted(d.concepts[s] & d.concepts[t])
        mech = sorted(d.mech.get((s, t), set()))
        ev = {k: [json.loads(x) for x in sorted({json.dumps(y, sort_keys=True) for y in v})]
              for k, v in r["evidence"].items()}
        out.append({"source_card": s, "target_card": t,
                    "source_name": d.name.get(s, s), "target_name": d.name.get(t, t),
                    "buckets": sorted(r["buckets"]), "evidence": ev,
                    "shared_concepts": shared, "mechanical_relations": mech})
    out.sort(key=lambda r: (r["source_card"], r["target_card"]))
    with (repo / "data/graph_global/audit_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    bc = Counter(b for r in out for b in r["buckets"])
    return {"candidates": len(out), "by_bucket": dict(bc),
            "high_signal": sum(1 for r in out if set(r["buckets"]) - {"shared_vocabulary"})}


# --------------------------------------------------------------------------- #
#  Stage B: batch packets for extractor + critic sub-agents                    #
# --------------------------------------------------------------------------- #
_HIGH_SIGNAL = {"named_reference", "participant_unresolved", "replacement_prevention",
                "copy_effect", "ambiguous_scope"}


def _faces(d: _Data, card: str):
    return [{"face_id": fid, "oracle_text": d.face_oracle[fid]} for fid in d.faces_of.get(card, [])]


def _packet(d: _Data, c: dict) -> dict:
    def sub(card):
        return [{"edge_id": e["edge_id"], "predicate": e["predicate"], "concept": e["target"]}
                for e in d.func.get(card, [])]
    return {**c,
            "source_faces": _faces(d, c["source_card"]), "target_faces": _faces(d, c["target_card"]),
            "source_subgraph": sub(c["source_card"]), "target_subgraph": sub(c["target_card"])}


def build_batches(repo: Path = REPO, batch_size: int = 14, high_signal_only: bool = False,
                  only_unaudited: bool = False, start_index: int = 0) -> dict:
    d = _Data(repo)
    cands = list(_load_dicts(repo / "data/graph_global/audit_candidates.jsonl"))
    if high_signal_only:
        cands = [c for c in cands if set(c["buckets"]) & _HIGH_SIGNAL]
    outdir = repo / "data" / "llm" / "audit"
    outdir.mkdir(parents=True, exist_ok=True)
    if only_unaudited:
        done = {(v["source_card"], v["target_card"])
                for f in outdir.glob("extract_*.jsonl") for v in _load_dicts(f)}
        cands = [c for c in cands if (c["source_card"], c["target_card"]) not in done]
        for f in outdir.glob("batch_*.jsonl"):
            f.unlink()
    else:
        for f in (list(outdir.glob("batch_*.jsonl")) + list(outdir.glob("extract_*.jsonl"))
                  + list(outdir.glob("critic_*.jsonl"))):
            f.unlink()
    packets = [_packet(d, c) for c in cands]
    n = start_index
    for i in range(0, len(packets), batch_size):
        n += 1
        with (outdir / f"batch_{n:03d}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for p in packets[i:i + batch_size]:
                fh.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
    return {"candidates_batched": len(packets), "batches": n, "batch_size": batch_size}


# --------------------------------------------------------------------------- #
#  Ingest + reconcile (extractor ∩ critic) -> typed augmented layer            #
# --------------------------------------------------------------------------- #
def _valid_spans(d: _Data, grounding) -> bool:
    """Every grounding phrase must be an EXACT substring of the named face's Oracle
    text (per-face grounding). The char span is recomputed deterministically, so the
    agent only needs to copy exact text and name the correct face."""
    if not grounding:
        return False
    ok = 0
    for g in grounding:
        fid, text = g.get("face_id"), g.get("text")
        if fid in d.face_oracle and text and text in d.face_oracle[fid]:
            idx = d.face_oracle[fid].index(text)
            g["oracle_span"] = [idx, idx + len(text)]
            g["card_id"] = _card_of(fid)
            ok += 1
        else:
            return False
    return ok >= 1


def _find_edge(d: _Data, card: str, concept: str, preds: set):
    u = card.split(":")[1]
    for e in d.func.get(card, []):
        if e["target"] == concept and e["predicate"] in preds and u in e["source"]:
            return e
    return None


def _triggers_edge(d: _Data, concept: str, beneficiary: str):
    u = beneficiary.split(":")[1]
    for e in d.edges:
        if e["predicate"] == "TRIGGERS" and e["source"] == concept and u in e["target"]:
            return e
    return None


# Relation-specific path signatures — ordered real edges of a FAITHFUL primitive path
# for (enabler A, beneficiary B) over the connecting concept, or None.
def _sig_enables_trigger(d, a, b, concept):
    # A → produces/causes event E ; E → TRIGGERS → B's ability
    if not concept or not concept.startswith("event:"):
        return None
    ae = _find_edge(d, a, concept, {"PRODUCES", "CAUSES", "CREATES_OBJECT", "ADDS_COUNTER"})
    te = _triggers_edge(d, concept, b)
    return [project._step(ae, "forward"), project._step(te, "forward")] if ae and te else None


def _sig_amplifies(d, a, b, concept):
    # A → REPLACES/MODIFIES E  ←CAUSES/PRODUCES←  B
    ae = _find_edge(d, a, concept, {"REPLACES", "MODIFIES"})
    be = _find_edge(d, b, concept, {"CAUSES", "PRODUCES"})
    return [project._step(ae, "forward"), project._step(be, "reverse")] if ae and be else None


def _sig_supplies(d, a, b, concept):
    # A → PRODUCES R  ←CONSUMES/REQUIRES←  B
    ae = _find_edge(d, a, concept, {"PRODUCES"})
    be = _find_edge(d, b, concept, {"CONSUMES", "REQUIRES"})
    return [project._step(ae, "forward"), project._step(be, "reverse")] if ae and be else None


_SIGNATURES = {"ENABLES_TRIGGER": _sig_enables_trigger, "AMPLIFIES_EFFECT": _sig_amplifies,
               "SUPPLIES_RESOURCE": _sig_supplies}
_REPAIR_HINT = {
    "ENABLES_TRIGGER": "add/canonicalize the intermediate event (life-lost / counter-placed / "
                       "creature-ability-activated) and a TRIGGERS edge to the beneficiary ability",
    "AMPLIFIES_EFFECT": "canonicalize the shared modified event/resource node",
    "SUPPLIES_RESOURCE": "canonicalize the shared resource node so producer feeds consumer",
}


def _typed_path(d: _Data, relation: str, s: str, t: str, concept: str):
    """Try both orientations against the RELATION-SPECIFIC signature. Returns
    (steps, src, tgt, 'grounded') for a faithful primitive path, else
    (None, s, t, 'needs_repair'). A generic shared-output join is NOT accepted."""
    sig = _SIGNATURES.get(relation)
    if sig and concept:
        for (a, b) in ((s, t), (t, s)):
            steps = sig(d, a, b, concept)
            if steps:
                anchor = steps[0]["target"]
                bridge = project._derived(f"derived:{relation}:{concept}", relation, anchor,
                                          steps[-1]["source"], "llm_audit_typed_link")
                return [steps[0], bridge, steps[-1]], a, b, "grounded"
    return None, s, t, "needs_repair"


_FACE = re.compile(r"face:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:\d+")


def _grounding_covers_path(d: _Data, steps: list, grounding: list) -> bool:
    """Each real path edge must be tied to a grounding phrase on the SAME face (the face
    the edge's op belongs to) whose span overlaps the edge's provenance Oracle span — so
    the grounding corresponds to the primitive edges actually used."""
    for st in steps:
        if st.get("derived"):
            continue
        faces = {m.group(0) for nid in (st["source"], st["target"]) for m in [_FACE.search(nid)] if m}
        prov_spans = [p["oracle_span"] for p in st.get("provenance", []) if p.get("oracle_span")]
        if not faces:
            continue
        covered = False
        for g in grounding:
            if g.get("face_id") not in faces:
                continue
            if not prov_spans:
                covered = True
                break
            gs = g.get("oracle_span") or [0, 0]
            if any(max(0, min(sp[1], gs[1]) - max(sp[0], gs[0])) > 0 for sp in prov_spans):
                covered = True
                break
        if not covered:
            return False
    return True


def _is_duplicate(d: _Data, s: str, t: str, concept: str, relation: str) -> bool:
    mech = d.mech.get((s, t), set()) | d.mech.get((t, s), set())
    if relation in mech:
        return True
    if concept and concept.startswith("resource:mana") and "INFRASTRUCTURE_CASTING" in mech:
        return True
    # already represented: the connecting concept appears on an existing mechanical path
    if concept:
        for m in d.proj:
            if {m["source_card"], m["target_card"]} == {s, t}:
                for alt in m.get("alternative_paths", []):
                    if concept in alt.get("primitive_path", []):
                        return True
    return False


def ingest(repo: Path = REPO) -> dict:
    d = _Data(repo)
    rdir = repo / "data" / "llm" / "audit"
    cand_pairs = {(c["source_card"], c["target_card"])
                  for c in _load_dicts(repo / "data/graph_global/audit_candidates.jsonl")}
    # only verdicts for CURRENT candidate pairs (ignore stale verdicts from superseded buckets)
    extract = {(v["source_card"], v["target_card"]): v
               for f in sorted(rdir.glob("extract_*.jsonl")) for v in _load_dicts(f)
               if (v["source_card"], v["target_card"]) in cand_pairs}
    critic = {(v["source_card"], v["target_card"]): v
              for f in sorted(rdir.glob("critic_*.jsonl")) for v in _load_dicts(f)
              if (v["source_card"], v["target_card"]) in cand_pairs}
    results, accepted, repair = [], [], []
    counts = Counter()
    for key, ex in sorted(extract.items()):
        s, t = key
        cr = critic.get(key, {})
        verdict = (ex.get("verdict") or "").upper()
        cr_verdict = (cr.get("verdict") or "").upper()
        relation = ex.get("relation_type")
        concept = ex.get("connecting_concept")
        rec = {"source_card": s, "target_card": t, "source_name": d.name.get(s, s),
               "target_name": d.name.get(t, t), "extractor_verdict": verdict,
               "critic_verdict": cr_verdict, "relation_type": relation,
               "connecting_concept": concept, "confidence": ex.get("confidence")}
        if verdict != "RELATION":
            rec["status"] = "no_relation"
            counts["no_relation"] += 1
            results.append(rec)
            continue
        # reconcile: the critic must ALSO find a RELATION and AGREE on the normalized tuple
        # (relation_type + connecting_concept), and its own grounding spans must validate.
        tuple_agree = (cr_verdict == "RELATION"
                       and (cr.get("relation_type") or "").upper() == (relation or "").upper()
                       and (cr.get("connecting_concept") or "") == (concept or "")
                       and _valid_spans(d, cr.get("grounding")))
        if not tuple_agree:
            rec["status"] = "critic_disagreement"
            rec["critic_reason"] = cr.get("mechanism") or cr.get("reason")
            counts["critic_disagreement"] += 1
            results.append(rec)
            continue
        if not _valid_spans(d, ex.get("grounding")):
            rec["status"] = "ungrounded"
            counts["ungrounded"] += 1
            results.append(rec)
            continue
        # relation-specific FAITHFUL typed path (both orientations); sets direction
        steps, src, tgt, kind = _typed_path(d, relation, s, t, concept)
        rec.update({"source_card": src, "target_card": tgt,
                    "source_name": d.name.get(src, src), "target_name": d.name.get(tgt, tgt),
                    "grounding": ex.get("grounding"), "conditions": ex.get("conditions") or []})
        if _is_duplicate(d, src, tgt, concept, relation):
            rec["status"] = "duplicate_of_mechanical"
            counts["duplicate"] += 1
            results.append(rec)
            continue
        if kind != "grounded" or not _grounding_covers_path(d, steps, ex.get("grounding")):
            # credible but no faithful primitive path -> graph-repair queue, NOT a shortcut
            rec["status"] = "requires_graph_repair"
            rec["missing"] = _REPAIR_HINT.get(relation, "canonicalize the intermediate node")
            repair.append({"source_card": src, "target_card": tgt, "relation": relation,
                           "connecting_concept": concept, "missing": rec["missing"],
                           "grounding": ex.get("grounding"), "confidence": ex.get("confidence"),
                           "source_name": d.name.get(src, src), "target_name": d.name.get(tgt, tgt)})
            counts["requires_graph_repair"] += 1
            results.append(rec)
            continue
        rec.update({"status": "accepted", "relation_type": relation, "path_kind": kind})
        accepted.append(_augmented(rec, steps))
        counts["accepted"] += 1
        results.append(rec)

    results.sort(key=lambda r: (r["source_card"], r["target_card"], r.get("relation_type") or ""))
    with (repo / "data/graph_global/audit_results.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    # dedup augmented metaedges by (source, target, relation) — the same relation can be
    # reached from a candidate's two orientations; keep one, union the grounding.
    uniq = {}
    for m in accepted:
        k = (m["source_card"], m["target_card"], m["relation"])
        if k not in uniq:
            uniq[k] = m
        else:
            seen = {json.dumps(g, sort_keys=True) for g in uniq[k]["grounding"]}
            for g in m["grounding"]:
                if json.dumps(g, sort_keys=True) not in seen:
                    uniq[k]["grounding"].append(g)
    accepted = sorted(uniq.values(), key=lambda m: (m["source_card"], m["target_card"], m["relation"]))
    with (repo / "data/graph_global/card_pair_projection_audit.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in accepted:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    # dedup the graph-repair queue by UNORDERED pair + relation (mirror candidate
    # orientations describe the same missing mechanism; direction is provisional until
    # the intermediate event is canonicalized and the pair is reprojected mechanically).
    rq = {}
    for r in repair:
        rq.setdefault((frozenset((r["source_card"], r["target_card"])), r["relation"]), r)
    repair = sorted(rq.values(), key=lambda r: (r["source_card"], r["target_card"], r["relation"]))
    with (repo / "data/graph_global/audit_repair_queue.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in repair:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    total_candidates = len(list(_load_dicts(repo / "data/graph_global/audit_candidates.jsonl")))
    stats = {"total_candidates": total_candidates, "audited": len(extract),
             "unaudited": total_candidates - len(extract),
             "critic_verdicts": len(critic), **dict(counts),
             "augmented_metaedges": len(accepted), "repair_queue": len(repair)}
    _audit_report(repo, results, accepted, repair, stats)
    return stats


def _augmented(rec: dict, steps: list) -> dict:
    nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
    return {"source_card": rec["source_card"], "target_card": rec["target_card"],
            "relation": rec["relation_type"], "origin": "llm_audit", "path_kind": rec["path_kind"],
            "steps": steps, "primitive_path": nodes_seq,
            "path_predicates": [s["predicate"] for s in steps],
            "edge_ids": [s["edge_id"] for s in steps],
            "connecting_concept": rec["connecting_concept"],
            "conditions": rec.get("conditions") or [],
            "grounding": rec.get("grounding") or [], "confidence": rec.get("confidence"),
            "critic_confirmed": True}


def _audit_report(repo: Path, results: list, accepted: list, repair: list, stats: dict) -> None:
    L = ["# HOB Phase 5 Part 2 — Pairwise LLM Audit (extractor + critic, typed paths)", "",
         f"- **coverage**: {stats.get('audited', 0)}/{stats.get('total_candidates', 0)} candidates audited "
         f"({stats.get('unaudited', 0)} shared-vocabulary candidates unaudited)",
         f"- **accepted faithful typed paths (origin: llm_audit)**: {stats.get('accepted', 0)}",
         f"- **routed to graph-repair queue**: {stats.get('requires_graph_repair', 0)}",
         f"- **critic disagreement**: {stats.get('critic_disagreement', 0)}",
         f"- **duplicate of mechanical**: {stats.get('duplicate', 0)}",
         f"- **ungrounded**: {stats.get('ungrounded', 0)}",
         f"- **NO_RELATION**: {stats.get('no_relation', 0)}", "",
         "## Accepted faithful typed paths (origin: llm_audit)", ""]
    for m in accepted:
        L.append(f"- **{_nm(results, m['source_card'])} → {_nm(results, m['target_card'])}** "
                 f"[{m['relation']}] via `{m['connecting_concept']}` — {' → '.join(m['path_predicates'])}")
    L += ["", "## Graph-repair queue (credible relations lacking a primitive path)", ""]
    for r in repair:
        L.append(f"- **{r['source_name']} → {r['target_name']}** [{r['relation']}] via "
                 f"`{r['connecting_concept']}` — needs: {r['missing']}")
    (repo / "reports" / "pair_audit.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _nm(results, cid):
    for r in results:
        if r["source_card"] == cid:
            return r["source_name"]
        if r["target_card"] == cid:
            return r["target_name"]
    return cid
