"""Phase 1 orchestration: read the frozen snapshot, normalize, extract, validate,
and write deliverables. Idempotent and resumable — every run fully rewrites its
outputs from the raw snapshot.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from .extract_mechanical import extract_face
from .mechanics import detect_mechanics
from . import rules
from .models import (
    Card,
    ConditionRecord,
    Edge,
    Face,
    Gate,
    MechanicalExtraction,
    MechanicDetection,
    Node,
    Provenance,
    StructuredCondition,
    TokenSpec,
    UnresolvedExtraction,
)
from .normalize import (
    canonicalize_tokens,
    correct_tokens,
    enrich_tokens,
    extract_tokens,
    normalize_card,
)

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw" / "scryfall_hob.json"


def _write_jsonl(path: Path, rows: list[BaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(r.model_dump_json() + "\n")


def export_schemas(repo: Path = REPO) -> list[str]:
    """Emit JSON Schema for each Phase 1 model (schemas-first discipline)."""
    out = repo / "schema"
    out.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {
        "card": Card, "face": Face, "token": TokenSpec,
        "mechanic_detection": MechanicDetection,
        "mechanical_extraction": MechanicalExtraction,
        "unresolved_extraction": UnresolvedExtraction,
        "condition": ConditionRecord,
        "node": Node, "edge": Edge, "gate": Gate,
        "structured_condition": StructuredCondition,
    }
    written = []
    for name, model in models.items():
        p = out / f"{name}.schema.json"
        p.write_text(json.dumps(model.model_json_schema(), indent=2), encoding="utf-8")
        written.append(str(p.relative_to(repo)))
    return written


def run(repo: Path = REPO) -> dict:
    raw_cards = json.loads((repo / "data" / "raw" / "scryfall_hob.json").read_text(encoding="utf-8"))

    cards: list[Card] = []
    faces: list[Face] = []
    token_lists: list[list[TokenSpec]] = []
    mechanics: list[MechanicDetection] = []
    keyword_attr_ambiguous: list[dict] = []
    extractions: list[MechanicalExtraction] = []
    unresolved: list[UnresolvedExtraction] = []
    conditions: list[ConditionRecord] = []

    for raw in raw_cards:
        card, cfaces = normalize_card(raw)
        cards.append(card)
        faces.extend(cfaces)
        token_lists.append(extract_tokens(raw, card.id))

        # Scryfall keywords are card-level HINTS; attach each to the face(s) whose
        # Oracle text supports it (word-boundary match). For MULTIFACE cards, do NOT
        # fall back to the primary face when unsupported — a card-level keyword cannot
        # determine face ownership on a multiface card; record an ambiguous attribution
        # instead. Single-face cards attach to their one face (the card IS the face).
        for kw in card.keywords_scryfall:
            supporting = [f for f in cfaces if f.oracle_text
                          and re.search(r"\b" + re.escape(kw) + r"\b", f.oracle_text, re.I)]
            if supporting:
                targets = supporting
            elif len(cfaces) == 1:
                targets = [cfaces[0]]
            else:
                keyword_attr_ambiguous.append({
                    "card_id": card.id, "card": card.name, "keyword": kw,
                    "candidate_faces": [f.id for f in cfaces],
                    "reason": "card-level keyword not supported by any face's Oracle text/type line"})
                continue
            for f in targets:
                mechanics.append(MechanicDetection(
                    face_id=f.id, card_id=card.id, mechanic=kw, source="scryfall_keyword",
                    provenance=Provenance(card_id=card.id, face_id=f.id, source="scryfall.keywords", text=kw)))
        for f in cfaces:
            mechanics.extend(detect_mechanics(f.id, card.id, f.oracle_text))
            ex, un, co = extract_face(f.id, card.id, f.oracle_text)
            extractions.extend(ex)
            unresolved.extend(un)
            conditions.extend(co)

    tokens = canonicalize_tokens(token_lists)
    tokens_raw_path = repo / "data" / "raw" / "scryfall_hob_tokens.json"
    if tokens_raw_path.exists():
        token_raw_by_id = {t["id"]: t for t in json.loads(tokens_raw_path.read_text(encoding="utf-8"))}
        enrich_tokens(tokens, token_raw_by_id)

    def _blob(raw: dict) -> str:
        t = raw.get("oracle_text", "") or ""
        for f in raw.get("card_faces", []):
            t += "\n" + (f.get("oracle_text", "") or "")
        return t

    correct_tokens(tokens, {f"card:{raw['oracle_id']}": _blob(raw) for raw in raw_cards})

    nd = repo / "data" / "normalized"
    _write_jsonl(nd / "cards.jsonl", cards)
    _write_jsonl(nd / "faces.jsonl", faces)
    _write_jsonl(nd / "tokens.jsonl", tokens)
    _write_jsonl(nd / "mechanical_extractions.jsonl", extractions)
    rd = repo / "data" / "rules"
    _write_jsonl(rd / "mechanics.jsonl", mechanics)
    _write_jsonl(rd / "conditions.jsonl", conditions)
    with (rd / "keyword_attribution_ambiguous.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in keyword_attr_ambiguous:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    _write_jsonl(repo / "data" / "review" / "unresolved.jsonl", unresolved)

    schemas = export_schemas(repo)
    stats = _coverage(cards, faces, tokens, mechanics, extractions, unresolved, conditions, raw_cards)
    _write_reports(repo, stats, unresolved)
    stats["schemas_written"] = schemas
    return stats


def _load_dicts(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


_PERMANENT_TYPES = {"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"}


def _storied_qualifies(parsed: dict | None) -> bool:
    """A permanent that is Legendary, an Artifact, and/or a Saga qualifies for Storied."""
    if not parsed:
        return False
    types = set(parsed.get("types", []))
    if not (types & _PERMANENT_TYPES):
        return False
    return (
        "Legendary" in parsed.get("supertypes", [])
        or "Artifact" in types
        or "Saga" in parsed.get("subtypes", [])
    )


def build_templates(repo: Path = REPO) -> dict:
    """Phase 2: instantiate mechanic rule templates on the Phase 1 normalized set."""
    nd = repo / "data" / "normalized"
    faces = _load_dicts(nd / "faces.jsonl")
    tokens = _load_dicts(nd / "tokens.jsonl")
    mechanics = _load_dicts(repo / "data" / "rules" / "mechanics.jsonl")

    faces_by_id = {f["id"]: f for f in faces}
    faces_by_card: dict[str, list[dict]] = {}
    for f in faces:
        faces_by_card.setdefault(f["card_id"], []).append(f)

    # mechanic -> set of face_ids (from Oracle-text detections)
    by_mech: dict[str, set[str]] = {}
    for m in mechanics:
        if m["source"] == "oracle_text":
            by_mech.setdefault(m["mechanic"], set()).add(m["face_id"])

    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)

    counts = {"recruit": 0, "storied_payoff": 0, "hone": 0, "adventure": 0, "saga": 0,
              "amass": 0, "typecycling": 0,
              "storied_qualifier_faces": 0, "storied_qualifier_tokens": 0}
    # all detected mechanics per face (any source), for keyword templates like Amass
    mech_all_by_face: dict[str, set[str]] = {}
    for m in mechanics:
        mech_all_by_face.setdefault(m["face_id"], set()).add(m["mechanic"])

    for fid in sorted(by_mech.get("Recruit", set())):
        rules.expand_recruit(gb, faces_by_id[fid]); counts["recruit"] += 1
    for fid in sorted(by_mech.get("Storied", set())):
        rules.expand_storied_payoff(gb, faces_by_id[fid]); counts["storied_payoff"] += 1
    for fid in sorted(by_mech.get("Hone", set())):
        rules.expand_hone(gb, faces_by_id[fid]); counts["hone"] += 1

    # Adventure: pair primary + adventure faces by card
    for cid, fs in faces_by_card.items():
        prim = next((f for f in fs if f["role"] == "primary"), None)
        adv = next((f for f in fs if f["role"] == "adventure"), None)
        if prim and adv:
            rules.expand_adventure(gb, prim, adv); counts["adventure"] += 1

    # Saga: single primary face whose parsed subtypes include Saga
    for f in faces:
        parsed = f.get("type_line") or {}
        if f["role"] == "primary" and "Saga" in parsed.get("subtypes", []):
            rules.expand_saga(gb, f); counts["saga"] += 1

    # Amass: faces with the Amass keyword; parse subtype + N from "amass <Subtype> <N>"
    _AMASS = re.compile(r"\bamass\s+(\w+)\s+([0-9]+|X)\b", re.I)
    for f in faces:
        if "Amass" in mech_all_by_face.get(f["id"], set()):
            m = _AMASS.search(f.get("oracle_text") or "")
            subtype, n = (m.group(1), m.group(2)) if m else ("Goblin", "N")
            rules.expand_amass(gb, f, subtype, n); counts["amass"] += 1

    # Typecycling variants (Halflingcycling, Mountaincycling, ...); exclude bare "Cycling"
    _TYPECYC = re.compile(r"\b([A-Z][a-z]+)cycling\b")
    for f in faces:
        m = _TYPECYC.search(f.get("oracle_text") or "")
        if m:
            rules.expand_typecycling(gb, f, m.group(1)); counts["typecycling"] += 1

    # Storied contributors: qualifying permanent faces + qualifying tokens
    for f in faces:
        if f["role"] != "primary":
            continue
        if _storied_qualifies(f.get("type_line")):
            prov = [Provenance(card_id=f["card_id"], face_id=f["id"],
                               source="rule.template:storied", text=f.get("type_line_raw"),
                               rule_ref=rules.RULE_REFS["storied"])]
            rules.storied_qualifier(gb, f["id"], "CardFace", f.get("name", f["id"]), prov)
            counts["storied_qualifier_faces"] += 1
    for t in tokens:
        if _storied_qualifies(t.get("type_line")):
            prov = [Provenance(card_id="", source="rule.template:storied",
                               text=t.get("type_line_raw"), rule_ref=rules.RULE_REFS["storied"])]
            rules.storied_qualifier(gb, t["id"], "TokenSpec", t.get("name", t["id"]), prov)
            counts["storied_qualifier_tokens"] += 1

    gd = repo / "data" / "graph"
    _write_jsonl(gd / "nodes.jsonl", list(gb.nodes.values()))
    _write_jsonl(gd / "edges.jsonl", gb.edges)
    _write_jsonl(gd / "gates.jsonl", list(gb.gates.values()))
    _write_jsonl(gd / "conditions.jsonl", list(gb.conditions.values()))

    stats = _graph_coverage(gb, counts)
    _write_graph_report(repo, stats)
    export_schemas(repo)
    return stats


def _graph_coverage(gb: "rules.GraphBuilder", counts: dict) -> dict:
    from collections import Counter
    node_types = Counter(n.type for n in gb.nodes.values())
    edge_preds = Counter(e.predicate for e in gb.edges)
    node_ids = set(gb.nodes)
    dangling = [e.edge_id for e in gb.edges if e.source not in node_ids or e.target not in node_ids]
    return {
        "instantiations": counts,
        "nodes": len(gb.nodes),
        "edges": len(gb.edges),
        "gates": len(gb.gates),
        "conditions": len(gb.conditions),
        "node_types": dict(node_types),
        "edge_predicates": dict(edge_preds),
        "dangling_edges": dangling,
    }


def _write_graph_report(repo: Path, stats: dict) -> None:
    reports = repo / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    lines = ["# HOB Phase 2 — Mechanic Templates / Graph Coverage", "",
             "> Rule-expansion graph fragments. Possibility only; no value judgments. (spec)", "",
             f"- **nodes**: {stats['nodes']}", f"- **edges**: {stats['edges']}",
             f"- **gates**: {stats['gates']}", f"- **conditions**: {stats['conditions']}",
             f"- **dangling edges**: {len(stats['dangling_edges'])}", "",
             "## Instantiations", ""]
    for k, v in stats["instantiations"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Node types", ""]
    for k, v in sorted(stats["node_types"].items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Edge predicates", ""]
    for k, v in sorted(stats["edge_predicates"].items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    (reports / "graph_coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _coverage(cards, faces, tokens, mechanics, extractions, unresolved, conditions, raw_cards) -> dict:
    layouts = Counter(c.layout for c in cards)
    adv = [c for c in cards if c.layout == "adventure"]
    ext_by_kind = Counter(e.kind for e in extractions)
    unr_by_signal = Counter(u.signal for u in unresolved)
    mech_by_source = Counter(m.source for m in mechanics)
    named = Counter(m.mechanic for m in mechanics if m.source == "oracle_text")
    faces_with_text = sum(1 for f in faces if f.oracle_text)
    faces_no_edges = sum(
        1 for f in faces
        if f.oracle_text and not any(e.face_id == f.id for e in extractions)
    )
    return {
        "cards": len(cards),
        "faces": len(faces),
        "tokens": len(tokens),
        "layouts": dict(layouts),
        "adventures": len(adv),
        "adventure_faces_ok": all(len(c.face_ids) == 2 for c in adv),
        "sagas": layouts.get("saga", 0),
        "faces_with_oracle_text": faces_with_text,
        "faces_with_text_no_extraction": faces_no_edges,
        "mechanics_total": len(mechanics),
        "mechanics_by_source": dict(mech_by_source),
        "named_mechanics_oracle": dict(named),
        "extractions_total": len(extractions),
        "extractions_by_kind": dict(ext_by_kind),
        "unresolved_total": len(unresolved),
        "unresolved_by_signal": dict(unr_by_signal),
        "conditions_total": len(conditions),
    }


def _write_reports(repo: Path, stats: dict, unresolved: list[UnresolvedExtraction]) -> None:
    reports = repo / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    cov = ["# HOB Phase 1 — Coverage Report", "",
           "> Coverage is not correctness. Do not maximize edge count. (spec)", ""]
    for k in ("cards", "faces", "tokens", "adventures", "adventure_faces_ok", "sagas",
              "faces_with_oracle_text", "faces_with_text_no_extraction",
              "mechanics_total", "extractions_total", "unresolved_total", "conditions_total"):
        cov.append(f"- **{k}**: {stats[k]}")
    cov += ["", "## Layouts", ""]
    for k, v in sorted(stats["layouts"].items()):
        cov.append(f"- {k}: {v}")
    cov += ["", "## Mechanics by source", ""]
    for k, v in sorted(stats["mechanics_by_source"].items()):
        cov.append(f"- {k}: {v}")
    cov += ["", "## Named mechanics detected in Oracle text", ""]
    for k, v in sorted(stats["named_mechanics_oracle"].items()):
        cov.append(f"- {k}: {v}")
    cov += ["", "## Extractions by kind", ""]
    for k, v in sorted(stats["extractions_by_kind"].items(), key=lambda x: -x[1]):
        cov.append(f"- {k}: {v}")
    cov += ["", "## Unresolved signals by kind", ""]
    for k, v in sorted(stats["unresolved_by_signal"].items(), key=lambda x: -x[1]):
        cov.append(f"- {k}: {v}")
    (reports / "coverage.md").write_text("\n".join(cov) + "\n", encoding="utf-8")

    unr = ["# HOB Phase 1 — Unresolved Extraction Queue", "",
           "Signals whose deterministic parse was ambiguous; queued for the Phase 3 LLM.",
           "We never guess — these are recorded, not resolved.", "",
           f"Total: {len(unresolved)}", ""]
    for u in unresolved:
        txt = (u.provenance.text or "").replace("\n", " ")
        unr.append(f"- `{u.card_id}` [{u.signal}] {u.reason} — “{txt}”")
    (reports / "unresolved.md").write_text("\n".join(unr) + "\n", encoding="utf-8")


def validate(repo: Path = REPO) -> dict:
    """Reload every emitted jsonl and re-validate against its model (integrity check)."""
    checks = {
        "data/normalized/cards.jsonl": Card,
        "data/normalized/faces.jsonl": Face,
        "data/normalized/tokens.jsonl": TokenSpec,
        "data/normalized/mechanical_extractions.jsonl": MechanicalExtraction,
        "data/rules/mechanics.jsonl": MechanicDetection,
        "data/rules/conditions.jsonl": ConditionRecord,
        "data/review/unresolved.jsonl": UnresolvedExtraction,
        "data/graph/nodes.jsonl": Node,
        "data/graph/edges.jsonl": Edge,
        "data/graph/gates.jsonl": Gate,
        "data/graph/conditions.jsonl": StructuredCondition,
    }
    result = {}
    for rel, model in checks.items():
        p = repo / rel
        if not p.exists():
            continue
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                model.model_validate_json(line)
                n += 1
        result[rel] = n

    # integrity: every graph edge endpoint must resolve to a node
    gd = repo / "data" / "graph"
    if (gd / "nodes.jsonl").exists():
        node_ids = {json.loads(l)["id"] for l in (gd / "nodes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
        dangling = []
        for l in (gd / "edges.jsonl").read_text(encoding="utf-8").splitlines():
            if l.strip():
                e = json.loads(l)
                if e["source"] not in node_ids or e["target"] not in node_ids:
                    dangling.append(e["edge_id"])
        result["graph_dangling_edges"] = dangling
    return result
