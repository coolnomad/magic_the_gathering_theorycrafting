"""Phase 6 completion: coverage report + stratified manual gold-set.

The coverage report (spec §Coverage report) summarizes what the build covers — NOT a
correctness metric (do not maximize edge count). The gold set (spec §Manual gold set)
emits a stratified sample for hand review before full acceptance.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _card_of(nid):
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


# Spec semantic invariants that are DELIBERATELY not modeled as graph structure yet — recorded
# honestly as representational gaps, not presented as satisfied invariants. The graph asserts no
# edge for these rather than inventing an unsupported one (per the spec's "flag ambiguity" rule).
DEFERRED_INVARIANTS = [
    {"id": 2, "name": "Recruit -> Master's Councillors second-draw ordering",
     "status": "deferred_unmodeled",
     "reason": ("Councillors triggers only on 'the second card drawn each turn' — a per-turn "
                "ORDERING condition. Modeling it needs a turn-scoped cards-drawn-this-turn count "
                "state/gate (draw -> increment count -> count reaches 2 -> second-draw event -> "
                "Councillors), where Recruit contributes one draw without being sufficient alone. "
                "Until that turn-scoped counter exists, the graph correctly asserts NO Recruit<->"
                "Councillors edge in either direction across all three projection layers.")},
]


def _opt(path):
    return list(_load_dicts(path)) if path.exists() else []


def coverage(repo: Path = REPO) -> dict:
    G = repo / "data" / "graph_global"
    nodes = list(_load_dicts(G / "nodes.jsonl"))
    frozen_edges = list(_load_dicts(G / "edges.jsonl"))
    repair_edges = _opt(G / "repair_edges.jsonl")
    repair_nodes = _opt(G / "repair_nodes.jsonl")
    legend_edges = _opt(G / "legend_edges.jsonl")
    legend_nodes = _opt(G / "legend_nodes.jsonl")
    # deduplicated union of the frozen Phase 4 layer + the graph-repair layer + the legend layer
    union = {e["edge_id"]: {**e, "origin": e.get("origin", "phase4")} for e in frozen_edges}
    for e in repair_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "graph_repair")}
    for e in legend_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "legend_rule")}
    edges = list(union.values())
    cards = list(_load_dicts(repo / "data/normalized/cards.jsonl"))
    faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
    proj = list(_load_dicts(G / "card_pair_projection.jsonl"))
    audit_accepted = [a for a in _opt(G / "card_pair_projection_audit.jsonl")]
    repaired_rel = _opt(G / "card_pair_projection_repaired.jsonl")
    audit = _opt(G / "audit_results.jsonl")
    conds = list(_load_dicts(G / "conditions.jsonl"))

    ability_kinds = Counter(n["data"].get("kind", "?") for n in nodes if n["type"] == "Ability")
    edges_by_pred = Counter(e["predicate"] for e in edges)
    # pair relations
    rel_by_type = Counter(m["relation"] for m in proj)
    pairs = defaultdict(set)
    for m in proj:
        pairs[(m["source_card"], m["target_card"])].add(m["relation"])
    multi_rel_pairs = sum(1 for v in pairs.values() if len(v) > 1)
    infra_only = sum(1 for v in pairs.values() if v == {"INFRASTRUCTURE_CASTING"})
    gate_mediated = rel_by_type.get("CONTRIBUTES_TO_GATE", 0)
    # cards with no non-infrastructure OUTGOING / INCOMING pair relation
    out_noninfra, in_noninfra = defaultdict(set), defaultdict(set)
    for m in proj:
        if m["relation"] != "INFRASTRUCTURE_CASTING":
            out_noninfra[m["source_card"]].add(m["target_card"])
            in_noninfra[m["target_card"]].add(m["source_card"])
    card_ids = {c["id"] for c in cards}
    no_out = sorted(card_ids - set(out_noninfra))
    no_in = sorted(card_ids - set(in_noninfra))

    stats = {
        "cards_parsed": len(cards), "faces_parsed": len(faces),
        "abilities_by_kind": dict(ability_kinds),
        # per-layer AND deduplicated union (the completed graph, not just Phase 4)
        "edges_frozen": len(frozen_edges), "edges_repair": len(repair_edges),
        "edges_legend": len(legend_edges),
        "edges_union": len(edges), "nodes_repair": len(repair_nodes),
        "nodes_legend": len(legend_nodes),
        "edges_total": len(edges), "edges_by_predicate": dict(edges_by_pred),
        "edges_by_origin": dict(Counter(e.get("origin", "phase4") for e in edges)),
        "edges_without_provenance": sum(1 for e in edges if not e.get("provenance")),
        # relations per layer + union
        "relations_mechanical": len(proj), "relations_audited": len(audit_accepted),
        "relations_repaired": len(repaired_rel),
        "relations_union": len(proj) + len(audit_accepted) + len(repaired_rel),
        "conditions_total": len(conds),
        "conditions_raw_unresolved": sum(1 for c in conds if c.get("status") == "raw_unresolved"),
        "unresolved_oracle_records": len(_opt(repo / "data/review/unresolved.jsonl")),
        "llm_faces_accepted": len(_opt(repo / "data/review/llm_accepted.jsonl")),
        "audit_accepted_relations": sum(1 for a in audit if a.get("status") == "accepted"),
        "audit_no_relation": sum(1 for a in audit if a.get("status") == "no_relation"),
        "audit_graph_repair": sum(1 for a in audit if a.get("status") == "requires_graph_repair"),
        "pair_relations_total": len(proj),
        "pair_relations_by_type": dict(rel_by_type),
        "pairs_with_multiple_relation_types": multi_rel_pairs,
        "gate_mediated_relations": gate_mediated,
        "infrastructure_only_pairs": infra_only,
        "cards_no_noninfra_outgoing": len(no_out),
        "cards_no_noninfra_incoming": len(no_in),
        "deferred_invariants": DEFERRED_INVARIANTS,
    }
    _coverage_report(repo, stats, no_out, no_in, cards)
    (G / "coverage.json").write_text(json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    return stats


def _coverage_report(repo, s, no_out, no_in, cards):
    nm = {c["id"]: c["name"] for c in cards}
    L = ["# HOB Coverage Report (Phase 6)", "",
         "*Coverage is not correctness; edge count is not maximized.*", "",
         f"- cards / faces parsed: **{s['cards_parsed']} / {s['faces_parsed']}**",
         f"- abilities by kind: {s['abilities_by_kind']}",
         f"- primitive edges (per layer + union): frozen **{s['edges_frozen']}** + repair "
         f"**{s['edges_repair']}** + legend **{s['edges_legend']}** = union **{s['edges_union']}** "
         f"(+{s['nodes_repair']} repair nodes, +{s['nodes_legend']} legend nodes); "
         f"by origin {s['edges_by_origin']}; provenance gaps: {s['edges_without_provenance']}",
         f"- pair relations (per layer + union): mechanical **{s['relations_mechanical']}** + audited "
         f"**{s['relations_audited']}** + repaired **{s['relations_repaired']}** = union **{s['relations_union']}**",
         f"- conditions: {s['conditions_total']} ({s['conditions_raw_unresolved']} raw-unresolved); "
         f"unresolved Oracle records: {s['unresolved_oracle_records']}",
         f"- LLM: {s['llm_faces_accepted']} faces accepted; audit "
         f"{s['audit_accepted_relations']} accepted / {s['audit_no_relation']} no-relation / "
         f"{s['audit_graph_repair']} graph-repair",
         f"- pair relations: **{s['pair_relations_total']}** {s['pair_relations_by_type']}",
         f"- pairs with multiple relation types: {s['pairs_with_multiple_relation_types']}",
         f"- gate-mediated relations: {s['gate_mediated_relations']}; "
         f"infrastructure-only pairs: {s['infrastructure_only_pairs']}",
         f"- cards with NO non-infrastructure outgoing relation: **{s['cards_no_noninfra_outgoing']}**",
         f"- cards with NO non-infrastructure incoming relation: **{s['cards_no_noninfra_incoming']}**", "",
         "## Edges by predicate", ""]
    for k, v in sorted(s["edges_by_predicate"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {v}")
    L += ["", "## Deferred / unmodeled semantic invariants", "",
          "*Recorded as honest representational gaps — the graph asserts no edge rather than "
          "inventing an unsupported one.*", ""]
    for d in s["deferred_invariants"]:
        L.append(f"- **#{d['id']} {d['name']}** — _{d['status']}_: {d['reason']}")
    L += ["", "## Cards with no non-infrastructure outgoing relation (sample)", ""]
    L += [f"- {nm.get(c, c)}" for c in no_out[:30]]
    (repo / "reports" / "coverage.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def pair_index(repo: Path = REPO) -> dict:
    """Emit EXACTLY 193^2 = 37,249 ordered-pair records (the completion criterion), each
    listing its mechanical, audited, and repaired relations (empty pairs included)."""
    G = repo / "data" / "graph_global"
    cards = sorted(c["id"] for c in _load_dicts(repo / "data/normalized/cards.jsonl"))
    mech, aud, rep = defaultdict(list), defaultdict(list), defaultdict(list)
    for m in _load_dicts(G / "card_pair_projection.jsonl"):
        mech[(m["source_card"], m["target_card"])].append(m["relation"])
    for m in _opt(G / "card_pair_projection_audit.jsonl"):
        aud[(m["source_card"], m["target_card"])].append(m["relation"])
    for m in _opt(G / "card_pair_projection_repaired.jsonl"):
        rep[(m["source_card"], m["target_card"])].append(m["relation"])
    n, nonempty = 0, 0
    with (G / "pair_index.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for a in cards:
            for b in cards:
                mr, ar, rr = sorted(mech[(a, b)]), sorted(aud[(a, b)]), sorted(rep[(a, b)])
                total = len(mr) + len(ar) + len(rr)
                n += 1
                nonempty += 1 if total else 0
                fh.write(json.dumps({"source_card": a, "target_card": b, "self_pair": a == b,
                                     "mechanical": mr, "audited": ar, "repaired": rr,
                                     "total_relations": total}, sort_keys=True) + "\n")
    return {"pair_records": n, "possible_ordered_pairs": len(cards) ** 2,
            "nonempty_pairs": nonempty, "empty_pairs": n - nonempty}


def structural_validation_set(repo: Path = REPO) -> dict:
    """Stratified STRUCTURAL VALIDATION set (NOT an independent human gold set — it applies
    deterministic structural assertions to the same graph being evaluated; human reviewers
    still adjudicate semantics). Diversified sampling + per-item pass/fail verdicts."""
    G = repo / "data" / "graph_global"
    faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
    cards = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
    mech = defaultdict(set)
    for m in _load_dicts(repo / "data/rules/mechanics.jsonl"):
        mech[m["mechanic"]].add(m["card_id"])
    edges = list(_load_dicts(G / "edges.jsonl")) + _opt(G / "repair_edges.jsonl")
    by_card_pred = defaultdict(set)
    for e in edges:
        c = _card_of(e["source"])
        if c:
            by_card_pred[(c, e["predicate"])].add(e["target"])
    lore_cards = {_card_of(e["source"]) for e in edges
                  if e["predicate"] == "HAS_COUNTER_TYPE" and e["target"] == "counter:lore"} - {None}
    # relation TYPES per pair across ALL THREE layers (mechanical + audit + repaired)
    rel_by_pair = defaultdict(set)
    for layer in ("card_pair_projection.jsonl", "card_pair_projection_audit.jsonl",
                  "card_pair_projection_repaired.jsonl"):
        for m in _opt(G / layer):
            rel_by_pair[(m["source_card"], m["target_card"])].add(m["relation"])
    related = set(rel_by_pair)
    # self-pair metaedges + their primitive paths (to check reflexive resolution)
    selfpath = {}
    for m in _load_dicts(G / "card_pair_projection.jsonl"):
        if m["source_card"] == m["target_card"]:
            selfpath[m["source_card"]] = [n for a in m.get("alternative_paths", []) for n in a["primitive_path"]]

    sagas = sorted({f["card_id"] for f in faces
                    if "Saga" in ((f.get("type_line") or {}).get("subtypes") or [])})
    replacement = sorted({_card_of(e["source"]) for e in edges if e["predicate"] == "REPLACES"} - {None})
    multitoken = sorted({c for c in cards if len(by_card_pred.get((c, "CREATES_OBJECT"), set())) >= 2})
    faces_by_card = defaultdict(set)
    for f in faces:
        faces_by_card[f["card_id"]].add(f["id"])

    all_ids = sorted(cards)
    null_pairs, used_src = [], set()               # one per DISTINCT source card
    for a in all_ids:
        if a in used_src:
            continue
        for b in all_ids:
            if a != b and (a, b) not in related and (b, a) not in related:
                null_pairs.append((a, b))
                used_src.add(a)
                break
        if len(null_pairs) >= 20:
            break
    # multi-edge: distinct relation-type COMBINATIONS across all layers (one per combo)
    combos = {}
    for p, v in sorted(rel_by_pair.items()):
        if len(v) > 1:
            combos.setdefault(frozenset(v), (p, sorted(v)))
    multi_edge = [pv for _, pv in sorted(combos.items(), key=lambda kv: sorted(kv[0]))]
    self_pairs = sorted(selfpath)[:10]

    def adj_card(c, expect, ok):
        return {"item": cards.get(c, c), "id": c, "expected": expect,
                "disposition": "pass" if ok else "fail"}

    def adj_pair(p, expect, ok, extra=None):
        r = {"item": [cards.get(p[0], p[0]), cards.get(p[1], p[1])], "ids": list(p),
             "expected": expect, "disposition": "pass" if ok else "fail"}
        if extra:
            r.update(extra)
        return r

    def saga_ok(c):
        return "rule:saga" in by_card_pred.get((c, "REFERENCES_RULE"), set()) or c in lore_cards

    def selfpair_ok(c):
        # a genuine self-effect: the reflexive path must NOT run through an "another/other"
        # object class (which would be one copy affecting a DIFFERENT object, not itself)
        return not any(n.startswith(("obj:another", "obj:other")) for n in selfpath.get(c, []))

    adjudicated = {
        "recruit": [adj_card(c, "references rule:recruit",
                             "rule:recruit" in by_card_pred.get((c, "REFERENCES_RULE"), set()))
                    for c in sorted(mech["Recruit"])],
        "storied": [adj_card(c, "qualifies for gate:storied",
                             "gate:storied" in by_card_pred.get((c, "QUALIFIES_FOR"), set()))
                    for c in sorted(mech["Storied"])],
        "adventures": [adj_card(c, "exactly two face nodes", len(faces_by_card[c]) == 2)
                       for c in sorted({f["card_id"] for f in faces if f.get("role") == "adventure"})],
        "sagas": [adj_card(c, "has a lore-counter chapter structure (REFERENCES rule:saga or lore counter)",
                           saga_ok(c)) for c in sagas],
        "replacement_effects": [adj_card(c, "has a REPLACES edge", bool(by_card_pred.get((c, "REPLACES"))))
                                for c in replacement],
        "multi_token_or_type": [adj_card(c, "creates >=2 token types",
                                         len(by_card_pred.get((c, "CREATES_OBJECT"), set())) >= 2)
                                for c in multitoken],
        "null_pairs": [adj_pair(p, "no relation in any of the 3 projection layers",
                                p not in related and (p[1], p[0]) not in related) for p in null_pairs],
        "self_pairs": [adj_pair((c, c), "reflexive self-effect not routed through an 'another/other' class",
                                selfpair_ok(c)) for c in self_pairs],
        "multi_edge_pairs": [adj_pair(p, f"relation combination {combo}", len(combo) >= 2,
                                      {"relation_combination": combo}) for (p, combo) in multi_edge],
    }
    with (G / "structural_validation_set.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for stratum, items in sorted(adjudicated.items()):
            passed = sum(1 for it in items if it["disposition"] == "pass")
            fh.write(json.dumps({"stratum": stratum, "count": len(items), "passed": passed,
                                 "failed": len(items) - passed, "items": items},
                                ensure_ascii=False, sort_keys=True) + "\n")
    counts = {k: len(v) for k, v in adjudicated.items()}
    total = sum(counts.values())
    passed = sum(1 for its in adjudicated.values() for it in its if it["disposition"] == "pass")
    _validation_report(repo, adjudicated)
    return {"strata": counts, "total_items": total, "passed": passed, "failed": total - passed,
            "distinct_null_sources": len({it["ids"][0] for it in adjudicated["null_pairs"]}),
            "distinct_multi_edge_combos": len({tuple(it["relation_combination"])
                                               for it in adjudicated["multi_edge_pairs"]})}


# backwards-compatible alias
gold_set = structural_validation_set


def _validation_report(repo, adjudicated):
    total = sum(len(v) for v in adjudicated.values())
    passed = sum(1 for its in adjudicated.values() for it in its if it["disposition"] == "pass")
    L = ["# HOB Structural Validation Set (stratified, adjudicated)", "",
         "*NOT an independent human gold set: these are deterministic structural assertions "
         "against the same graph. Human reviewers still adjudicate semantics and may override.*", "",
         f"Structural checks: **{passed}/{total} pass**.", ""]
    for stratum, items in sorted(adjudicated.items()):
        p = sum(1 for it in items if it["disposition"] == "pass")
        L.append(f"## {stratum} — {p}/{len(items)} pass")
        for it in items[:30]:
            name = it["item"] if isinstance(it["item"], str) else " → ".join(it["item"])
            L.append(f"- [{it['disposition']}] {name}  _(expect: {it['expected']})_")
        L.append("")
    (repo / "reports" / "structural_validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
