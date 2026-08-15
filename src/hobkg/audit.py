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

    # 4. copy_effect: a copier paired with cards that CREATE a copyable permanent token
    copiers = [cid for cid in d.cards if re.search(r"\bcopy\b|\bcopies\b", d.oracle[cid], re.I)]
    token_creators = defaultdict(set)
    for e in d.edges:
        if e["predicate"] == "CREATES_OBJECT" and e["target"].startswith("token:"):
            c = _card_of(e["source"])
            if c:
                token_creators[c].add(e["target"])
    for cp in copiers:
        for b, toks in token_creators.items():
            if b != cp:
                C.add(cp, b, "copy_effect", {"copyable_tokens": sorted(toks)}, directed=True)

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


def build_batches(repo: Path = REPO, batch_size: int = 14, high_signal_only: bool = False) -> dict:
    d = _Data(repo)
    cands = list(_load_dicts(repo / "data/graph_global/audit_candidates.jsonl"))
    if high_signal_only:
        cands = [c for c in cands if set(c["buckets"]) & _HIGH_SIGNAL]
    packets = [_packet(d, c) for c in cands]
    outdir = repo / "data" / "llm" / "audit"
    outdir.mkdir(parents=True, exist_ok=True)
    for f in list(outdir.glob("batch_*.jsonl")) + list(outdir.glob("extract_*.jsonl")) + list(outdir.glob("critic_*.jsonl")):
        f.unlink()
    n = 0
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
    best = None
    for e in d.func.get(card, []):
        if e["target"] == concept and e["predicate"] in preds and u in e["source"]:
            best = e
            break
    return best


def _build_path(d: _Data, enabler: str, beneficiary: str, concept: str, relation: str):
    """Typed path: enabler's real edge to the concept (fwd) -> derived relation bridge ->
    beneficiary's real edge to the concept (rev). Returns (steps, kind) or (None, 'semantic')."""
    if not concept or concept.startswith("name"):
        bridge = project._derived(f"derived:{relation}:{enabler}->{beneficiary}", relation,
                                  enabler, beneficiary, "llm_audit_semantic_link")
        return [bridge], "semantic"
    ee = _find_edge(d, enabler, concept, _ENABLE_PREDS)
    be = _find_edge(d, beneficiary, concept, _BENEFIT_PREDS)
    if not ee or not be:
        bridge = project._derived(f"derived:{relation}:{enabler}->{beneficiary}", relation,
                                  enabler, beneficiary, "llm_audit_semantic_link")
        return [bridge], "semantic"
    bridge = project._derived(f"derived:{relation}:{concept}", relation, ee["target"], be["source"],
                              "llm_audit_grounded_link")
    return [project._step(ee, "forward"), bridge, project._step(be, "reverse")], "grounded"


def _graph_direction(d: _Data, s: str, t: str, concept: str):
    """If exactly one of the two cards has an ENABLE edge to the concept and the other a
    BENEFIT edge, return (enabler, beneficiary); else None (fall back to LLM direction)."""
    if not concept or concept.startswith("name"):
        return None
    s_en, s_be = _find_edge(d, s, concept, _ENABLE_PREDS), _find_edge(d, s, concept, _BENEFIT_PREDS)
    t_en, t_be = _find_edge(d, t, concept, _ENABLE_PREDS), _find_edge(d, t, concept, _BENEFIT_PREDS)
    if s_en and t_be and not (t_en and s_be):
        return (s, t)
    if t_en and s_be and not (s_en and t_be):
        return (t, s)
    return None


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
    extract = {(v["source_card"], v["target_card"]): v
               for f in sorted(rdir.glob("extract_*.jsonl")) for v in _load_dicts(f)}
    critic = {(v["source_card"], v["target_card"]): v
              for f in sorted(rdir.glob("critic_*.jsonl")) for v in _load_dicts(f)}
    results, accepted = [], []
    counts = Counter()
    for key, ex in sorted(extract.items()):
        s, t = key
        cr = critic.get(key, {})
        verdict = (ex.get("verdict") or "").upper()
        cr_verdict = (cr.get("verdict") or "").upper()
        agree = cr_verdict == "RELATION"                 # independent critic also finds a relation
        rec = {"source_card": s, "target_card": t, "source_name": d.name.get(s, s),
               "target_name": d.name.get(t, t), "extractor_verdict": verdict,
               "critic_verdict": cr_verdict, "critic_agrees": agree,
               "relation_type": ex.get("relation_type"),
               "connecting_concept": ex.get("connecting_concept"), "confidence": ex.get("confidence")}
        if verdict != "RELATION":
            rec["status"] = "no_relation"
            counts["no_relation"] += 1
            results.append(rec)
            continue
        # reconcile: require the independent critic to ALSO find a relation
        if not agree:
            rec["status"] = "critic_rejected"
            rec["critic_reason"] = cr.get("mechanism") or cr.get("reason")
            counts["critic_rejected"] += 1
            results.append(rec)
            continue
        enabler = ex.get("enabler") or "source"
        relation = ex.get("relation_type")
        concept = ex.get("connecting_concept")
        src, tgt = (s, t) if enabler == "source" else (t, s)
        # DETERMINISTIC direction override: when the graph unambiguously shows one card
        # produces/affects the concept and the other consumes/triggers on it, the enabler
        # is the producer — regardless of the submitted direction.
        det = _graph_direction(d, s, t, concept)
        if det:
            src, tgt = det
            rec["direction_source"] = "graph_normalized"
        # grounding must be exact per-face spans
        if not _valid_spans(d, ex.get("grounding")):
            rec["status"] = "ungrounded"
            counts["ungrounded"] += 1
            results.append(rec)
            continue
        # reject anything already represented mechanically
        if _is_duplicate(d, src, tgt, concept, relation):
            rec["status"] = "duplicate_of_mechanical"
            counts["duplicate"] += 1
            results.append(rec)
            continue
        steps, kind = _build_path(d, src, tgt, concept, relation)
        rec.update({"status": "accepted", "source_card": src, "target_card": tgt,
                    "source_name": d.name.get(src, src), "target_name": d.name.get(tgt, tgt),
                    "relation_type": relation, "connecting_concept": concept, "path_kind": kind,
                    "grounding": ex.get("grounding"), "conditions": ex.get("conditions") or []})
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
    stats = {"extractor_verdicts": len(extract), "critic_verdicts": len(critic), **dict(counts),
             "augmented_metaedges": len(accepted)}
    _audit_report(repo, results, accepted, stats)
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


def _audit_report(repo: Path, results: list, accepted: list, stats: dict) -> None:
    L = ["# HOB Phase 5 Part 2 — Pairwise LLM Audit (extractor + critic)", "",
         f"- **extractor verdicts**: {stats.get('extractor_verdicts', 0)}",
         f"- **accepted (critic-confirmed, grounded, novel)**: {stats.get('accepted', 0)}",
         f"- **critic-rejected**: {stats.get('critic_rejected', 0)}",
         f"- **duplicate of mechanical**: {stats.get('duplicate', 0)}",
         f"- **ungrounded**: {stats.get('ungrounded', 0)}",
         f"- **NO_RELATION**: {stats.get('no_relation', 0)}", "",
         "## Accepted augmented relations (origin: llm_audit)", ""]
    for m in accepted:
        L.append(f"- **{_nm(results, m['source_card'])} → {_nm(results, m['target_card'])}** "
                 f"[{m['relation']}/{m['path_kind']}] via `{m['connecting_concept']}`")
    (repo / "reports" / "pair_audit.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _nm(results, cid):
    for r in results:
        if r["source_card"] == cid:
            return r["source_name"]
        if r["target_card"] == cid:
            return r["target_name"]
    return cid
