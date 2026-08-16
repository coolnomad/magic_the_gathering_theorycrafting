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


def _opt(path):
    return list(_load_dicts(path)) if path.exists() else []


def coverage(repo: Path = REPO) -> dict:
    G = repo / "data" / "graph_global"
    nodes = list(_load_dicts(G / "nodes.jsonl"))
    edges = list(_load_dicts(G / "edges.jsonl"))
    cards = list(_load_dicts(repo / "data/normalized/cards.jsonl"))
    faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
    proj = list(_load_dicts(G / "card_pair_projection.jsonl"))
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
        "edges_total": len(edges), "edges_by_predicate": dict(edges_by_pred),
        "edges_by_origin": dict(Counter(e.get("origin", "phase4") for e in edges)),
        "edges_without_provenance": sum(1 for e in edges if not e.get("provenance")),
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
         f"- primitive edges: **{s['edges_total']}** by origin {s['edges_by_origin']}; "
         f"provenance gaps: {s['edges_without_provenance']}",
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
    L += ["", "## Cards with no non-infrastructure outgoing relation (sample)", ""]
    L += [f"- {nm.get(c, c)}" for c in no_out[:30]]
    (repo / "reports" / "coverage.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def gold_set(repo: Path = REPO) -> dict:
    """Stratified sample for manual hand-review (spec §Manual gold set)."""
    G = repo / "data" / "graph_global"
    faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
    cards = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
    mech = defaultdict(set)
    for m in _load_dicts(repo / "data/rules/mechanics.jsonl"):
        mech[m["mechanic"]].add(m["card_id"])
    edges = list(_load_dicts(G / "edges.jsonl"))
    proj = list(_load_dicts(G / "card_pair_projection.jsonl"))

    replacement = sorted({_card_of(e["source"]) for e in edges if e["predicate"] == "REPLACES"} - {None})
    multitoken = sorted({c for c, ts in
                         ((c, {e["target"] for e in edges if e["predicate"] == "CREATES_OBJECT"
                               and _card_of(e["source"]) == c}) for c in cards)
                         if len(ts) >= 2})
    pairs = defaultdict(set)
    for m in proj:
        pairs[(m["source_card"], m["target_card"])].add(m["relation"])
    multi_edge = [p for p, v in pairs.items() if len(v) > 1][:20]
    self_pairs = [m for m in proj if m["source_card"] == m["target_card"]][:10]
    related = set(pairs)
    all_ids = list(cards)
    null_pairs = [(a, b) for a in all_ids[:25] for b in all_ids[:25]
                  if a != b and (a, b) not in related][:20]

    sagas = sorted({f["card_id"] for f in faces
                    if "Saga" in ((f.get("type_line") or {}).get("subtypes") or [])})
    strata = {
        "recruit": sorted(mech["Recruit"]), "storied": sorted(mech["Storied"]),
        "adventures": sorted({f["card_id"] for f in faces if f.get("role") == "adventure"}),
        "sagas": sagas, "replacement_effects": replacement,
        "multi_token_or_type": multitoken,
        "null_pairs": null_pairs, "self_pairs": [m["source_card"] for m in self_pairs],
        "multi_edge_pairs": multi_edge,
    }
    with (G / "gold_set.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for stratum, items in sorted(strata.items()):
            fh.write(json.dumps({"stratum": stratum, "count": len(items),
                                 "items": [(list(map(lambda x: cards.get(x, x), it)) if isinstance(it, (list, tuple))
                                            else cards.get(it, it)) for it in items]},
                                ensure_ascii=False, sort_keys=True) + "\n")
    counts = {k: len(v) for k, v in strata.items()}
    _gold_report(repo, strata, cards)
    return {"strata": counts, "total_items": sum(counts.values())}


def _gold_report(repo, strata, cards):
    L = ["# HOB Manual Gold Set (stratified sample for hand review)", "",
         "Review each stratum by hand before full acceptance.", ""]
    for stratum, items in sorted(strata.items()):
        L.append(f"## {stratum} ({len(items)})")
        for it in items[:30]:
            if isinstance(it, (list, tuple)):
                L.append(f"- {' → '.join(cards.get(x, x) for x in it)}")
            else:
                L.append(f"- {cards.get(it, it)}")
        L.append("")
    (repo / "reports" / "gold_set.md").write_text("\n".join(L) + "\n", encoding="utf-8")
