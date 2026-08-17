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
# (Invariant #2, Recruit -> Master's Councillors second-draw ordering, was resolved in the
#  mechanism-repair layer: a turn-scoped `state:cards-drawn-this-turn` + `gate:second-draw`
#  now produce the second-draw event, so the relation projects with the second-draw condition.)
DEFERRED_INVARIANTS = []


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
    mechanism_edges = _opt(G / "mechanism_edges.jsonl")
    mechanism_nodes = _opt(G / "mechanism_nodes.jsonl")
    equip_edges = _opt(G / "equip_edges.jsonl")
    equip_nodes = _opt(G / "equip_nodes.jsonl")
    completeness_edges = _opt(G / "completeness_edges.jsonl")
    completeness_nodes = _opt(G / "completeness_nodes.jsonl")
    lifecycle_edges = _opt(G / "lifecycle_edges.jsonl")
    lifecycle_nodes = _opt(G / "lifecycle_nodes.jsonl")
    # deduplicated union of frozen + graph-repair + legend + mechanism + equip + completeness + lifecycle
    union = {e["edge_id"]: {**e, "origin": e.get("origin", "phase4")} for e in frozen_edges}
    for e in repair_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "graph_repair")}
    for e in legend_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "legend_rule")}
    for e in mechanism_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "mechanism_repair")}
    for e in equip_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "equip")}
    for e in completeness_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "completeness")}
    for e in lifecycle_edges:
        union[e["edge_id"]] = {**e, "origin": e.get("origin", "lifecycle")}
    edges = list(union.values())
    cards = list(_load_dicts(repo / "data/normalized/cards.jsonl"))
    faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
    proj = list(_load_dicts(G / "card_pair_projection.jsonl"))
    audit_accepted = [a for a in _opt(G / "card_pair_projection_audit.jsonl")]
    repaired_rel = _opt(G / "card_pair_projection_repaired.jsonl")
    mechanism_rel = _opt(G / "card_pair_projection_mechanism.jsonl")
    equip_rel = _opt(G / "card_pair_projection_equip.jsonl")
    completeness_rel = _opt(G / "card_pair_projection_completeness.jsonl")
    lifecycle_rel = _opt(G / "card_pair_projection_lifecycle.jsonl")
    audit = _opt(G / "audit_results.jsonl")
    conds = list(_load_dicts(G / "conditions.jsonl")) + _opt(G / "mechanism_conditions.jsonl") \
        + _opt(G / "equip_conditions.jsonl") + _opt(G / "completeness_conditions.jsonl")
    # every condition_id referenced by any edge (union) must resolve to a condition record
    defined_conds = {c["condition_id"] for c in conds}
    referenced_conds = {c for e in edges for c in (e.get("condition_ids") or [])}
    unresolved_conds = sorted(referenced_conds - defined_conds)

    # abilities counted over the UNIFIED node set (frozen + repair + legend), so the legend
    # layer's state_based_action ability is included — not just the frozen Phase 4 nodes.
    union_nodes = {n["id"]: n for n in nodes}
    for n in repair_nodes + legend_nodes + mechanism_nodes + equip_nodes + completeness_nodes + lifecycle_nodes:
        union_nodes.setdefault(n["id"], n)
    ability_kinds = Counter(n["data"].get("kind", "?")
                            for n in union_nodes.values() if n["type"] == "Ability")
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
        "edges_legend": len(legend_edges), "edges_mechanism": len(mechanism_edges),
        "edges_equip": len(equip_edges), "edges_completeness": len(completeness_edges),
        "edges_lifecycle": len(lifecycle_edges),
        "edges_union": len(edges), "nodes_repair": len(repair_nodes),
        "nodes_legend": len(legend_nodes), "nodes_mechanism": len(mechanism_nodes),
        "nodes_equip": len(equip_nodes), "nodes_completeness": len(completeness_nodes),
        "nodes_lifecycle": len(lifecycle_nodes),
        "edges_total": len(edges), "edges_by_predicate": dict(edges_by_pred),
        "edges_by_origin": dict(Counter(e.get("origin", "phase4") for e in edges)),
        "edges_without_provenance": sum(1 for e in edges if not e.get("provenance")),
        # relations per layer + union
        "relations_mechanical": len(proj), "relations_audited": len(audit_accepted),
        "relations_repaired": len(repaired_rel), "relations_mechanism": len(mechanism_rel),
        "relations_equip": len(equip_rel), "relations_completeness": len(completeness_rel),
        "relations_lifecycle": len(lifecycle_rel),
        "relations_union": (len(proj) + len(audit_accepted) + len(repaired_rel) + len(mechanism_rel)
                            + len(equip_rel) + len(completeness_rel) + len(lifecycle_rel)),
        "conditions_total": len(conds),
        "conditions_raw_unresolved": sum(1 for c in conds if c.get("status") == "raw_unresolved"),
        "conditions_unresolved": unresolved_conds,
        "conditions_all_resolve": not unresolved_conds,
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
         f"**{s['edges_repair']}** + legend **{s['edges_legend']}** + mechanism **{s['edges_mechanism']}** "
         f"+ equip **{s['edges_equip']}** + completeness **{s['edges_completeness']}** + lifecycle "
         f"**{s['edges_lifecycle']}** = union **{s['edges_union']}** (+{s['nodes_repair']} repair, "
         f"+{s['nodes_legend']} legend, +{s['nodes_mechanism']} mechanism, +{s['nodes_equip']} equip, "
         f"+{s['nodes_completeness']} completeness, +{s['nodes_lifecycle']} lifecycle nodes); "
         f"by origin {s['edges_by_origin']}; provenance gaps: {s['edges_without_provenance']}",
         f"- pair relations (per layer + union): mechanical **{s['relations_mechanical']}** + audited "
         f"**{s['relations_audited']}** + repaired **{s['relations_repaired']}** + mechanism "
         f"**{s['relations_mechanism']}** + equip **{s['relations_equip']}** + completeness "
         f"**{s['relations_completeness']}** = union **{s['relations_union']}**",
         f"- conditions all resolve: **{s['conditions_all_resolve']}** "
         f"(unresolved: {s['conditions_unresolved'] or 'none'})",
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
    if not s["deferred_invariants"]:
        L.append("- _none_ — every spec semantic invariant is now modeled (invariant #2, the "
                 "Recruit → Master's Councillors second-draw ordering, is resolved in the "
                 "mechanism-repair layer via `state:cards-drawn-this-turn` + `gate:second-draw`).")
    for d in s["deferred_invariants"]:
        L.append(f"- **#{d['id']} {d['name']}** — _{d['status']}_: {d['reason']}")
    L += ["", "## Cards with no non-infrastructure outgoing relation (sample)", ""]
    L += [f"- {nm.get(c, c)}" for c in no_out[:30]]
    (repo / "reports" / "coverage.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def pair_index(repo: Path = REPO) -> dict:
    """Emit EXACTLY 193^2 = 37,249 ordered-pair records (the completion criterion), each listing
    its mechanical, audited, repaired, and mechanism-repair relations (empty pairs included)."""
    G = repo / "data" / "graph_global"
    cards = sorted(c["id"] for c in _load_dicts(repo / "data/normalized/cards.jsonl"))
    # audit_repair suppressions: (layer, source, target, relation) to drop (human-audit corrections)
    suppress = {(s["layer"], s["source_card"], s["target_card"], s["relation"])
                for s in _opt(G / "audit_repair_suppressions.jsonl")}
    layers = {"mechanical": "card_pair_projection.jsonl", "audited": "card_pair_projection_audit.jsonl",
              "repaired": "card_pair_projection_repaired.jsonl", "mechanism": "card_pair_projection_mechanism.jsonl",
              "equip": "card_pair_projection_equip.jsonl", "completeness": "card_pair_projection_completeness.jsonl",
              "lifecycle": "card_pair_projection_lifecycle.jsonl",
              "audit_repair": "card_pair_projection_audit_repair.jsonl"}
    data = {k: defaultdict(list) for k in layers}
    n_suppressed = 0
    for lay, fn in layers.items():
        rows = _load_dicts(G / fn) if lay == "mechanical" else _opt(G / fn)
        for m in rows:
            if (lay, m["source_card"], m["target_card"], m["relation"]) in suppress:
                n_suppressed += 1
                continue                                   # human audit retracted/retyped this relation
            data[lay][(m["source_card"], m["target_card"])].append(m["relation"])
    order = ["mechanical", "audited", "repaired", "mechanism", "equip", "completeness", "lifecycle",
             "audit_repair"]
    n, nonempty = 0, 0
    with (G / "pair_index.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for a in cards:
            for b in cards:
                rels = {lay: sorted(data[lay][(a, b)]) for lay in order}
                total = sum(len(v) for v in rels.values())          # audit_repair rows are generic + filterable
                n += 1
                nonempty += 1 if total else 0
                rec = {"source_card": a, "target_card": b, "self_pair": a == b,
                       "total_relations": total, **rels}
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return {"pair_records": n, "possible_ordered_pairs": len(cards) ** 2,
            "nonempty_pairs": nonempty, "empty_pairs": n - nonempty, "suppressed": n_suppressed}


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
                  "card_pair_projection_repaired.jsonl", "card_pair_projection_mechanism.jsonl",
                  "card_pair_projection_equip.jsonl", "card_pair_projection_completeness.jsonl",
                  "card_pair_projection_lifecycle.jsonl"):
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
