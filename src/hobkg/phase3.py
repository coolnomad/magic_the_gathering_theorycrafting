"""Phase 3: LLM semantic extraction — control plane.

The "LLM" is a Claude Code session / sub-agents (not the Anthropic API — see the
user's standing preference). This module is the deterministic control plane:

  build_tasks()      -> one self-contained task packet per Oracle-bearing face
  build_prompt()     -> the extractor prompt (shared context + packet + schema)
  critic_prompt()    -> the independent-critic prompt over a candidate
  validate_output()  -> JSON-Schema + predicate-vocab + provenance + no-evaluative-language
  ingest()           -> route validated extractions to candidates / rejections
  reconcile()        -> accept where extractor & critic agree; queue the rest

No model calls happen here. Agents produce JSON conforming to
schema/llm_output.schema.json; this module validates and routes it. Never
silently repair invalid output — reject or queue it (spec discipline #8).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

from jsonschema import Draft202012Validator

from . import rules
from .models import Predicate
from .pipeline import REPO, _load_dicts, _write_jsonl  # reuse helpers

SCHEMA_VERSION = "hobkg-llm-output-1"
PREDICATES = list(get_args(Predicate))
NODE_TYPES = [
    "Card", "CardFace", "Ability", "Operation", "Event", "Resource",
    "ObjectClass", "Zone", "CounterType", "State", "Gate", "Cost",
    "Effect", "Rule", "TokenSpec",
]

# Curated evaluative / value-judgment terms the LLM must not use (spec: reject
# outputs containing evaluative language). Conservative to avoid false rejects.
_EVALUATIVE = re.compile(
    r"\b(synerg(y|ies|ize|istic)|win\s?rate|good card|bad card|better than|worse than|"
    r"overpowered|underpowered|\bbomb\b|archetype|tier\s?\d|playab|strong(er|est)?\b|"
    r"weak(er|est)?\b|powerful|value\s?engine)\b",
    re.I,
)


# --- output schema (single source of truth; exported to schema/) ------------

def llm_output_schema() -> dict:
    prov = {
        "type": "object",
        "properties": {
            "oracle_span": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
            "text": {"type": "string"},
            "rule_ref": {"type": "string"},
            "note": {"type": "string"},
        },
        "additionalProperties": True,
    }
    ability = {
        "type": "object",
        "required": ["ability_id", "kind", "effects", "oracle_spans", "confidence", "unresolved"],
        "additionalProperties": False,
        "properties": {
            "ability_id": {"type": "string"},
            "kind": {"enum": ["triggered", "activated", "static", "replacement", "spell_effect"]},
            "trigger": {"type": ["object", "null"]},
            "costs": {"type": "array"},
            "conditions": {"type": "array"},
            "effects": {"type": "array"},
            "oracle_spans": {
                "type": "array", "minItems": 1,
                "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
            },
            "confidence": {"enum": ["high", "medium", "low"]},
            "unresolved": {"type": "array", "items": {"type": "string"}},
        },
    }
    edge = {
        "type": "object",
        "required": ["source", "target", "predicate", "provenance"],
        "additionalProperties": False,
        "properties": {
            "source": {"type": "string"},
            "target": {"type": "string"},
            "predicate": {"enum": PREDICATES},
            "polarity": {"enum": ["positive", "negative"]},
            "timing": {"type": ["string", "null"]},
            "scope": {"type": ["string", "null"]},
            "optional": {"type": "boolean"},
            "condition": {"type": ["string", "object", "null"]},
            "certainty": {"enum": ["rules_explicit", "high", "medium", "low"]},
            "provenance": prov,
        },
    }
    ext = {
        "type": "object",
        "required": ["proposed_predicate", "rationale"],
        "additionalProperties": False,
        "properties": {
            "proposed_predicate": {"type": "string"},
            "rationale": {"type": "string"},
            "oracle_span": {"type": "array", "items": {"type": "integer"}},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "hobkg LLM extraction output",
        "type": "object",
        "required": ["face_id", "abilities", "proposed_edges", "schema_extension_requests"],
        "additionalProperties": False,
        "properties": {
            "face_id": {"type": "string"},
            "abilities": {"type": "array", "items": ability},
            "proposed_edges": {"type": "array", "items": edge},
            "schema_extension_requests": {"type": "array", "items": ext},
        },
    }


def export_schema(repo: Path = REPO) -> str:
    p = repo / "schema" / "llm_output.schema.json"
    p.write_text(json.dumps(llm_output_schema(), indent=2), encoding="utf-8")
    return str(p.relative_to(repo))


# --- shared context (stable across faces) -----------------------------------

def _mechanic_templates() -> list[dict]:
    return [
        {"mechanic": "Recruit", "rule_ref": rules.RULE_REFS["recruit"],
         "summary": "Keyword action: draw a card, then discard a card; if the discarded card was nonland, create a 1/1 white Human Soldier."},
        {"mechanic": "Storied", "rule_ref": rules.RULE_REFS["storied"],
         "summary": "Once you control >=3 permanents that are legendary, artifacts, and/or Sagas, you get the enduring story designation for the rest of the game."},
        {"mechanic": "hone", "rule_ref": rules.RULE_REFS["hone"],
         "summary": "A hone counter on an Equipment gives +1/+0 to the creature that Equipment is attached to."},
        {"mechanic": "Adventure", "rule_ref": rules.RULE_REFS["adventure"],
         "summary": "Cast the Adventure (instant/sorcery) face from hand; on resolution it exiles; you may later cast the permanent face from exile. The permanent may also be cast normally from hand."},
        {"mechanic": "Saga", "rule_ref": rules.RULE_REFS["saga"],
         "summary": "Enters with a lore counter, adds one after your draw step; chapter abilities trigger as the lore count reaches their number; sacrificed after the final chapter."},
    ]


def build_shared_context(repo: Path = REPO) -> dict:
    tokens = _load_dicts(repo / "data" / "normalized" / "tokens.jsonl")
    known_tokens = [
        {"id": t["id"], "name": t["name"], "type_line": t.get("type_line_raw"),
         "colors": t.get("colors", []), "power": t.get("power"), "toughness": t.get("toughness"),
         "oracle_text": t.get("oracle_text")}
        for t in tokens
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "controlled_predicates": PREDICATES,
        "node_types": NODE_TYPES,
        "mechanic_templates": _mechanic_templates(),
        "known_tokens": known_tokens,
        "relevant_rules": {
            "recruit": rules.RULE_REFS["recruit"], "storied": rules.RULE_REFS["storied"],
            "hone": rules.RULE_REFS["hone"], "adventure": rules.RULE_REFS["adventure"],
            "saga": rules.RULE_REFS["saga"],
        },
    }


# --- per-face task packets ---------------------------------------------------

def safe_id(face_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", face_id)


def build_tasks(repo: Path = REPO) -> dict:
    faces = _load_dicts(repo / "data" / "normalized" / "faces.jsonl")
    cards = {c["id"]: c for c in _load_dicts(repo / "data" / "normalized" / "cards.jsonl")}
    exts = _load_dicts(repo / "data" / "normalized" / "mechanical_extractions.jsonl")
    mechs = _load_dicts(repo / "data" / "rules" / "mechanics.jsonl")
    ext_by_face: dict[str, list] = {}
    for e in exts:
        ext_by_face.setdefault(e["face_id"], []).append(e)
    mech_by_face: dict[str, list] = {}
    for m in mechs:
        mech_by_face.setdefault(m["face_id"], []).append(m["mechanic"])

    tasks_dir = repo / "data" / "llm" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    index = []
    n = 0
    for f in faces:
        if not f.get("oracle_text"):
            continue  # spec: only Oracle-bearing faces (209 of 210)
        card = cards[f["card_id"]]
        packet = {
            "face_id": f["id"],
            "card": {"id": card["id"], "name": card["name"], "layout": card["layout"],
                     "color_identity": card.get("color_identity", []),
                     "keywords_scryfall": card.get("keywords_scryfall", [])},
            "face": {"id": f["id"], "name": f["name"], "role": f["role"],
                     "type_line": f.get("type_line_raw"), "mana_cost": f.get("mana_cost_raw"),
                     "power": f.get("power"), "toughness": f.get("toughness"),
                     "produced_mana": f.get("produced_mana", []),
                     "oracle_text": f["oracle_text"]},
            "detected_mechanics": sorted(set(mech_by_face.get(f["id"], []))),
            "mechanical_extractions": [
                {"kind": e["kind"], "quantity": e.get("quantity"),
                 "detail": e.get("detail", {}), "qualifiers": e.get("qualifiers", []),
                 "text": e["provenance"].get("text")}
                for e in ext_by_face.get(f["id"], [])
            ],
        }
        (tasks_dir / f"{safe_id(f['id'])}.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"face_id": f["id"], "card": card["name"], "file": f"{safe_id(f['id'])}.json"})
        n += 1

    (repo / "data" / "llm" / "tasks_index.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in index) + "\n", encoding="utf-8")
    shared = build_shared_context(repo)
    (repo / "data" / "llm" / "shared_context.json").write_text(
        json.dumps(shared, ensure_ascii=False, indent=2), encoding="utf-8")
    export_schema(repo)
    return {"faces_with_oracle_text": n, "tasks_dir": str(tasks_dir.relative_to(repo))}


# --- prompts (used by the spawned agents) -----------------------------------

EXTRACTOR_SYSTEM = """\
You extract a rules-grounded, mechanistic structured representation of ONE Magic: The Gathering
card face for the HOB knowledge graph. Output JSON only, conforming to the provided schema.

DO:
1. Split the Oracle text into distinct abilities/clauses; classify each kind
   (triggered|activated|static|replacement|spell_effect).
2. Identify trigger, costs, conditions, effects, duration, controller, optionality.
3. Resolve pronouns/local references ("it", "that card", "this creature", "this way").
4. Distinguish costs from effects and replacement effects from triggers.
5. Identify resources/states produced and requirements consumed; conditional branches and ordering.
6. Identify when one effect changes the magnitude/timing/target-set/availability of another.
7. Cite exact Oracle character spans [start,end) for every ability and proposed edge.
8. Flag rules ambiguity in `unresolved` rather than guessing.
9. Propose a controlled-vocabulary extension (schema_extension_requests) only if no predicate fits.

DO NOT:
- infer that a card is good/bad, or infer empirical synergy or win rate;
- use color/archetype co-membership as an interaction; invent edges from shared theme;
- treat co-occurrence as causation; omit conditions to simplify;
- infer opponent cooperation; assert a pair interaction without an explicit mechanistic path;
- translate flavor text into mechanics; use ANY evaluative/value-judgment language.

Only use predicates from `controlled_predicates` and node types from `node_types`.
Every proposed_edge must carry provenance (an oracle_span or a rule_ref). Return JSON only."""

CRITIC_SYSTEM = """\
You are an INDEPENDENT critic of a candidate structured extraction of one MTG card face.
Given the Oracle text, normalized fields, mechanic rules, and the candidate assertions:
1. identify assertions not entailed by the rules;
2. identify missing conditions, scope, timing, optionality, or duration;
3. identify omitted mechanistic outputs or requirements;
4. identify incorrect identity/pronoun resolution;
5. return CORRECTED JSON (same schema), not prose. Do not add evaluative language.
Return JSON only conforming to the schema."""


def build_prompt(face_id: str, repo: Path = REPO) -> str:
    shared = json.loads((repo / "data" / "llm" / "shared_context.json").read_text(encoding="utf-8"))
    packet = json.loads((repo / "data" / "llm" / "tasks" / f"{safe_id(face_id)}.json").read_text(encoding="utf-8"))
    schema = llm_output_schema()
    return (
        f"{EXTRACTOR_SYSTEM}\n\n"
        f"# Shared context\n{json.dumps(shared, ensure_ascii=False)}\n\n"
        f"# Output JSON schema\n{json.dumps(schema)}\n\n"
        f"# Card face to extract\n{json.dumps(packet, ensure_ascii=False, indent=2)}\n\n"
        f'Return a single JSON object for face_id "{face_id}".'
    )


def critic_prompt(face_id: str, candidate: dict, repo: Path = REPO) -> str:
    packet = json.loads((repo / "data" / "llm" / "tasks" / f"{safe_id(face_id)}.json").read_text(encoding="utf-8"))
    schema = llm_output_schema()
    return (
        f"{CRITIC_SYSTEM}\n\n"
        f"# Output JSON schema\n{json.dumps(schema)}\n\n"
        f"# Card face\n{json.dumps(packet, ensure_ascii=False, indent=2)}\n\n"
        f"# Candidate extraction to review\n{json.dumps(candidate, ensure_ascii=False)}\n\n"
        f'Return the corrected JSON object for face_id "{face_id}".'
    )


# --- validation --------------------------------------------------------------

_VALIDATOR = Draft202012Validator(llm_output_schema())


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def validate_output(obj: dict, face_id: str | None = None, oracle_len: int | None = None) -> list[str]:
    """Return a list of validation errors; empty list means the output is acceptable."""
    errors = [f"schema: {e.message}" for e in _VALIDATOR.iter_errors(obj)]
    if face_id is not None and obj.get("face_id") != face_id:
        errors.append(f"face_id mismatch: expected {face_id}, got {obj.get('face_id')}")
    # evaluative language
    for s in _strings(obj):
        m = _EVALUATIVE.search(s)
        if m:
            errors.append(f"evaluative language: '{m.group(0)}'")
            break
    # oracle spans within bounds
    if oracle_len is not None:
        for ab in obj.get("abilities", []):
            for span in ab.get("oracle_spans", []):
                if len(span) == 2 and not (0 <= span[0] <= span[1] <= oracle_len):
                    errors.append(f"oracle span out of bounds: {span} (len {oracle_len})")
    return errors


def _oracle_len(face_id: str, repo: Path) -> int | None:
    p = repo / "data" / "llm" / "tasks" / f"{safe_id(face_id)}.json"
    if not p.exists():
        return None
    return len(json.loads(p.read_text(encoding="utf-8"))["face"]["oracle_text"])


# --- ingest & reconcile ------------------------------------------------------

def _write_dicts(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _load_json_dir(d: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and obj.get("face_id"):
            out[obj["face_id"]] = obj
    return out


def ingest(repo: Path = REPO) -> dict:
    """Validate raw extractor outputs (data/llm/extractions/*.json) and route them to
    llm_candidates.jsonl (valid) or llm_rejections.jsonl (invalid). Never repairs."""
    raw = _load_json_dir(repo / "data" / "llm" / "extractions")
    candidates, rejections = [], []
    for face_id, obj in raw.items():
        errs = validate_output(obj, face_id=face_id, oracle_len=_oracle_len(face_id, repo))
        if errs:
            rejections.append({"face_id": face_id, "errors": errs, "raw": obj})
        else:
            candidates.append(obj)
    review = repo / "data" / "review"
    _write_dicts(review / "llm_candidates.jsonl", candidates)
    _write_dicts(review / "llm_rejections.jsonl", rejections)
    return {"extractions": len(raw), "candidates": len(candidates), "rejections": len(rejections)}


def _edge_key(e: dict) -> tuple:
    return (e["source"], e["predicate"], e["target"])


def _ability_key(a: dict) -> tuple:
    span = tuple(a["oracle_spans"][0]) if a.get("oracle_spans") else ()
    return (a["kind"], span)


def reconcile(repo: Path = REPO) -> dict:
    """Accept assertions on which extractor and critic agree AND which validate;
    queue the rest (spec Phase 3 second-pass acceptance rule)."""
    candidates = {c["face_id"]: c for c in _load_dicts(repo / "data" / "review" / "llm_candidates.jsonl")}
    critiques = _load_json_dir(repo / "data" / "llm" / "critiques")
    accepted, queued = [], []
    for face_id, cand in candidates.items():
        crit = critiques.get(face_id)
        if crit is None:
            queued.append({"face_id": face_id, "reason": "no critic review", "candidate": cand})
            continue
        errs = validate_output(crit, face_id=face_id, oracle_len=_oracle_len(face_id, repo))
        if errs:
            queued.append({"face_id": face_id, "reason": "critic output invalid", "errors": errs})
            continue
        # edge-level agreement
        c_edges = {_edge_key(e): e for e in cand.get("proposed_edges", [])}
        k_edges = {_edge_key(e): e for e in crit.get("proposed_edges", [])}
        agreed_edges = [k_edges[k] for k in c_edges.keys() & k_edges.keys()]
        disputed_edges = [c_edges[k] for k in c_edges.keys() - k_edges.keys()] + \
                         [k_edges[k] for k in k_edges.keys() - c_edges.keys()]
        # ability-level agreement
        c_ab = {_ability_key(a): a for a in cand.get("abilities", [])}
        k_ab = {_ability_key(a): a for a in crit.get("abilities", [])}
        agreed_ab = [k_ab[k] for k in c_ab.keys() & k_ab.keys()]
        disputed_ab = [c_ab[k] for k in c_ab.keys() - k_ab.keys()] + \
                      [k_ab[k] for k in k_ab.keys() - c_ab.keys()]

        accepted.append({"face_id": face_id, "abilities": agreed_ab, "proposed_edges": agreed_edges,
                         "schema_extension_requests": crit.get("schema_extension_requests", [])})
        if disputed_edges or disputed_ab:
            queued.append({"face_id": face_id, "reason": "extractor/critic disagreement",
                           "disputed_edges": disputed_edges, "disputed_abilities": disputed_ab})
    review = repo / "data" / "review"
    _write_dicts(review / "llm_accepted.jsonl", accepted)
    _write_dicts(review / "llm_queued.jsonl", queued)
    total_edges = sum(len(a["proposed_edges"]) for a in accepted)
    return {"faces": len(candidates), "accepted_faces": len(accepted),
            "accepted_edges": total_edges, "queued_items": len(queued)}
