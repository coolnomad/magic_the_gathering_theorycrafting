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

# (family, detector, prior-layer coverage). Detectors are broad CANDIDATE catchers — adjudication
# happens in later phases; false positives are expected. Expanded (review PHASE1 pt1 finding 2) to
# cover EVERY required effect family so the completeness ledger omits none.
_FAMILIES = [
    ("draw", r"\bdraws?\b[^.]*?\bcards?\b", "mechanism (second-draw gate)"),
    ("discard", r"\bdiscards?\b", "—"),
    ("sacrifice", r"\bsacrifices?\b", "sac_schema + completeness/lifecycle"),
    ("exile", r"\bexiles?\b", "—"),
    ("mill", r"\bmills?\b", "—"),
    ("return_move", r"\breturns?\b[^.]*?\b(?:hand|battlefield|graveyard|library)\b", "—"),
    ("tutor_search", r"\bsearch(?:es)?\b[^.]*?\blibrary\b", "audit_repair (tutor)"),
    ("token_create", r"\bcreate[s]?\b[^.]*?\btokens?\b", "audit_repair (token-enter)"),
    ("amass", r"\bamass\b", "—"),
    ("life", r"\b(?:gain|lose|pay)s?\b[^.]*?\blife\b", "—"),
    ("counterspell", r"\bcounter target\b", "—"),
    ("play_cast_permission",
     r"\bmay (?:play|cast)\b|\bplay (?:that|those|the exiled|an additional|this|it|them)\b|"
     r"\bcast (?:it|that|those|the exiled|them)\b|mana of any (?:type|color) can be spent", "—"),
    ("deal_damage", r"\bdeals?\b[^.]*?\bdamage\b", "effect_semantics (Phase 3 planned)"),
    ("destroy", r"\bdestroys?\b", "effect_semantics (CAN_DESTROY)"),
    ("tap_untap", r"\b(?:taps?|untaps?)\b", "—"),
    ("add_counter", r"\bput[s]?\b[^.]*?\bcounters?\b|\+1/\+1 counter|\bamass\b", "audit_repair (targeted-counter)"),
    ("remove_counter", r"\bremove[s]?\b[^.]*?\bcounters?\b", "—"),
    ("modify_pt", r"gets? [+\-][\dXx]+/[+\-][\dXx]+", "audit_repair (anthem/pump) + equip"),
    ("set_switch_pt",
     r"base power and toughness|power and toughness (?:are|is|becomes)|switch(?:es)? its power and toughness",
     "—"),
    ("grant_ability",
     r"\b(?:gains?|has|have)\b[^.]*?\b(?:flying|trample|vigilance|lifelink|deathtouch|menace|reach|haste|"
     r"hexproof|indestructible|first strike|double strike|ward|protection|prowess|defender|shroud)\b|"
     r"\bgains? \"", "equip (granted-when-attached)"),
    ("remove_ability", r"\bloses? (?:all abilities|flying|trample|vigilance|lifelink|deathtouch|menace|"
     r"reach|haste|hexproof|indestructible|first strike|double strike|ward|defender)\b", "—"),
    ("fight", r"\bfights?\b", "—"),
    ("prevent", r"\bprevents?\b", "—"),
    ("control_change", r"\b(?:gains?|exchange[s]?) control\b|\byou control (?:that|it|those) \w+", "—"),
    ("type_change",
     r"\bbecomes?\b[^.]*?\b(?:artifact|creature|enchantment|land)\b|\bin addition to its other types\b", "—"),
    ("scry_look_reveal", r"\b(?:scry|surveil)\b|\blook at the top\b|\breveal(?:s|ed)?\b", "—"),
    ("copy", r"\bcop(?:y|ies|ied)\b", "—"),
    ("cost_modification", r"\bcosts? \{|\bcosts?\b[^.]*?\b(?:less|more)\b|\bwithout paying\b", "infrastructure_casting"),
    ("additional_land", r"\badditional land\b", "—"),
    ("restriction",
     r"\bcan't (?:attack|block|be blocked|be the target|be countered|cast)\b|\battacks? (?:each combat )?if able\b|"
     r"\bmust (?:attack|be blocked)\b|\bdoesn't untap\b|\bdon't untap\b", "—"),
    ("delayed", r"\bat the beginning of the next\b|\buntil your next\b|\bwhen you do\b|"
     r"\bthen (?:exile|sacrifice|return) (?:it|that|them)\b|\bat the beginning of your next\b", "lifecycle (delayed sac)"),
    ("replacement", r"\bwould\b[^.]*?\binstead\b|\benters with\b|\bas [^.]{1,45} enters\b", "legend_rule (SBA)"),
]
_FAMILIES = [(n, re.compile(p, re.I), c) for n, p, c in _FAMILIES]

# heuristic reference counts from the instructions (starting points, NOT acceptance values)
_HEURISTIC = {"draw": 53, "discard": 25, "sacrifice": 34, "exile": 33, "mill": 6, "return_move": 13,
              "tutor_search": 10, "token_create": 46, "life": 22, "counterspell": 3,
              "play_cast_permission": 23}
_BULLET_CHAR = "•"


def _reminder_spans(text: str):
    return [(m.start(), m.end()) for m in re.finditer(r"\([^)]*\)", text)]


def _in_reminder(span, spans):
    return any(s <= span[0] and span[1] <= e for s, e in spans)


def _segment(text: str):
    """Split a face's Oracle text into semantic CLAUSES with stable indices and absolute spans:
    (ability_index, mode_index, sentence_index, start, end, clause_text). Ability = newline paragraph;
    a `Choose one` paragraph opens a modal block whose subsequent `•`-bulleted paragraphs get mode
    indices; sentences split on '.'. Offsets stay aligned (single-char '\\n'/bullet separators)."""
    out = []
    pos = 0
    mode_kind = None
    mode_counter = None
    for ai, para in enumerate(text.split("\n")):
        p_start = pos
        pos += len(para) + 1                               # +1 for the '\n'
        low = para.lower()
        if "choose one" in low:
            mode_kind = "choose_one_or_both" if "choose one or both" in low else "choose_one"
            mode_counter = -1
            cur_mode = None
        elif para.strip().startswith(_BULLET_CHAR):
            mode_counter = (mode_counter if mode_counter is not None else -1) + 1
            cur_mode = mode_counter
        else:
            mode_kind, mode_counter, cur_mode = None, None, None
        if not para.strip():
            continue
        si = 0
        for sm in re.finditer(r"[^.]*\.|[^.]+$", para):
            stext = sm.group(0)
            if not stext.strip():
                continue
            out.append({"ability_index": ai, "mode_kind": mode_kind, "mode_index": cur_mode,
                        "sentence_index": si, "start": p_start + sm.start(), "end": p_start + sm.end(),
                        "text": stext})
            si += 1
    return out


def census(repo: Path = REPO) -> dict:
    """Clause-level completeness ledger (review PHASE1 pt1 finding 1): one row per semantic CLAUSE,
    carrying stable clause_id, clause_span + per-family match_span(s), ability/mode/sentence indices,
    and ALL families detected in that clause. Every row stays `pending_structuring` until its phase
    adjudicates it. No card-name branching; reminder-text clauses/matches flagged, not dropped."""
    repo = Path(repo)
    faces = _load_dicts(repo / "data/normalized/faces.jsonl")
    rows = []
    for f in sorted(faces, key=lambda x: x["id"]):
        text = f.get("oracle_text") or ""
        rem = _reminder_spans(text)
        # group sentences into one CLAUSE per (ability, mode) so a modal branch / paragraph is
        # adjudicated ONCE, consistently (review pt1 finding 1); sentence detail kept per-match.
        groups = {}
        for c in _segment(text):
            key = (c["ability_index"], c["mode_index"])
            g = groups.setdefault(key, {"ability_index": c["ability_index"], "mode_kind": c["mode_kind"],
                                        "mode_index": c["mode_index"], "start": c["start"], "end": c["end"],
                                        "matches": []})
            g["start"] = min(g["start"], c["start"])
            g["end"] = max(g["end"], c["end"])
            for family, rx, _cov in _FAMILIES:
                for m in rx.finditer(c["text"]):
                    abspan = [c["start"] + m.start(), c["start"] + m.end()]
                    g["matches"].append({"family": family, "match_span": abspan, "snippet": m.group(0)[:60],
                                         "sentence_index": c["sentence_index"],
                                         "in_reminder": _in_reminder(abspan, rem)})
        for (ai, mi), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1)):
            if not g["matches"]:
                continue
            fams = sorted({m["family"] for m in g["matches"]})
            clause_id = f"{f['id']}#a{ai}" + (f".m{mi}" if mi is not None else "")
            rows.append({"clause_id": clause_id, "face_id": f["id"], "name": f["name"],
                         "ability_index": ai, "mode_kind": g["mode_kind"], "mode_index": mi,
                         "clause_span": [g["start"], g["end"]], "clause_text": text[g["start"]:g["end"]].strip()[:260],
                         "families": fams, "matches": sorted(g["matches"], key=lambda m: m["match_span"]),
                         "clause_in_reminder": _in_reminder([g["start"], g["end"]], rem),
                         "disposition": "pending_structuring"})
    out = repo / "data" / "graph_global" / "effect_census.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    # per-family summary: clauses with a NON-reminder match of the family (the meaningful count)
    summary = []
    for family, _rx, cov in _FAMILIES:
        fam_clauses = [r for r in rows if family in r["families"]]
        real_faces = {r["face_id"] for r in fam_clauses
                      if any(m["family"] == family and not m["in_reminder"] for m in r["matches"])}
        rem_only = {r["face_id"] for r in fam_clauses} - real_faces
        summary.append({"family": family, "faces_with_candidate": len(real_faces),
                        "reminder_only_faces": len(rem_only), "clauses": len(fam_clauses),
                        "heuristic_reference": _HEURISTIC.get(family), "prior_coverage": cov})
    _write_report(repo, summary, len({r["face_id"] for r in rows}), len(faces), len(rows))
    return {"faces": len(faces), "clauses_with_candidate": len(rows),
            "faces_with_any_candidate": len({r["face_id"] for r in rows}),
            "families": len(_FAMILIES), "multi_family_clauses": sum(1 for r in rows if len(r["families"]) > 1),
            "summary": summary}


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


def _write_report(repo, summary, faces_with_any, total_faces, total_clauses):
    L = ["# HOB effect-family census (Phase 1.1 — clause-level completeness ledger)", "",
         "Deterministic scan of **all Oracle text on all faces** (permanents included), grouped into "
         "semantic **clauses** (one row per clause, carrying `clause_span`, per-family `match_span`s, "
         "ability/mode/sentence indices, and every family detected in the clause). Detectors are broad "
         "CANDIDATE catchers; reminder-text hits are flagged, not removed. Every clause's disposition "
         "is `pending_structuring` until its phase adjudicates it. Heuristic reference counts are from "
         "the instructions and are NOT acceptance values.", "",
         f"- faces scanned: **{total_faces}**  · faces with ≥1 candidate: **{faces_with_any}**  · "
         f"candidate clauses: **{total_clauses}**", "",
         "| family | faces w/ candidate | reminder-only | clauses | heuristic ref | prior-layer coverage |",
         "|---|---:|---:|---:|---:|---|"]
    for s in summary:
        L.append(f"| `{s['family']}` | {s['faces_with_candidate']} | {s['reminder_only_faces']} | "
                 f"{s['clauses']} | {s['heuristic_reference'] if s['heuristic_reference'] is not None else '—'} "
                 f"| {s['prior_coverage']} |")
    L += ["", "All dispositions are `pending_structuring`; see "
          "`docs/hob_effect_semantics_repair_instructions.md` for the required dispositions and the "
          "per-family structuring plan. A clause may list several families (e.g. Warg Tactics mode-1 "
          "carries `add_counter` + `grant_ability`) so it is adjudicated once, consistently.", ""]
    (repo / "reports" / "effect_census.md").write_text("\n".join(L) + "\n", encoding="utf-8")
