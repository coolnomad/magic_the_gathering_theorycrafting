"""Phase 1 orchestration: read the frozen snapshot, normalize, extract, validate,
and write deliverables. Idempotent and resumable — every run fully rewrites its
outputs from the raw snapshot.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from .extract_mechanical import extract_face
from .mechanics import detect_mechanics
from .models import (
    Card,
    ConditionRecord,
    Face,
    MechanicalExtraction,
    MechanicDetection,
    Provenance,
    TokenSpec,
    UnresolvedExtraction,
)
from .normalize import canonicalize_tokens, extract_tokens, normalize_card

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
    extractions: list[MechanicalExtraction] = []
    unresolved: list[UnresolvedExtraction] = []
    conditions: list[ConditionRecord] = []

    for raw in raw_cards:
        card, cfaces = normalize_card(raw)
        cards.append(card)
        faces.extend(cfaces)
        token_lists.append(extract_tokens(raw, card.id))

        # Scryfall keywords are card-level; attach to the primary (index-0) face.
        primary = cfaces[0]
        for kw in card.keywords_scryfall:
            mechanics.append(
                MechanicDetection(
                    face_id=primary.id, card_id=card.id, mechanic=kw,
                    source="scryfall_keyword",
                    provenance=Provenance(card_id=card.id, face_id=primary.id, source="scryfall.keywords", text=kw),
                )
            )
        for f in cfaces:
            mechanics.extend(detect_mechanics(f.id, card.id, f.oracle_text))
            ex, un, co = extract_face(f.id, card.id, f.oracle_text)
            extractions.extend(ex)
            unresolved.extend(un)
            conditions.extend(co)

    tokens = canonicalize_tokens(token_lists)

    nd = repo / "data" / "normalized"
    _write_jsonl(nd / "cards.jsonl", cards)
    _write_jsonl(nd / "faces.jsonl", faces)
    _write_jsonl(nd / "tokens.jsonl", tokens)
    _write_jsonl(nd / "mechanical_extractions.jsonl", extractions)
    rd = repo / "data" / "rules"
    _write_jsonl(rd / "mechanics.jsonl", mechanics)
    _write_jsonl(rd / "conditions.jsonl", conditions)
    _write_jsonl(repo / "data" / "review" / "unresolved.jsonl", unresolved)

    schemas = export_schemas(repo)
    stats = _coverage(cards, faces, tokens, mechanics, extractions, unresolved, conditions, raw_cards)
    _write_reports(repo, stats, unresolved)
    stats["schemas_written"] = schemas
    return stats


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
    }
    result = {}
    for rel, model in checks.items():
        p = repo / rel
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                model.model_validate_json(line)
                n += 1
        result[rel] = n
    return result
