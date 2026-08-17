"""Effect-semantics repair — Phase 1: a deterministic effect-family CENSUS over all HOB card faces.

Per `docs/hob_effect_semantics_repair_instructions.md`, the effect-semantics work is a systematic
additive layer over the frozen reference. This module is the foundation (sequence step 1): a
deterministic census of candidate effect clauses across ALL 210 faces (permanents included, not just
instants/sorceries), so every clause can later receive a disposition (structured & projected /
structured not projected / ignored / unresolved). No card-name/UUID branching — pure Oracle-text
detectors. Reads only frozen/normalized inputs; writes a census (machine + human readable).

Phase 1 assigns every candidate the disposition `pending_structuring`; later phases replace it as the
selector/participant/mode schema and per-family extractors land. Heuristic reference counts from the
instructions are recorded for comparison but are NOT acceptance values (reminder text / false
positives mean adjudicated totals differ).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .pipeline import REPO, _load_dicts

# (family, detector, note on prior-layer coverage). Detectors are deliberately broad CANDIDATE
# catchers — adjudication/structuring happens in later phases; false positives are expected and
# flagged (reminder text is marked, not removed).
_FAMILIES = [
    ("draw", re.compile(r"\bdraws?\b[^.]*?\bcards?\b", re.I), "mechanism layer (second-draw gate)"),
    ("discard", re.compile(r"\bdiscards?\b", re.I), "—"),
    ("sacrifice", re.compile(r"\bsacrifices?\b", re.I), "sac_schema + completeness/lifecycle"),
    ("exile", re.compile(r"\bexiles?\b", re.I), "—"),
    ("mill", re.compile(r"\bmills?\b[^.]*?\bcard|\bmills?\b", re.I), "—"),
    ("return_move", re.compile(r"\breturns?\b[^.]*?\b(hand|battlefield|graveyard|library)\b", re.I), "—"),
    ("tutor_search", re.compile(r"\bsearch(?:es)?\b[^.]*?\blibrary\b", re.I), "audit_repair (Seek the Heart tutor)"),
    ("token_create", re.compile(r"\bcreate[s]?\b[^.]*?\btokens?\b", re.I), "audit_repair (token-enter)"),
    ("amass", re.compile(r"\bamass\b", re.I), "—"),
    ("life", re.compile(r"\b(?:gain|lose|pay)s?\b[^.]*?\blife\b", re.I), "—"),
    ("counterspell", re.compile(r"\bcounter target\b", re.I), "—"),
    ("play_cast_permission", re.compile(r"\bmay (?:play|cast)\b", re.I), "—"),
    ("deal_damage", re.compile(r"\bdeals?\b[^.]*?\bdamage\b", re.I), "—"),
    ("destroy", re.compile(r"\bdestroys?\b", re.I), "—"),
    ("tap_untap", re.compile(r"\b(?:taps?|untaps?)\b", re.I), "—"),
    ("add_counter", re.compile(r"\bput[s]?\b[^.]*?\bcounters?\b|\+1/\+1 counter", re.I),
     "audit_repair (targeted-counter)"),
    ("modify_pt", re.compile(r"gets? [+\-]\d+/[+\-]\d+", re.I), "audit_repair (anthem/pump) + equip"),
    ("grant_ability", re.compile(
        r"\b(?:gains?|has|have)\b[^.]*?\b(?:flying|trample|vigilance|lifelink|deathtouch|menace|reach|"
        r"haste|hexproof|indestructible|first strike|double strike|ward|protection|prowess|defender)\b",
        re.I), "equip (granted-when-attached)"),
    ("fight", re.compile(r"\bfights?\b", re.I), "—"),
    ("prevent", re.compile(r"\bprevents?\b", re.I), "—"),
    ("control_change", re.compile(r"\bgains? control\b", re.I), "—"),
    ("type_change", re.compile(r"\bbecomes?\b[^.]*?\bin addition\b", re.I), "—"),
]

# heuristic reference counts from the instructions (starting points, NOT acceptance values)
_HEURISTIC = {"draw": 53, "discard": 25, "sacrifice": 34, "exile": 33, "mill": 6, "return_move": 13,
              "tutor_search": 10, "token_create": 46, "life": 22, "counterspell": 3,
              "play_cast_permission": 23}


def _reminder_spans(text: str):
    return [(m.start(), m.end()) for m in re.finditer(r"\([^)]*\)", text)]


def _in_reminder(span, spans):
    return any(s <= span[0] and span[1] <= e for s, e in spans)


def census(repo: Path = REPO) -> dict:
    repo = Path(repo)
    faces = _load_dicts(repo / "data/normalized/faces.jsonl")
    rows = []
    for f in sorted(faces, key=lambda x: x["id"]):
        text = f.get("oracle_text") or ""
        rem = _reminder_spans(text)
        for family, rx, _cov in _FAMILIES:
            for m in rx.finditer(text):
                span = [m.start(), m.end()]
                rows.append({"face_id": f["id"], "name": f["name"], "family": family,
                             "snippet": m.group(0)[:80], "oracle_span": span,
                             "in_reminder": _in_reminder(span, rem),
                             "disposition": "pending_structuring"})
    out = repo / "data" / "graph_global" / "effect_census.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    # per-family summary: faces with >=1 non-reminder candidate (the meaningful count)
    summary = []
    for family, _rx, cov in _FAMILIES:
        fam_rows = [r for r in rows if r["family"] == family]
        real = {r["face_id"] for r in fam_rows if not r["in_reminder"]}
        reminder_only = {r["face_id"] for r in fam_rows} - real
        summary.append({"family": family, "faces_with_candidate": len(real),
                        "reminder_only_faces": len(reminder_only), "total_clauses": len(fam_rows),
                        "heuristic_reference": _HEURISTIC.get(family), "prior_coverage": cov})
    _write_report(repo, summary, len({r["face_id"] for r in rows}), len(faces))
    return {"faces": len(faces), "candidate_clauses": len(rows),
            "faces_with_any_candidate": len({r["face_id"] for r in rows}),
            "families": len(_FAMILIES), "summary": summary}


# --------------------------------------------------------------------------- #
#  Phase 2 — structured effects. First family: targeted destruction (CAN_DESTROY) #
# --------------------------------------------------------------------------- #
from . import effect_schema as _sch  # noqa: E402

_BULLET = "•"
_PRONOUNS = {"it", "them", "that creature", "those", "that permanent", "it instead"}
_DESTROY_RE = re.compile(r"destroys?\s+(?:up to (\w+)\s+)?(other\s+|another\s+)?(?:target\s+)?(.+)", re.I)


def _modes(text: str):
    """Return (mode_kind, [branch dicts]). Non-modal cards have one unconditional branch."""
    low = text.lower()
    kind = "choose_one_or_both" if "choose one or both" in low else (
        "choose_one" if "choose one" in low else None)
    if not kind:
        return None, [{"index": 0, "text": text}]
    parts = text.split(_BULLET)
    return kind, [{"index": i, "text": p.strip()} for i, p in enumerate(parts[1:])]


def _blank_reminders(text: str) -> str:
    """Replace parenthetical reminder text with equal-length spaces (offsets preserved) so effect
    detectors never fire on reminders (e.g. Stone by Sunlight's '… that say "destroy" don't …')."""
    return re.sub(r"\([^)]*\)", lambda m: " " * len(m.group(0)), text)


def _destroy_effects(face: dict):
    """Structured DESTROY effects on a face (mode-aware, reminder-free), each with a resolved selector."""
    text = _blank_reminders(face.get("oracle_text") or "")
    kind, branches = _modes(text)
    out = []
    for br in branches:
        for sentence in br["text"].split("."):
            m = _DESTROY_RE.search(sentence)
            if not m:
                continue
            qty, excl, phrase = m.group(1), m.group(2), m.group(3).strip()
            if phrase.lower().strip() in _PRONOUNS or phrase.lower().startswith(("it ", "them ")):
                sel = _sch.selector(sentence[:m.start()])   # pronoun: resolve to the sentence's antecedent
                sel["targeted"] = False
            else:
                sel = _sch.selector(phrase)
            if not (sel["card_types"] or sel["subtypes"] or sel["generic_permanent"]):
                continue                                    # not a real object selector (e.g. "destroy it" w/ no antecedent)
            if qty:
                sel["quantity"] = f"up_to_{_sch._NUM.get(qty.lower(), qty.lower())}"
            if excl:
                sel["exclusions"] = sorted(set(sel["exclusions"]) | {excl.strip().lower()})
            span0 = text.find(m.group(0))
            out.append({"op": "DESTROY", "relation": "CAN_DESTROY", "selector": sel,
                        "mode_kind": kind, "mode_index": br["index"], "affects_each": False,
                        "clause": m.group(0).strip()[:120],
                        "oracle_span": [span0, span0 + len(m.group(0))] if span0 >= 0 else None})
    return out


def build_effects(repo: Path = REPO) -> dict:
    """Extract + project the destruction family (Phase 2). Structured facts → effect_destroy.jsonl;
    deterministic card-pair projection → card_pair_projection_effect.jsonl (origin effect_semantics)."""
    repo = Path(repo)
    faces = _load_dicts(repo / "data/normalized/faces.jsonl")
    tokens = _load_dicts(repo / "data/normalized/tokens.jsonl")
    by_card = {}
    for f in faces:
        by_card.setdefault(f["card_id"], []).append(f)
    cards = sorted(by_card)

    structured, pairs = [], []
    seen = set()
    for f in sorted(faces, key=lambda x: x["id"]):
        for eff in _destroy_effects(f):
            sel = eff["selector"]
            prov = {"face_id": f["id"], "name": f["name"], "oracle_span": eff["oracle_span"],
                    "clause": eff["clause"], "rule": "effect_semantics.destroy", "layer": "effect_semantics",
                    "mode_kind": eff["mode_kind"], "mode_index": eff["mode_index"]}
            elig_tokens = sorted(t["id"] for t in tokens if _sch.matches_token(sel, t))
            structured.append({**eff, "face_id": f["id"], "card": f["card_id"], "name": f["name"],
                               "eligible_token_specs": elig_tokens, "provenance": prov})
            src = f["card_id"]
            for tgt in cards:
                if any(_sch.matches_card(sel, cf) for cf in by_card[tgt]):
                    key = (src, tgt, "CAN_DESTROY")
                    if key in seen:
                        continue
                    seen.add(key)
                    pairs.append({"source_card": src, "target_card": tgt, "relation": "CAN_DESTROY",
                                  "self_pair": src == tgt, "generic": True, "origin": "effect_semantics",
                                  "family": "destroy", "provenance": [prov]})
    G = repo / "data" / "graph_global"
    _writej(G / "effect_destroy.jsonl", sorted(structured, key=lambda r: (r["face_id"], r["mode_index"])))
    _writej(G / "card_pair_projection_effect.jsonl",
            sorted(pairs, key=lambda p: (p["source_card"], p["target_card"], p["relation"])))
    _effects_report(repo, structured, pairs)
    return {"faces_with_destroy": len({s["face_id"] for s in structured}),
            "destroy_effects": len(structured), "destroy_pairs": len(pairs)}


def _effects_report(repo, structured, pairs):
    L = ["# Effect-semantics — structured effects (Phase 2)", "",
         "Additive `effect_semantics` layer over the frozen reference. Family delivered this phase: "
         "**targeted destruction** (`CAN_DESTROY`). Structured facts carry a resolved selector, mode, "
         "and Oracle-span provenance; deterministic projection fans each targeted destroy to every "
         "eligible card (and records eligible token specs). Frozen core untouched.", "",
         f"- destroy effects: **{len(structured)}** on {len({s['face_id'] for s in structured})} faces  "
         f"· CAN_DESTROY pairs: **{len(pairs)}**", "",
         "| card | mode | selector | eligible cards | token specs |", "|---|---|---|---:|---:|"]
    npairs = {}
    for p in pairs:
        npairs[p["source_card"]] = npairs.get(p["source_card"], 0) + 1
    for s in sorted(structured, key=lambda r: r["name"]):
        sel = s["selector"]
        desc = "/".join(sel["card_types"]) or (",".join(sel["subtypes"]) or ("permanent" if sel["generic_permanent"] else "?"))
        for k, v in sel["predicates"].items():
            desc += f" [{k}{'' if v is True else '≥'+str(v)}]"
        mode = f"{s['mode_kind']}#{s['mode_index']}" if s["mode_kind"] else "—"
        L.append(f"| {s['name']} | {mode} | {desc} | {npairs.get(s['card'], 0)} | {len(s['eligible_token_specs'])} |")
    (repo / "reports" / "effect_semantics.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _writej(path: Path, rows: list):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _write_report(repo, summary, faces_with_any, total_faces):
    L = ["# HOB effect-family census (Phase 1 — deterministic candidate detection)", "",
         "Deterministic scan of **all Oracle text on all faces** (permanents included). Each family's "
         "detector is a broad CANDIDATE catcher; reminder-text hits are flagged (`reminder_only`), not "
         "removed. Every candidate's disposition is `pending_structuring` — later phases replace it "
         "with structured / not-projected / ignored / unresolved. Heuristic reference counts are from "
         "the instructions and are NOT acceptance values.", "",
         f"- faces scanned: **{total_faces}**  · faces with ≥1 candidate: **{faces_with_any}**", "",
         "| family | faces w/ candidate | reminder-only | clauses | heuristic ref | prior-layer coverage |",
         "|---|---:|---:|---:|---:|---|"]
    for s in summary:
        L.append(f"| `{s['family']}` | {s['faces_with_candidate']} | {s['reminder_only_faces']} | "
                 f"{s['total_clauses']} | {s['heuristic_reference'] if s['heuristic_reference'] is not None else '—'} "
                 f"| {s['prior_coverage']} |")
    L += ["", "All dispositions are `pending_structuring` at Phase 1; see "
          "`docs/hob_effect_semantics_repair_instructions.md` for the required dispositions and the "
          "per-family structuring plan.", ""]
    (repo / "reports" / "effect_census.md").write_text("\n".join(L) + "\n", encoding="utf-8")
