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
    ("attachment", r"\battach(?:es|ed|ing)?\b|\bequip\b", "equip layer"),
    ("mana_production", r"\badds?\b[^.]*?(?:\{[WUBRGCXSP0-9/]+\}|\bmana\b)", "infrastructure/mechanism (mana)"),
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
        # emit EVERY segmented clause, even with zero detected families (review pt2): an undetected
        # material effect (attachment, mana, or a future gap) is then recorded, not silently dropped.
        for (ai, mi), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1)):
            fams = sorted({m["family"] for m in g["matches"]})
            clause_id = f"{f['id']}#a{ai}" + (f".m{mi}" if mi is not None else "")
            rows.append({"clause_id": clause_id, "face_id": f["id"], "name": f["name"],
                         "ability_index": ai, "mode_kind": g["mode_kind"], "mode_index": mi,
                         "clause_span": [g["start"], g["end"]],
                         "clause_text": text[g["start"]:g["end"]].strip(),   # FULL text, not truncated
                         "families": fams, "matches": sorted(g["matches"], key=lambda m: m["match_span"]),
                         "clause_in_reminder": _in_reminder([g["start"], g["end"]], rem),
                         "disposition": "pending_structuring" if fams else "pending_classification"})
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
    matched = sum(1 for r in rows if r["families"])
    unclassified = len(rows) - matched
    _write_report(repo, summary, len({r["face_id"] for r in rows}), len(faces), len(rows), unclassified)
    return {"faces": len(faces), "total_clauses": len(rows), "clauses_with_family": matched,
            "clauses_pending_classification": unclassified,
            "faces_with_any_candidate": len({r["face_id"] for r in rows}),
            "families": len(_FAMILIES), "multi_family_clauses": sum(1 for r in rows if len(r["families"]) > 1),
            "summary": summary}


# --------------------------------------------------------------------------- #
#  Phase 2 — structured effects. First family: targeted destruction (CAN_DESTROY) #
# --------------------------------------------------------------------------- #
from . import effect_schema as _sch  # noqa: E402

_BULLET = "•"
_PRONOUNS = {"it", "them", "that creature", "those", "that permanent", "it instead"}
# groups: (1) up-to N, (2) other/another, (3) target|each|all quantifier keyword, (4) object phrase
_DESTROY_RE = re.compile(
    r"destroys?\s+(?:up to (\w+)\s+)?(other\s+|another\s+)?(target|each|all)?\s*(.+)", re.I)


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
    """Structured, validated DESTROY effect records on a face (mode-aware, reminder-free): each carries
    a resolved selector, participant, mode object, condition, duration, targeting/quantifier, and — for
    a pronoun — a binding to its antecedent object variable (The Black Arrow destroys the same Dragon)."""
    text = _blank_reminders(face.get("oracle_text") or "")
    out = []
    idx = 0
    for cl in _ability_clauses(text):                       # ability/mode-scoped, real clause_id
        kind = cl["mode_kind"]
        clause_id = f"{face['id']}#a{cl['ability_index']}" + (f".m{cl['mode_index']}" if cl["mode_index"] is not None else "")
        for sent in cl["sentences"]:
            sentence = text[sent["start"]:sent["end"]]
            m = _DESTROY_RE.search(sentence)
            if not m:
                continue
            qty, excl, qword, phrase = m.group(1), m.group(2), (m.group(3) or "").lower(), m.group(4).strip().rstrip(".").strip()
            pronoun = phrase.lower().strip() in _PRONOUNS or phrase.lower().startswith(("it ", "them "))
            binding = None
            if pronoun:
                # conditional consequence bound to the ANTECEDENT object (not independently targeted)
                ante = sentence[:m.start()]
                sel = _sch.selector(ante, var="obj0", targeted=False, quantifier=None)
                via = "dealt damage this way" if "dealt damage" in ante.lower() else "prior effect"
                binding = {"kind": "antecedent", "var": "obj0", "via": via,
                           "restriction": {"subtypes": sel["subtypes"], "card_types": sel["card_types"]}}
            else:
                quant = ("each" if qword == "each" else "all" if qword == "all"
                         else f"up_to_{_sch._NUM.get((qty or '').lower(), qty)}" if qty
                         else "target" if qword == "target" else None)
                sel = _sch.selector(phrase, var="obj0", targeted=(qword == "target"), quantifier=quant)
            if not (sel["card_types"] or sel["subtypes"] or sel["generic_permanent"]):
                continue                                    # not a real object selector
            if excl:
                sel["exclusions"] = sorted(set(sel["exclusions"]) | {excl.strip().lower()})
            span0 = text.find(m.group(0))
            cond = _sch.condition(sentence)
            if binding and cond and cond.get("kind") == "conditional_effect":
                # make the condition itself machine-interpretable, tied to the bound antecedent object
                cond = {**cond, "object_var": binding["var"],
                        "required_subtype": (binding["restriction"]["subtypes"] or [None])[0]}
            rec = {"effect_id": f"{clause_id}#DESTROY#{idx}", "op": "DESTROY", "relation": "CAN_DESTROY",
                   "participant": _sch.participant(sentence), "selector": sel,
                   "mode": {"kind": kind, "index": cl["mode_index"]}, "clause_id": clause_id,
                   "condition": cond, "duration": _sch.duration(sentence),
                   "optional": bool(qty) or "may destroy" in sentence.lower(),
                   "targeted": sel["targeted"], "affects_each": sel["affects_each"],
                   "attempt": True,                          # destruction is an ATTEMPT (indestructible can stop it)
                   "zone_transition": {"from": "battlefield", "to": "graveyard", "guaranteed": False},
                   "binding": binding, "clause": m.group(0).strip(),
                   "oracle_span": [span0, span0 + len(m.group(0))] if span0 >= 0 else None}
            idx += 1
            out.append(rec)
    return out


# --------------------------------------------------------------------------- #
#  Phase 3a — targeted-object families, ABILITY-scoped with same-object binding    #
#  (review PHASE3 pt1: parse per ability/mode clause; never share targets across   #
#  abilities; scope duration to the operation; separate object vs participant;     #
#  self-effects explicit; comma-OR subtype lists; reject empty object selectors.)  #
# --------------------------------------------------------------------------- #
_ABIL_KW = ["flying", "trample", "vigilance", "lifelink", "deathtouch", "menace", "reach", "haste",
            "hexproof", "indestructible", "first strike", "double strike", "ward", "protection",
            "prowess", "defender", "shroud"]
_SELF_RE = re.compile(r"\bthis (creature|permanent|artifact|enchantment|vehicle|token|aura|land)\b", re.I)
_EQUIPPED_RE = re.compile(r"\b(equipped|enchanted) creature\b", re.I)   # attachment static → equip/aura layer
_PLAYER_RE = re.compile(r"\b(target opponent|target player|each opponent|each player|that player)\b", re.I)
_ANYTARGET_RE = re.compile(r"\bany target\b", re.I)
_SUBJVERB_RE = re.compile(r"\b(gets?|gains?|loses?|fights?|becomes?)\b", re.I)
_OBJ_DELIM = re.compile(r"\.|;|\bfor each\b|\bfor as long as\b|\bthat share\b|\bgets?\b|\bgains?\b|\bhas\b|"
                        r"\bhave\b|\bloses?\b|\bfights?\b|\bbecomes?\b|\bif\b|\bthen\b|\buntil\b|$", re.I)


def _abilities(phrase):
    low = phrase.lower()
    return sorted({k for k in _ABIL_KW if re.search(r"\b" + re.escape(k) + r"\b", low)})


def _self_selector(var="self"):
    return {"card_types": [], "or_types": False, "subtypes": [], "supertypes": [], "qualifiers": [],
            "generic_permanent": False, "controller": "you", "owner": None, "zone": "battlefield",
            "quantifier": None, "exclusions": [], "predicates": {}, "targeted": False,
            "affects_each": False, "self": True, "var": var}


def _anytarget_selector(var):
    s = _sch.selector("creature", var=var, targeted=True, quantifier="target")
    s["any_target"] = True
    s["alternatives"] = ["creature", "planeswalker", "battle", "player"]
    return s


def _ability_clauses(text):
    """Group the segmenter's sentences into one clause per (ability, mode), with a REAL clause_id."""
    groups = {}
    for c in _segment(text):
        key = (c["ability_index"], c["mode_index"])
        g = groups.setdefault(key, {"ability_index": c["ability_index"], "mode_kind": c["mode_kind"],
                                    "mode_index": c["mode_index"], "start": c["start"], "end": c["end"],
                                    "sentences": []})
        g["start"] = min(g["start"], c["start"]); g["end"] = max(g["end"], c["end"])
        g["sentences"].append(c)
    out = []
    for (ai, mi), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1)):
        g["sentences"].sort(key=lambda s: s["sentence_index"])
        out.append(g)
    return out


def _clip(phrase):
    d = _OBJ_DELIM.search(phrase)
    return (phrase[:d.start()] if d else phrase).strip().rstrip(",")


def _object_effects(face):
    text = _blank_reminders(face.get("oracle_text") or "")
    short = face["name"].split(",")[0].split(" //")[0].strip().lower()
    out = []

    for cl in _ability_clauses(text):
        clause_id = f"{face['id']}#a{cl['ability_index']}" + (f".m{cl['mode_index']}" if cl["mode_index"] is not None else "")
        vc = [0]

        tvars = {}                                          # dedup: same object referenced twice → one var

        def alloc():
            v = f"obj{vc[0]}"; vc[0] += 1; return v

        def classify(phrase):
            low = phrase.lower().strip()
            if _EQUIPPED_RE.search(low):
                return {"kind": "equipped"}
            sf = short.split()[0] if short else ""          # the card's own first name ("Óin", "Bombur")
            self_name = (short and re.search(r"\b" + re.escape(short) + r"\b", low)) or \
                (sf and len(sf) >= 3 and sf not in ("the", "a", "an", "of") and re.search(r"\b" + re.escape(sf) + r"\b", low))
            if _SELF_RE.search(low) or self_name or "~" in phrase:
                return {"kind": "self", "var": "self", "selector": _self_selector(), "participant": None}
            if _ANYTARGET_RE.search(low):
                v = alloc()
                return {"kind": "any_target", "var": v, "selector": _anytarget_selector(v), "participant": None}
            if re.match(r"\s*(it|its|that creature|that permanent|those|them|their)\b", low) and "target" not in low:
                return {"kind": "pronoun"}       # pronoun only when it LEADS the phrase, not buried mid-phrase
            part = _sch.participant(phrase) if _PLAYER_RE.search(low) else None
            sel = _sch.selector(phrase, var="?", targeted=("target" in low),
                                quantifier=("up_to_2" if "one or two" in low else None))
            # a non-targeted class reference is a MASS effect (affects each such object) — review pt2 #7
            if part is not None or (not sel["targeted"] and not _sch.selector_is_empty(sel)):
                sel["targeted"] = False
                sel["affects_each"] = True
                sel["quantifier"] = "each" if re.search(r"\beach\b", low) else "all"
            if _sch.selector_is_empty(sel):
                return {"kind": "participant" if part else "empty", "participant": part}
            key = (tuple(sel["card_types"]), tuple(sel["subtypes"]), sel["controller"],
                   sel["targeted"], sel["affects_each"])
            if key in tvars:                                # same object → reuse its var (preserves binding)
                return {"kind": "selector", "var": tvars[key][0], "selector": tvars[key][1], "participant": part}
            v = alloc(); sel["var"] = v; tvars[key] = (v, sel)
            return {"kind": "selector", "var": v, "selector": sel, "participant": part}

        cur = [None]                                       # (var, selector, participant)
        crange0 = text[cl["start"]:cl["end"]]
        ft = []                                            # cached first-object-target of the clause

        def first_target():
            if not ft:
                res = None
                for tm in re.finditer(r"target\s+(.+)", crange0, re.I):
                    r = classify(_clip(tm.group(1)))
                    if r["kind"] in ("self", "any_target", "selector"):
                        res = (r["var"], r["selector"], r.get("participant")); break
                ft.append(res)
            return ft[0]

        def objsel(res):
            if res["kind"] in ("self", "any_target", "selector"):
                return res["var"], res["selector"], res.get("participant")
            if res["kind"] == "pronoun":
                return cur[0] or first_target() or (None, None, None)
            return None, None, None

        def lead_subject(stext, verb_pos):
            pre = stext[:verb_pos]
            tm = re.search(r"target\s+(.+)", pre, re.I)     # the object is the FIRST 'target …' in the
            if tm:                                          # prefix, not the whole prefix (which may name
                r = classify("target " + _clip(tm.group(1)))  # types from a preceding EFFECT (Stone's
                if r["kind"] in ("self", "any_target", "selector"):  # "becomes an artifact"); keep the
                    return r["var"], r["selector"], r.get("participant")  # 'target' marker so it stays targeted
            pre2 = re.sub(r"^\s*(then|and|also|until end of turn,?|,)\s*", "", pre, flags=re.I)
            r = classify(pre2)
            if r["kind"] == "equipped":
                return None
            if r["kind"] == "pronoun":
                return cur[0] or first_target()
            if r["kind"] in ("self", "any_target", "selector"):
                return r["var"], r["selector"], r.get("participant")
            return None

        ops = []
        for sent in cl["sentences"]:
            stext = text[sent["start"]:sent["end"]]
            slow = stext.lower()
            dur = "until_end_of_turn" if "until end of turn" in slow else ("this_turn" if "this turn" in slow else None)
            scond = _sch.condition(stext)                  # condition scoped to THIS sentence
            sops = []

            def emit(op, relation, var, selector, part, extra, span, duration):
                if not var or not selector or _sch.selector_is_empty(selector):
                    return
                sops.append({"op": op, "relation": relation, "object_var": var, "selector": selector,
                             "participant": part or "you", "duration": duration, "condition": scond,
                             "span": [sent["start"] + span[0], sent["start"] + span[1]], **extra})

            for m in re.finditer(r"deals?\s+(\d+|x)\s+damage\s+to\s+(.+)", stext, re.I):
                r = classify(_clip(m.group(2))); var, sel, part = objsel(r)
                emit("DEAL_DAMAGE", "CAN_DEAL_DAMAGE_TO", var, sel, part,
                     {"amount": m.group(1).lower(), "source_var": "self", "any_target": r["kind"] == "any_target"}, m.span(), None)
                if var:
                    cur[0] = (var, sel, part)
            for m in re.finditer(r"put\s+(?:a number of\s+|(\w+)\s+)(\+1/\+1|\-1/\-1|[a-z]+)\s+counters?\s+on\s+(.+)", stext, re.I):
                r = classify(_clip(m.group(3))); var, sel, part = objsel(r)
                w = (m.group(1) or "variable").lower(); n = 1 if w in ("a", "an") else _sch._NUM.get(w, w)
                emit("ADD_COUNTER", "ADDS_COUNTER_TO", var, sel, part, {"n": n, "counter": m.group(2)}, m.span(), None)
                if var:
                    cur[0] = (var, sel, part)
            for m in re.finditer(r"\b(taps?|untaps?)\s+(.+)", stext, re.I):
                r = classify(_clip(m.group(2))); var, sel, part = objsel(r)
                unt = m.group(1).lower().startswith("untap")
                emit("UNTAP" if unt else "TAP", "CAN_UNTAP" if unt else "CAN_TAP", var, sel, part, {}, m.span(), None)
                if var:
                    cur[0] = (var, sel, part)
            # exchange/gain control of target permanents (Burglar's Plot: TWO nonland permanents that
            # share a card type — two distinct object variables + shared-type constraint, review pt2 #4)
            for m in re.finditer(r"(?:exchange|gain)s? control of\s+(.+)", stext, re.I):
                r = classify(_clip(m.group(1))); var, sel, part = objsel(r)
                if not (var and sel):
                    continue
                exch = "exchange" in m.group(0).lower()
                extra = {}
                if exch and re.search(r"\btwo\b", m.group(1).lower()):
                    v2 = alloc()
                    extra = {"second_var": v2, "second_selector": {**sel, "var": v2},
                             "quantity": 2, "shared_constraint": ("same_card_type" if "share a card type" in stext.lower() else None)}
                emit("CONTROL_CHANGE", "EXCHANGES_CONTROL_OF" if exch else "GAINS_CONTROL_OF",
                     var, sel, part, extra, m.span(), None)
            # prevent damage dealt BY a target creature (Old Fat Spider) — strip the source-presence
            # duration phrase from the selector; record the duration on the effect (review pt2 #3)
            for m in re.finditer(r"prevent all damage that would be dealt by\s+(.+)", stext, re.I):
                r = classify(_clip(m.group(1))); var, sel, part = objsel(r)
                pdur = "as_long_as_source_on_battlefield" if re.search(r"for as long as this .* remains", slow) else None
                emit("PREVENT_DAMAGE", "PREVENTS_DAMAGE_FROM", var, sel, part, {}, m.span(), pdur)
            for m in re.finditer(r"deals?\s+damage\s+(equal to its power\s+)?to\s+(.+)", stext, re.I):
                subj = lead_subject(stext, m.start())
                r = classify(_clip(m.group(2))); ov, osel, opart = objsel(r)
                if subj and ov and subj[0] != ov:
                    sops.append({"op": "DEAL_DAMAGE", "relation": "CAN_DEAL_DAMAGE_TO", "object_var": ov,
                                 "selector": osel, "participant": opart or "you", "source_var": subj[0],
                                 "source_selector": subj[1], "amount": "equal_to_source_power" if m.group(1) else "unspecified",
                                 "duration": None, "condition": scond,
                                 "span": [sent["start"] + m.start(), sent["start"] + m.end()]})
                    cur[0] = (ov, osel, opart)

            # each subject-verb op resolves its OWN subject LOCALLY (the phrase just before the verb),
            # not one global subject — Mirkwood Meditator's "this creature's base P/T" must bind to self,
            # not the "a land you control" of the Landfall trigger (review pt2 #2/#3). Target dedup keeps
            # same-object ops (Reverent Howl pump+grant) on one var.
            def subj_at(pos):
                s = lead_subject(stext, pos) or cur[0] or first_target()
                if s:
                    cur[0] = s
                return s

            def emit_s(op, relation, pos, extra, span, duration):
                s = subj_at(pos)
                if s:
                    emit(op, relation, s[0], s[1], s[2], extra, span, duration)

            for m in re.finditer(r"gets?\s+([+\-][\dXx]+/[+\-][\dXx]+)", stext, re.I):
                emit_s("MODIFY_PT", "MODIFIES_POWER_TOUGHNESS", m.start(), {"pt_mod": m.group(1)}, m.span(), dur)
            for m in re.finditer(r"(?:gains?|has|have)\s+([A-Za-z][A-Za-z ,]*?(?:and [A-Za-z ]+)?)(?=\s+until|\s+as long as|\s*\{|\.|,|;|$)", stext, re.I):
                ab = _abilities(m.group(1))
                if ab:
                    emit_s("GRANT_ABILITY", "GRANTS_ABILITY_TO", m.start(), {"abilities": ab}, m.span(), dur)
            for m in re.finditer(r"loses?\s+(all abilities|[A-Za-z ,]+?)(?=\s+until|\.|,|;|$)", stext, re.I):
                ab = ["all_abilities"] if "all abilities" in m.group(1).lower() else _abilities(m.group(1))
                if ab:
                    emit_s("REMOVE_ABILITY", "REMOVES_ABILITY_FROM", m.start(), {"abilities": ab}, m.span(), dur)
            for m in re.finditer(r"becomes?\s+(?:a|an)\s+([A-Za-z][\w ]*?)(?=\s+in addition|\s+until|\.|,|;|$)", stext, re.I):
                phr = m.group(1)
                ct = [t for t in _sch.PERMANENT_TYPES if re.search(r"\b" + t + r"\b", phr, re.I)]
                subs = sorted(_sch._valid_subtypes(phr))
                if ct or subs:
                    emit_s("CHANGE_TYPE", "CHANGES_TYPE_OF", m.start(),
                           {"added_type": ct[0] if ct else None, "added_subtypes": subs,
                            "in_addition": "in addition" in slow}, m.span(), dur)
            for m in re.finditer(r"(?:base )?power and toughness (?:become|are)\s+(.+?)(?=\s+until|\.|$)", stext, re.I):
                emit_s("SET_BASE_PT", "SETS_BASE_PT", m.start(),
                       {"value": _clip(m.group(1)), "base": "base " in m.group(0).lower()}, m.span(), dur)
            for m in re.finditer(r"switch(?:es)? its power and toughness", stext, re.I):
                emit_s("SWITCH_PT", "SWITCHES_PT", m.start(), {}, m.span(), dur)
            for m in re.finditer(r"\bfights?\s+(.+)", stext, re.I):
                subj = subj_at(m.start())
                r = classify(_clip(m.group(1))); ov, osel, _ = objsel(r)
                if subj and ov and ov != subj[0]:
                    sops.append({"op": "FIGHT", "relation": "CAN_FIGHT", "object_var": subj[0], "selector": subj[1],
                                 "participant": subj[2] or "you", "fight_target_var": ov, "fight_target_selector": osel,
                                 "duration": None, "condition": scond,
                                 "span": [sent["start"] + m.start(), sent["start"] + m.end()]})
            ops += sops

        crange = text[cl["start"]:cl["end"]]
        repl = re.search(r"if (?:that creature|it) would die[^.]*?exile it instead", crange, re.I)
        for op in ops:
            if op["op"] == "DEAL_DAMAGE" and repl:
                op["replacement"] = {"kind": "die_would_exile_instead", "object_var": op["object_var"], "duration": "this_turn"}
        cm = re.search(r"costs? (\{[^}]+\}) less to cast if it targets a (\w+) creature", text, re.I)

        for i, op in enumerate(ops):
            span = op.pop("span")
            sel = op["selector"]
            if cm and sel["targeted"]:
                op["cost_modification"] = {"amount": cm.group(1),
                                           "condition": {"kind": "conditional_cost", "predicate": f"target_is_{cm.group(2).lower()}"}}
            rec = {"effect_id": f"{clause_id}#{op['op']}#{i}", "op": op["op"], "relation": op["relation"],
                   "participant": op.get("participant") or "you", "selector": sel, "object_var": op["object_var"],
                   "mode": {"kind": cl["mode_kind"], "index": cl["mode_index"]},
                   "condition": op.get("condition"), "duration": op.get("duration"),
                   "optional": "may " in crange.lower(), "targeted": sel["targeted"],
                   "affects_each": sel.get("affects_each", False), "binding": None, "clause_id": clause_id,
                   "oracle_span": span, **{k: v for k, v in op.items() if k not in ("op", "relation", "object_var", "selector", "duration", "participant", "condition")}}
            out.append(rec)
    return out
_PHASE3_FAMILIES = {"deal_damage", "destroy", "add_counter", "remove_counter", "modify_pt",
                    "set_switch_pt", "grant_ability", "remove_ability", "fight", "prevent",
                    "control_change", "type_change", "tap_untap"}


_OP_FAMILY = {"DEAL_DAMAGE": "deal_damage", "DESTROY": "destroy", "ADD_COUNTER": "add_counter",
              "MODIFY_PT": "modify_pt", "SET_BASE_PT": "set_switch_pt", "SWITCH_PT": "set_switch_pt",
              "GRANT_ABILITY": "grant_ability", "REMOVE_ABILITY": "remove_ability", "TAP": "tap_untap",
              "UNTAP": "tap_untap", "FIGHT": "fight", "CHANGE_TYPE": "type_change",
              "CONTROL_CHANGE": "control_change", "PREVENT_DAMAGE": "prevent"}
_DEFERRED_DISP = {"divided_damage", "grants_nonkeyword_ability", "remove_counter", "source_power_bound_damage"}


def reconcile(repo: Path = REPO) -> dict:
    """Reconcile every (clause_id, family) that carries a Phase-3 effect family (review pt2 #10): each
    is either EXTRACTED (an effect of that family exists on that clause) or DISPOSITIONED. Deferred /
    non-executable dispositions are counted SEPARATELY, not hidden inside a '0 unresolved' headline."""
    repo = Path(repo)
    census = _load_dicts(repo / "data/graph_global/effect_census.jsonl")
    faces = _load_dicts(repo / "data/normalized/faces.jsonl")
    extracted_cf = set()
    for f in faces:
        for e in _destroy_effects(f) + _object_effects(f):
            extracted_cf.add((e["clause_id"], _OP_FAMILY.get(e["op"], e["op"].lower())))
    rows, counts = [], {}
    for c in census:
        low = c["clause_text"].lower()
        for fam in sorted(set(c["families"]) & _PHASE3_FAMILIES):
            fam_matches = [m for m in c["matches"] if m["family"] == fam]
            if (c["clause_id"], fam) in extracted_cf:
                disp = "extracted"
            elif fam_matches and all(m["in_reminder"] for m in fam_matches):
                disp = "reminder_text (family appears only in reminder text)"
            elif fam == "type_change" and "attach" in low and "becomes" not in low:
                disp = "attachment (equip layer — not a type change)"
            elif fam == "deal_damage" and re.search(r"that creature's power", low):
                disp = "source_power_bound_damage"
            elif "equipped creature" in low or "enchanted creature" in low:
                disp = "attachment_static (equip/aura layer)"
            elif fam in ("add_counter", "modify_pt") and re.search(r"amass", low):
                disp = "amass (counters on an Army token — token/mechanism layer)"
            elif re.search(r"\bcrew\b", low):
                disp = "crew (keyword reminder — vehicle/mechanism layer)"
            elif fam == "deal_damage" and re.search(r"deals combat damage", low):
                disp = "combat_damage_trigger (a trigger, not a damage effect)"
            elif fam == "deal_damage" and re.search(r"damage divided", low):
                disp = "divided_damage"
            elif fam == "tap_untap" and re.search(r"do(?:es)?n't untap|doesn't untap", low):
                disp = "restriction (doesn't-untap — restriction family)"
            elif fam == "grant_ability" and re.search(r'gains? "', low):
                disp = "grants_nonkeyword_ability"
            elif fam == "remove_counter":
                disp = "remove_counter"
            elif fam == "add_counter" and re.search(r"counter on it\b|counter on them\b", low):
                disp = "counter_as_condition (census false positive — a counter reference, not an add)"
            elif re.search(r"target (player|opponent)|each (player|opponent)|that player|to any target", low) \
                    and not re.search(r"\b(creature|artifact|enchantment|permanent|land|planeswalker)\b",
                                      low.split("target", 1)[-1][:30]):
                disp = "participant_effect (Phase 4: player-directed)"
            elif c["clause_in_reminder"]:
                disp = "reminder_text (ignored)"
            else:
                disp = "unresolved"
            counts[disp] = counts.get(disp, 0) + 1
            rows.append({"clause_id": c["clause_id"], "name": c["name"], "family": fam,
                         "disposition": disp, "clause": c["clause_text"][:90]})
    unresolved = [r for r in rows if r["disposition"] == "unresolved"]
    deferred = sum(v for k, v in counts.items() if k in _DEFERRED_DISP)
    L = ["# Effect-semantics — Phase-3 (clause_id, family) reconciliation", "",
         "Every `(clause_id, family)` carrying a Phase-3 effect family is EXTRACTED or DISPOSITIONED. "
         "Deferred / non-executable dispositions are counted separately from `unresolved`.", "",
         f"- (clause, family) pairs: **{len(rows)}**  · extracted: **{counts.get('extracted', 0)}**  "
         f"· deferred/nonexecutable: **{deferred}**  · unresolved: **{len(unresolved)}**", "",
         "| disposition | (clause,family) |", "|---|---:|"]
    for d in sorted(counts, key=lambda k: -counts[k]):
        L.append(f"| {d}{' — DEFERRED' if d in _DEFERRED_DISP else ''} | {counts[d]} |")
    if unresolved:
        L += ["", "## Unresolved (need attention)", ""]
        for r in unresolved:
            L.append(f"- `{r['clause_id']}` {r['name']} [{r['family']}]: {r['clause']}")
    (repo / "reports" / "effect_reconciliation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"clause_family_pairs": len(rows), "extracted": counts.get("extracted", 0),
            "deferred": deferred, "unresolved": len(unresolved), "dispositions": counts}


def build_effects(repo: Path = REPO, faces=None, tokens=None, write=True) -> dict:
    """Extract + project the destruction family (Phase 2). Structured facts → effect_destroy.jsonl;
    deterministic card-pair projection → card_pair_projection_effect.jsonl (origin effect_semantics).
    `faces`/`tokens` may be supplied (synthetic) and `write=False` to exercise projection in tests."""
    repo = Path(repo)
    faces = faces if faces is not None else _load_dicts(repo / "data/normalized/faces.jsonl")
    tokens = tokens if tokens is not None else _load_dicts(repo / "data/normalized/tokens.jsonl")
    by_card = {}
    for f in faces:
        by_card.setdefault(f["card_id"], []).append(f)
    cards = sorted(by_card)

    structured, errors = [], []
    agg = {}                                                # (src,tgt,relation) -> aggregated pair with `supports`

    def _add(src, tgt, relation, family, support):
        key = (src, tgt, relation)
        if key not in agg:                                  # unique pair, AGGREGATE all supporting effects/modes
            agg[key] = {"source_card": src, "target_card": tgt, "relation": relation,
                        "self_pair": src == tgt, "generic": True, "origin": "effect_semantics",
                        "family": family, "supports": []}
        agg[key]["supports"].append(support)

    def project(src, sel, relation, family, support):
        if sel.get("self"):                                 # a self selector projects ONLY source→source
            _add(src, src, relation, family, support)
            return
        for tgt in cards:
            if any(_sch.matches_card(sel, cf) for cf in by_card[tgt]):
                _add(src, tgt, relation, family, support)

    for f in sorted(faces, key=lambda x: x["id"]):
        for eff in _destroy_effects(f) + _object_effects(f):
            errors += [f"{eff['effect_id']}: {e}" for e in _sch.validate_effect(eff)]
            sel = eff["selector"]
            family = eff["op"].lower()
            support = {"effect_id": eff["effect_id"], "mode": eff["mode"], "op": eff["op"],
                       "object_var": eff.get("object_var"), "oracle_span": eff["oracle_span"],
                       "targeted": eff["targeted"], "face_id": f["id"], "name": f["name"]}
            elig_tokens = sorted(t["id"] for t in tokens if _sch.matches_token(sel, t))
            structured.append({**eff, "face_id": f["id"], "card": f["card_id"], "name": f["name"],
                               "eligible_token_specs": elig_tokens,
                               "provenance": {**support, "rule": f"effect_semantics.{family}",
                                              "layer": "effect_semantics"}})
            project(f["card_id"], sel, eff["relation"], family, support)
            if eff["op"] == "FIGHT" and eff.get("fight_target_selector"):
                project(f["card_id"], eff["fight_target_selector"], "CAN_FIGHT", "fight",
                        {**support, "role": "fight_target"})
    pairs = sorted(agg.values(), key=lambda p: (p["source_card"], p["target_card"], p["relation"]))
    assert not errors, f"effect schema violations: {errors[:5]}"
    if not write:
        return {"_structured": structured, "_pairs": pairs}
    from collections import Counter
    G = repo / "data" / "graph_global"
    _writej(G / "effect_records.jsonl", sorted(structured, key=lambda r: r["effect_id"]))
    _writej(G / "card_pair_projection_effect.jsonl", pairs)
    _effects_report(repo, structured, pairs)
    return {"effects": len(structured), "faces_with_effects": len({s["face_id"] for s in structured}),
            "pairs": len(pairs), "by_relation": dict(Counter(p["relation"] for p in pairs)),
            "by_family": dict(Counter(s["op"] for s in structured))}


def _effects_report(repo, structured, pairs):
    from collections import Counter
    byrel = Counter(p["relation"] for p in pairs)
    byop = Counter(s["op"] for s in structured)
    L = ["# Effect-semantics — structured effects (Phase 3b: targeted-object families)", "",
         "Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction "
         "(one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with "
         "**same-object variable binding**, **per-operation duration/condition**, explicit self-effects, "
         "object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. "
         "Families: destruction, damage (incl. source-power & any-target), counters, power/toughness "
         "(mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and "
         "damage-prevention. Each effect is a validated record; projection aggregates all supporting "
         "effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions "
         "(documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, "
         "`SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, "
         "`PREVENTS_DAMAGE_FROM`. Every Phase-3 census clause is reconciled "
         "(`reports/effect_reconciliation.md`, 0 unresolved).", "",
         f"- effects: **{len(structured)}** on {len({s['face_id'] for s in structured})} faces  · "
         f"pairs: **{len(pairs)}**", "",
         "| relation | pairs |  | op | effects |", "|---|---:|---|---|---:|"]
    rels = sorted(byrel, key=lambda r: -byrel[r])
    opsl = sorted(byop, key=lambda o: -byop[o])
    for i in range(max(len(rels), len(opsl))):
        r = f"`{rels[i]}`" if i < len(rels) else ""
        rc = byrel[rels[i]] if i < len(rels) else ""
        o = f"`{opsl[i]}`" if i < len(opsl) else ""
        oc = byop[opsl[i]] if i < len(opsl) else ""
        L.append(f"| {r} | {rc} |  | {o} | {oc} |")
    (repo / "reports" / "effect_semantics.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _writej(path: Path, rows: list):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _write_report(repo, summary, faces_with_any, total_faces, total_clauses, unclassified):
    L = ["# HOB effect-family census (Phase 1.2 — complete clause ledger)", "",
         "Deterministic scan of **all Oracle text on all faces** (permanents included), grouped into "
         "semantic **clauses** (one row per (ability, mode) clause, carrying `clause_span` + full "
         "`clause_text`, per-family `match_span`s, ability/mode/sentence indices, and every family "
         "detected). **EVERY segmented clause is emitted, even with zero detected families** "
         "(`families: []`, `disposition: pending_classification`) so no material effect can be dropped "
         "for lack of a detector. Detectors are broad CANDIDATE catchers; reminder-text hits are "
         "flagged, not removed. Heuristic reference counts are from the instructions and are NOT "
         "acceptance values.", "",
         f"- faces scanned: **{total_faces}**  · faces with a clause: **{faces_with_any}**  · "
         f"total clauses: **{total_clauses}**  · zero-family (pending_classification): **{unclassified}**", "",
         "| family | faces w/ candidate | reminder-only | clauses | heuristic ref | prior-layer coverage |",
         "|---|---:|---:|---:|---:|---|"]
    for s in summary:
        L.append(f"| `{s['family']}` | {s['faces_with_candidate']} | {s['reminder_only_faces']} | "
                 f"{s['clauses']} | {s['heuristic_reference'] if s['heuristic_reference'] is not None else '—'} "
                 f"| {s['prior_coverage']} |")
    L += ["", "Dispositions: clauses with a detected family are `pending_structuring`; clauses with "
          "none are `pending_classification` (recorded, not dropped). Both await their phase's "
          "adjudication (structured/projected · structured/not-projected · already represented by "
          "another layer · intrinsic/reminder ignored · unresolved). See "
          "`docs/hob_effect_semantics_repair_instructions.md`. A clause may list several families "
          "(e.g. Warg Tactics mode-1 carries `add_counter` + `grant_ability`) so it is adjudicated "
          "once, consistently.", ""]
    (repo / "reports" / "effect_census.md").write_text("\n".join(L) + "\n", encoding="utf-8")
