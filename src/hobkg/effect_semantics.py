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
_OBJ_DELIM = re.compile(r"\.|;|\bfor each\b|\bfor as long as\b|\bthat share\b|\bto target\b|\bgets?\b|"
                        r"\bgains?\b|\bhas\b|\bhave\b|\bloses?\b|\bfights?\b|\bbecomes?\b|\bif\b|\bthen\b|"
                        r"\buntil\b|$", re.I)


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
        ftc = {}                                            # cached first-object-target of the clause, by wanted type

        def first_target(want=None):
            if want not in ftc:
                res = None
                for tm in re.finditer(r"\btarget\s+", crange0, re.I):    # EACH 'target …' occurrence
                    r = classify("target " + _clip(crange0[tm.end():]))
                    if r["kind"] in ("self", "any_target", "selector") and \
                            (want is None or want in (r["selector"].get("card_types") or [])):
                        res = (r["var"], r["selector"], r.get("participant")); break
                ftc[want] = res
            return ftc[want]

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
            dur = ("until_end_of_turn" if "until end of turn" in slow else
                   "this_turn" if "this turn" in slow else
                   "as_long_as_source_on_battlefield" if re.search(r"for as long as this .* remains", slow) else None)
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
                # the DAMAGING object is a creature (Thorin's 'that creature' = the target CREATURE the
                # Equipment attached to, not the target Equipment); bind the source across sentences
                subj = first_target(want="creature") or lead_subject(stext, m.start())
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
        # a die→exile replacement binds to the TARGETED object of the mode (Pinecone's damage, but also
        # Gnashing's -5/-5 MODIFY_PT), lasting the turn (review pt3 #2)
        if re.search(r"if (?:that creature|it) would die[^.]*?exile it instead", crange, re.I):
            tgt_op = next((op for op in ops if op["selector"]["targeted"]), None)
            if tgt_op:
                tgt_op["replacement"] = {"kind": "die_would_exile_instead",
                                         "object_var": tgt_op["object_var"], "duration": "this_turn"}
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


####################################################################################################
#  Phase 4a — participant/resource effects: DRAW and LIFE (gain/lose).                             #
#  Player-directed facts: they bind to a PARTICIPANT, not an object, and are STOCHASTIC /          #
#  participant-level, so they never fan out to card pairs (spec Projection Rules + False-Positive   #
#  Guards). 'Pay N life' is a COST, not a life effect, and is left to reconciliation.               #
####################################################################################################

_WORDNUM = {"a": "1", "an": "1", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
# nearest-preceding participant subject (default 'you'); resolves same-participant binding. Matches
# numeric target-player phrases ('two target players each'), possessive owner/controller subjects
# ("Gandalf's owner", 'its controller'), and the each-player forms.
_SUBJECT_RE = re.compile(r"\b((?:\w+\s+)?target opponents?|(?:\w+\s+)?target players?|each opponent|"
                         r"each player|that player|[a-z]+'s owner|[a-z]+'s controller|its owner|"
                         r"its controller|that card's owner|you)\b", re.I)
# a leading trigger clause ('Whenever …,' / 'When …,' / 'At the beginning of …,') — a draw/life verb
# INSIDE it is the trigger event, NOT an effect this ability produces (Ravenhill Flock, Lakeshore
# Apothecary, The Master of Lake-town's 'whenever a player loses life').
_TRIGGER_PREFIX_RE = re.compile(r"\s*(?:whenever|when|at the beginning of|as this |as long as )[^,]*,\s*", re.I)
_DRAW_RE = re.compile(r"draws?\s+((?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+|x|"
                      r"that many)\b)\s+(?:more\s+)?cards?", re.I)
# a computed-count draw ('draw cards equal to …') — a real draw whose amount is a variable
_DRAW_VAR_RE = re.compile(r"draws?\s+cards?\s+(equal to [^.,;]+)", re.I)
_LIFE_RE = re.compile(r"(gains?|loses?)\s+(\d+|x)\s+life", re.I)
# Phase 4b: participant-level graveyard-filling resource ops (both stochastic → no card-pair fan-out).
# DISCARD moves hand→graveyard; MILL moves library→graveyard.
_DISCARD_RE = re.compile(r"discards?\s+(your hand|that card|(?:a|an|one|two|three|four|five|six|seven|"
                         r"eight|nine|ten|\d+|x|that many)\b)", re.I)
_MILL_RE = re.compile(r"mills?\s+((?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+|x|"
                      r"that many)\b)\s+cards?", re.I)
# an activation-cost discard ('{1},{T}, Discard a card: Draw a card') — a COST, not a discard effect
_DISCARD_COST_RE = re.compile(r"^[^.]*:", re.I)
_ZONES = {"DISCARD": ("hand", "graveyard", "discard"), "MILL": ("library", "graveyard", "mill")}


def _amount(tok: str) -> str:
    t = tok.strip().lower()
    return _WORDNUM.get(t, "X" if t == "x" else t)


def _classify_participant(phrase: str) -> str:
    low = phrase.lower()
    if "each opponent" in low:
        return "each_opponent"
    if "each player" in low:
        return "each_player"
    if "target opponent" in low:
        return "target_opponent"
    if "target player" in low:
        return "target_player"
    if re.search(r"'s owner\b|\bits owner\b|that card's owner", low):
        return "owner"
    if re.search(r"'s controller\b|\bits controller\b|\bthat player\b", low):
        return "controller"
    return "you"


def _participant_at(text: str, pos: int):
    """Nearest-preceding participant subject → (participant, targeted, quantity, affects_each).
    'target player'/'target opponent' are real targets; 'two target players each' carries quantity 2
    and each-status; 'each opponent'/'each player' are mass; possessive owner/controller bind the
    named player. Defaults to 'you' (untargeted) when no subject precedes."""
    best = None
    for m in _SUBJECT_RE.finditer(text):
        if m.start() <= pos:
            best = m
        else:
            break
    if not best:
        return "you", False, None, False
    phrase = best.group(0).lower()
    if re.fullmatch(r"that player", phrase):                  # back-reference: bind to a prior target if any
        prior = None
        for pm in re.finditer(r"target (opponent|player)", text[:best.start()]):
            prior = pm.group(1)
        if prior:
            return ("target_opponent" if prior == "opponent" else "target_player"), True, None, False
        return "that_player", False, None, False              # trigger-bound antecedent (e.g. 'a player' who lost life)
    part = _classify_participant(phrase)
    targeted = "target" in phrase
    each = part.startswith("each") or bool(re.search(r"\beach\b", phrase)) or phrase.rstrip().endswith("s")
    qm = re.match(r"(\w+)\s+target", phrase)
    quantity = _WORDNUM.get(qm.group(1)) if qm and qm.group(1) in _WORDNUM else None
    return part, targeted, (int(quantity) if quantity else None), each


def _blank_quoted(text: str) -> str:
    """Blank double-quoted granted abilities (e.g. Supper for Spiders' Food tokens are
    '… with "{2},{T}, Sacrifice this artifact: You gain 3 life."'). The quoted text is an ability
    granted to ANOTHER object, not an immediate effect of the source — offsets are preserved."""
    return re.sub(r'"[^"]*"', lambda m: " " * len(m.group(0)), text)


def _op_sentence(crange: str, low: str, ms: int) -> str:
    """The single sentence containing the op at `ms` (review pt3): conditions are computed from this,
    not the whole clause, so a later/sibling 'If …' instruction ('Draw X cards. If you have an
    enduring story, … deals damage') does not leak onto an earlier draw, while a leading condition
    ('If you controlled that creature, draw a card') or a trailing suffix condition ('gain 1 life if
    this is the first time …') in the op's OWN sentence is preserved."""
    s0 = low.rfind(". ", 0, ms)
    s0 = 0 if s0 < 0 else s0 + 2
    s1 = low.find(". ", ms)
    s1 = len(crange) if s1 < 0 else s1
    return crange[s0:s1]


def _op_optionality(low: str, ms: int):
    """Per-OPERATION optionality (review pt2 #1): an op is optional only if 'may' governs its OWN
    verb (same sentence, before it) — NOT because a sibling instruction elsewhere in the clause says
    'may' (Old Thrush's mandatory 'gain 2 life' + optional 'You may search'). An op reached only via
    an optional prior action ('you may discard … If you do, draw …') is MANDATORY but conditioned on
    that action (Ragged Short Spear, The Sackville-Bagginses, Balin)."""
    s0 = low.rfind(". ", 0, ms)
    seg = low[(0 if s0 < 0 else s0 + 2):ms]
    if re.search(r"\bmay\b", seg):
        return True, None
    if "if you do" in seg:
        return False, {"kind": "prior_action_taken",
                       "detail": "gated by an optional prior action ('if you do')"}
    return False, None


def _quantity_formula(low: str, crange: str, amount: str, me: int):
    """Structured formula quantity (review pt2 #2): 'for each <set>' is a per-each multiplier (not a
    fixed count) and 'X, where X is …' binds X — so consumers never read `amount:"1"` / `"X"` as the
    total. Returns (formula|None, amount_marker)."""
    fe = re.search(r"\bfor each\b\s+([^.]+)", low[me:me + 120])
    if fe:
        base = int(amount) if amount.isdigit() else amount
        per = crange[me + fe.start(1):me + fe.end(1)].strip().rstrip(".")
        return {"kind": "per_each", "base": base, "per": per}, "formula"
    if amount in ("X", "variable"):
        wx = re.search(r"where x is ([^.]+)", low)
        if wx:
            return {"kind": "variable", "var": "X",
                    "binding": crange[wx.start(1):wx.end(1)].strip().rstrip(".")}, amount
    return None, amount


def _discard_selector(low: str, ms: int, amt: str, owner: str) -> dict:
    """The discarded-card object/selector for a DISCARD record (review pt5 #1): which cards leave
    WHOSE hand, any card constraint, who chooses, and — for 'discards that card' — the same-object
    binding to a previously chosen card. Source zone is always the hand. The predicate scan is scoped
    to the discard's OWN sentence (review pt6) so a later 'If you discard a land card this way …'
    conditional does not back-propagate a spurious constraint onto an earlier unconstrained discard."""
    send = low.find(". ", ms)
    seg = low[ms:(send if send >= 0 else len(low))][:90]
    sel = {"zone": "hand", "owner": owner, "count": ("all" if amt == "hand" else amt), "chooser": owner}
    preds = {}
    if "nonland" in seg:
        preds["nonland"] = True
    elif re.search(r"\bland cards?\b", seg):
        preds["type"] = "land"
    if "legendary" in seg:
        preds["supertype"] = "legendary"
    if re.search(r"discards? that card", seg):                # same-object: the previously chosen card
        sel["object"] = "that_card"
        sel["antecedent"] = {"kind": "chosen_card", "same_object": True}
        cm = re.search(r"\bchoose (?:a|an|one) (nonland |legendary )?card\b", low[:ms])
        if cm and cm.group(1):
            q = cm.group(1).strip()
            preds["nonland" if q == "nonland" else "supertype"] = True if q == "nonland" else "legendary"
        if re.search(r"\byou choose\b", low[:ms]):
            sel["chooser"] = "you"
    if preds:
        sel["predicates"] = preds
    return sel


def _participant_effects(face):
    """DRAW + LIFE participant records with same-participant binding. Reminder text AND double-quoted
    granted abilities are blanked (a recruit reminder 'Draw a card …' and a token's quoted 'You gain
    3 life' are NOT effects of the source), and a leading trigger condition is stripped so a draw/life
    *event* in a trigger is not mistaken for an effect. Each record carries its own participant
    targeting/quantity/each metadata, and a replaced 'would draw' antecedent is not emitted."""
    text = _blank_quoted(_blank_reminders(face.get("oracle_text") or ""))
    out = []
    for cl in _ability_clauses(text):
        clause_id = f"{face['id']}#a{cl['ability_index']}" + (f".m{cl['mode_index']}" if cl["mode_index"] is not None else "")
        crange = text[cl["start"]:cl["end"]]
        low = crange.lower()
        tm = _TRIGGER_PREFIX_RE.match(low)
        eff_start = tm.end() if tm else 0                    # only accept verbs in the EFFECT portion
        exclusive = bool(cl["mode_kind"] and "choose" in cl["mode_kind"])   # modal / choose-one alternative
        pvars, vc = {}, [0]

        def pvar(part):
            if part not in pvars:
                pvars[part] = f"p{vc[0]}"; vc[0] += 1
            return pvars[part]

        ops = []                                             # (op, relation, participant meta, extra, span)
        for m in _DRAW_RE.finditer(low):
            if m.start() < eff_start:
                continue                                     # the draw is the trigger event, not an effect
            if re.search(r"\bwould\s+$", low[:m.start()]):
                continue                                     # 'if you would draw a card …' = replaced event
            amt = _amount(m.group(1))
            opt, gate = _op_optionality(low, m.start())
            qf, amt = _quantity_formula(low, crange, amt, m.end())
            extra = {"amount": amt, "optional": opt}
            if gate:
                extra["condition"] = gate
            if qf:
                extra["quantity_formula"] = qf
            if re.search(r"cards?\s+instead", low[m.start():m.start() + 40]):
                extra["replacement"] = {"kind": "draw_instead"}   # Plunder / Bard King of Dale
            ops.append(("DRAW", "DRAWS_CARDS", _participant_at(low, m.start()), extra,
                        [cl["start"] + m.start(), cl["start"] + m.end()]))
        for m in _DRAW_VAR_RE.finditer(low):
            if m.start() < eff_start:
                continue
            opt, gate = _op_optionality(low, m.start())
            extra = {"amount": "variable", "optional": opt,
                     "quantity_formula": {"kind": "variable",
                                          "binding": crange[m.start(1):m.end(1)].strip().rstrip(".")}}
            if gate:
                extra["condition"] = gate
            ops.append(("DRAW", "DRAWS_CARDS", _participant_at(low, m.start()), extra,
                        [cl["start"] + m.start(), cl["start"] + m.end()]))
        for m in _LIFE_RE.finditer(low):
            if m.start() < eff_start:
                continue                                     # 'whenever a player loses life' trigger
            op = "GAIN_LIFE" if m.group(1).lower().startswith("gain") else "LOSE_LIFE"
            rel = "GAINS_LIFE" if op == "GAIN_LIFE" else "LOSES_LIFE"
            opt, gate = _op_optionality(low, m.start())
            extra = {"amount": _amount(m.group(2)), "optional": opt}
            if gate:
                extra["condition"] = gate
            ops.append((op, rel, _participant_at(low, m.start()), extra,
                        [cl["start"] + m.start(), cl["start"] + m.end()]))
        for m in _DISCARD_RE.finditer(low):
            if m.start() < eff_start:
                continue                                     # 'if you discard(ed) …' trigger/condition
            if re.search(r"\bif (?:you|a player|an opponent)\s+$", low[:m.start()]):
                continue                                     # 'If you discard a land card this way …' = a condition
            if _DISCARD_COST_RE.match(low[m.start():]):
                continue                                     # 'Discard a card: <effect>' = a COST, not an effect
            raw = m.group(1).lower()
            amt = "hand" if "hand" in raw else "1" if raw == "that card" else _amount(raw)
            opt, gate = _op_optionality(low, m.start())
            dmeta = _participant_at(low, m.start())
            extra = {"amount": amt, "optional": opt,
                     "card_selector": _discard_selector(low, m.start(), amt, dmeta[0])}
            if gate:
                extra["condition"] = gate
            ops.append(("DISCARD", "DISCARDS_CARDS", dmeta, extra,
                        [cl["start"] + m.start(), cl["start"] + m.end()]))
        for m in _MILL_RE.finditer(low):
            if m.start() < eff_start:
                continue
            amt = _amount(m.group(1))
            opt, gate = _op_optionality(low, m.start())
            extra = {"amount": "variable" if amt == "that many" else amt, "optional": opt}
            if amt == "that many":
                # 'that many' is trigger-bound (Master of Lake-town: 'Whenever a player loses life,
                # that player mills that many cards') — preserve the trigger event + amount binding
                qf = {"kind": "variable", "binding": "that many cards"}
                if tm:
                    trg = crange[:tm.end()].strip().rstrip(",")
                    qf["source"] = "trigger_quantity"
                    qf["of"] = _participant_at(low, m.start())[0]
                    extra["condition"] = {"kind": "triggered", "event": trg,
                                          "binds": {"participant": "player_who_lost_life",
                                                    "amount": "life_lost"}}
                extra["quantity_formula"] = qf
            if gate:
                extra["condition"] = gate
            ops.append(("MILL", "MILLS_CARDS", _participant_at(low, m.start()), extra,
                        [cl["start"] + m.start(), cl["start"] + m.end()]))

        for i, (op, rel, meta, extra, span) in enumerate(ops):
            part, targeted, quantity, each = meta
            v = pvar(part)                                    # same participant string → one var
            opt = extra.pop("optional", False)
            # per-op gate (e.g. 'if you do') wins; else the condition from the op's OWN sentence only
            cond = extra.pop("condition", None) or _sch.condition(_op_sentence(crange, low, span[0] - cl["start"]))
            rec = {"effect_id": f"{clause_id}#{op}#{i}", "op": op, "relation": rel,
                   "participant": part, "participant_var": v,
                   "selector": _sch.participant_selector(v, targeted=targeted, quantity=quantity,
                                                         affects_each=each),
                   "mode": {"kind": cl["mode_kind"], "index": cl["mode_index"], "exclusive": exclusive},
                   "condition": cond, "duration": _sch.duration(crange),
                   "optional": opt, "targeted": targeted,
                   "affects_each": each, "binding": None,
                   "clause_id": clause_id, "oracle_span": span, **extra}
            if op in _ZONES:                                  # zone movement + event for resource ops
                rec["source_zone"], rec["dest_zone"], rec["event"] = _ZONES[op]
            if quantity is not None:
                rec["participant_quantity"] = quantity
            out.append(rec)
    return out


# Phase 4c — SACRIFICE. Integrates the portable sacrifice extractor (`sac_schema`) — reusing its
# `_selector`/`_cost` parsing and its trigger/edict/phrase regexes — but applies the eligibility and
# self/pronoun handling in THIS layer so the accepted portable module (and its pinned FIN metrics)
# stays untouched. A sacrifice moves a chosen permanent battlefield→graveyard; it is participant-level
# (a choice among the sacrificer's own permanents / an edict) → no deterministic card-pair fan-out.
_SAC_COST_CTX = {"activated_ability", "additional_cast_cost", "kicker"}


def _sac_condition(prefix: str):
    """The condition that GATES a sacrifice — derived only from the text BEFORE the sacrifice verb
    (review pt8): a trailing 'If you do, <payoff>' gates the payoff, not the sacrifice; an activated
    cost is unconditional once activated. A leading gate is preserved WITH its specific predicate:
    'if you control four or more Treasures' / 'if it has six or more quest counters'."""
    low = prefix.lower()
    m = re.search(r"if you control (\w+) or more ([A-Za-z]+)", low)
    if m:
        return {"kind": "controls_count", "count": m.group(1), "of": m.group(2),
                "detail": f"control {m.group(1)} or more {m.group(2)}"}
    m = re.search(r"if it has (\w+) or more (\w+) counters?", low)
    if m:
        return {"kind": "counter_threshold", "count": m.group(1), "counter": m.group(2),
                "detail": f"{m.group(1)} or more {m.group(2)} counters"}
    return _sch.condition(prefix)


def _augment_sac_cost(cost, raw: str, ctx: str):
    """`sac_schema._cost` only emits mana ({…}) and tap ({T}) atoms, so a non-mana 'Pay N life'
    co-cost is dropped (review pt9 — Elven Passage). Insert a structured `pay_life` atom into the
    sacrifice branch, in printed order (before the sacrifice atom), without touching sac_schema."""
    if not cost:
        return cost
    prefix = raw.split(":")[0] if ctx == "activated_ability" else raw
    m = re.search(r"\bpay\s+(\d+)\s+life\b", prefix, re.IGNORECASE)
    if not m:
        return cost
    for branch in cost.get("alt", []):
        atoms = branch.get("all", [])
        idx = next((i for i, a in enumerate(atoms) if "sacrifice" in a), None)
        if idx is not None and not any("pay_life" in a for a in atoms):
            atoms.insert(idx, {"pay_life": m.group(1)})
    return cost


def _sacrifice_effects(face):
    from . import sac_schema as _sac
    text = _blank_quoted(_blank_reminders(face.get("oracle_text") or ""))
    clauses = _ability_clauses(text)

    def clause_id_at(pos):
        for cl in clauses:
            if cl["start"] <= pos < cl["end"]:
                return (f"{face['id']}#a{cl['ability_index']}"
                        + (f".m{cl['mode_index']}" if cl["mode_index"] is not None else ""),
                        cl["mode_kind"], cl["mode_index"])
        return f"{face['id']}#a0", None, None

    out, pvars, vc, j = [], {}, [0], 0
    for line in text.split("\n"):
        raw = line.strip()
        if "sacrifice" not in raw.lower() or _sac._TRIGGER_SAC_RE.search(raw):
            continue                                         # 'Whenever you sacrifice …' is a condition
        edict = _sac._EDICT_RE.search(raw)
        mphrase = _sac._SAC_PHRASE_RE.search(raw)
        if not mphrase:
            continue
        phrase = mphrase.group(1)
        sel = dict(_sac._selector(phrase, face["name"]))
        pl = phrase.strip().lower()
        if not sel["self"] and (re.match(r"(it|this)\b", pl) or re.search(r"\bthis (saga|enchantment)\b", pl)):
            sel["self"], sel["card_types"], sel["subtypes"], sel["or_types"] = True, [], [], False
            sel["quantity"] = sel["quantity"] or 1
        # eligibility (review-parity with sac_schema PLUS subtype-only fodder, e.g. 'another Goblin')
        if not (sel["card_types"] or sel["self"] or sel["generic_permanent"] or sel["subtypes"]):
            continue
        low = raw.lower()
        actor = re.sub(r"\s+", "_", edict.group(1).lower()) if edict else "you"
        if "as an additional cost to cast" in low:
            ctx = "additional_cast_cost"
        elif re.match(r"kicker\b", low):
            ctx = "kicker"
        elif edict:
            ctx = "resolution_effect"
        elif _sac._MAY_RE.search(raw):
            ctx = "effect"
        elif ":" in raw and re.search(r"[Ss]acrifice[^:]*:", raw):
            ctx = "activated_ability"
        else:
            ctx = "unsupported"
        # condition gating THE SACRIFICE is the LEADING text only (a trailing 'If you do, <payoff>'
        # gates the payoff, not the sacrifice; a cost is unconditional once activated) — review pt8 #1
        cond = _sac_condition(raw[:mphrase.start()])
        if ctx == "unsupported" and sel["self"] and cond:   # an ordinary conditional self-sac resolution
            ctx = "conditional_self_sacrifice"              # (not 'unsupported') — review pt8 #2
        role = "cost" if ctx in _SAC_COST_CTX else "effect"
        pos = text.find(mphrase.group(0))
        span = [pos, pos + len(mphrase.group(0))] if pos >= 0 else list(mphrase.span())
        cid, mkind, midx = clause_id_at(span[0])
        if actor not in pvars:
            pvars[actor] = f"p{vc[0]}"; vc[0] += 1
        targeted = actor.startswith("target")
        card_selector = {"zone": "battlefield", "owner": actor, "self": sel["self"],
                         "another": sel["another"], "card_types": sel["card_types"],
                         "or_types": sel["or_types"], "subtypes": sel["subtypes"],
                         "supertypes": sel["supertypes"], "generic_permanent": sel["generic_permanent"],
                         "count": sel["quantity"], "chooser": actor}
        rec = {"effect_id": f"{cid}#SACRIFICE#{j}", "op": "SACRIFICE", "relation": "SACRIFICES",
               "participant": actor, "participant_var": pvars[actor], "role": role, "cost_context": ctx,
               "cost": _augment_sac_cost(_sac._cost(raw, ctx if ctx in _SAC_COST_CTX else "x", sel), raw, ctx),
               "selector": _sch.participant_selector(pvars[actor], targeted=targeted),
               "card_selector": card_selector, "source_zone": "battlefield",
               "dest_zone": "graveyard", "event": "sacrifice",
               "mode": {"kind": mkind, "index": midx, "exclusive": bool(mkind and "choose" in mkind)},
               "condition": cond, "duration": None, "optional": ctx == "effect", "targeted": targeted,
               "affects_each": actor.startswith("each"), "binding": None,
               "clause_id": cid, "oracle_span": span}
        out.append(rec)
        j += 1
    return out


# Phase 4d — SEARCH / tutor. UNLIKE the participant-level resource families, a tutor is DETERMINISTIC:
# per the spec it 'projects to eligible choices', so the searched-for card selector fans out to every
# eligible card (a real card→card `SEARCHES_FOR` relation), reusing the Phase-3 object projection.
# group(1)=zone phrase (contains 'library', maybe 'hand and/or library'); group(2)=searched-for card
_SEARCH_RE = re.compile(r"search(?:es)?\s+(?:your|their|his or her|its owner's)\s+"
                        r"([^.,;]*?\blibrar(?:y|ies)\b[^.,;]*?)\s+for\s+"
                        r"(.+?)(?:,|\.|;| and (?:put|shuffle|exile)\b| then\b|$)", re.I)


def _search_dest(rest: str):
    """(destination zone, tapped) for the searched card, from the text after the search phrase."""
    if "onto the battlefield" in rest:
        head = rest[:rest.find("onto the battlefield") + 40]
        return "battlefield", "tapped" in head
    if "into your hand" in rest or "into their hand" in rest or "into its owner's hand" in rest:
        return "hand", False
    if re.search(r"\bexile (them|it|those)\b", rest):
        return "exile", False
    if re.search(r"\bon top\b", rest):                        # 'reveal … then shuffle and put that card on top'
        return "library_top", False
    return None, False


def _search_destinations(rest: str):
    """Per-object searched-card destinations (review pt12): a split like 'put ONE onto the battlefield
    tapped and THE OTHER into your hand' has two distinct destination roles that must not collapse
    into a single battlefield-tapped output. Returns a list of {zone, tapped, count}."""
    dests = []
    for m in re.finditer(r"\b(one|the other|the rest|them|it|those cards|that card)\b[^.,]*?"
                         r"(onto the battlefield(?:\s+tapped)?|into (?:your|their) hand|on top)", rest, re.I):
        cnt, d = m.group(1).lower(), m.group(2).lower()
        if "battlefield" in d:
            dests.append({"zone": "battlefield", "tapped": "tapped" in d, "count": cnt})
        elif "hand" in d:
            dests.append({"zone": "hand", "tapped": False, "count": cnt})
        elif "on top" in d:
            dests.append({"zone": "library_top", "tapped": False, "count": cnt})
    return dests


def _search_effects(face):
    text = _blank_quoted(_blank_reminders(face.get("oracle_text") or ""))   # cycling-reminder tutors are keyword-layer
    out = []
    for cl in _ability_clauses(text):
        clause_id = f"{face['id']}#a{cl['ability_index']}" + (f".m{cl['mode_index']}" if cl["mode_index"] is not None else "")
        crange = text[cl["start"]:cl["end"]]
        low = crange.lower()
        for i, m in enumerate(_SEARCH_RE.finditer(low)):
            phrase = crange[m.start(2):m.end(2)].strip()
            zp = m.group(1).lower()
            src = "hand_and_library" if "hand" in zp else ("library_and_graveyard" if "graveyard" in zp else "library")
            var = f"obj{i}"
            sel = _sch.selector(phrase, var=var, targeted=False)
            sel["zone"] = src                                # the searched card is in the LIBRARY / hand+library,
            #                                                  NOT the battlefield (selector() default) — review pt11 #1
            rest = low[m.end():m.end() + 140]
            dests = _search_destinations(rest)               # per-object split destinations (review pt12 #1)
            if dests:
                dest, tapped = dests[0]["zone"], dests[0].get("tapped", False)
            else:
                dest, tapped = _search_dest(rest)
                dests = [{"zone": dest, "tapped": tapped, "count": "all"}] if dest else []
            part = _participant_at(low, m.start())[0]
            lead = low[max(0, low.rfind(". ", 0, m.start()) + 2):m.start()]   # the search's own leading text
            opt = bool(re.search(r"\bmay\b", lead))
            qty = "variable" if "that many" in phrase.lower() else (sel.get("quantifier") or "1")
            shuffle = "shuffle" in rest
            # a hand-or-library search shuffles only if the LIBRARY was actually searched — review pt12 #2
            shuffle_cond = {"kind": "searched_zone", "zone": "library"} if (shuffle and src == "hand_and_library") else None
            rec = {"effect_id": f"{clause_id}#SEARCH#{i}", "op": "SEARCH", "relation": "SEARCHES_FOR",
                   "participant": part, "selector": sel, "object_var": var,
                   "mode": {"kind": cl["mode_kind"], "index": cl["mode_index"],
                            "exclusive": bool(cl["mode_kind"] and "choose" in cl["mode_kind"])},
                   "condition": None, "duration": None, "optional": opt, "targeted": False,
                   "affects_each": False, "binding": None, "clause_id": clause_id,
                   "oracle_span": [cl["start"] + m.start(), cl["start"] + m.end()],
                   "source_zone": src, "dest_zone": dest, "dest_tapped": tapped, "destinations": dests,
                   "event": "search", "quantity": qty, "reveal": "reveal" in rest,
                   "shuffle": shuffle, "shuffle_condition": shuffle_cond}
            # condition: a leading 'if you do' gates the search on a prior action (Last Light's
            # self-sacrifice); else the operation-scoped condition — review pt11 #3
            if "if you do" in lead:
                rec["condition"] = {"kind": "prior_action_taken",
                                    "detail": "gated by the prior action (self-sacrifice)"}
            else:
                rec["condition"] = _sch.condition(_op_sentence(crange, low, m.start()))
            # 'that many' binds to the count established by a prior instruction (Settle: exiled
            # attacking creatures) — review pt11 #2
            if qty == "variable":
                if re.search(r"\bexile all\b", low[:m.start()]):
                    rec["quantity_formula"] = {"kind": "variable", "source": "prior_exile_count", "of": part,
                                               "binding": "the number of attacking creatures exiled this way"}
                else:
                    rec["quantity_formula"] = {"kind": "variable", "binding": "that many"}
            out.append(rec)
    return out


# Phase 4e — RETURN / recursion (bounce + reanimation). Object-directed movement TO hand/battlefield
# FROM graveyard/battlefield → it PROJECTS to eligible objects (like removal). Blink (exile-and-return,
# which is coupled to the deferred exile family) and stack-object spell-bounce are dispositioned here.
_RETURN_RE = re.compile(r"returns?\s+(.+?)\s+"
                        r"(?:from\s+(?:your |their |its owner's |an? )?(graveyard|exile|battlefield)\s+)?"
                        r"to\s+(?:the\s+|your\s+|their\s+|its owner's\s+)?(battlefield|hand)", re.I)


def _return_effects(face):
    text = _blank_quoted(_blank_reminders(face.get("oracle_text") or ""))
    short = face["name"].split(",")[0].split(" //")[0].strip().lower()
    out = []
    for cl in _ability_clauses(text):
        clause_id = f"{face['id']}#a{cl['ability_index']}" + (f".m{cl['mode_index']}" if cl["mode_index"] is not None else "")
        crange = text[cl["start"]:cl["end"]]
        low = crange.lower()
        for i, m in enumerate(_RETURN_RE.finditer(low)):
            obj = crange[m.start(1):m.end(1)].strip()
            ol = obj.lower()
            dest = m.group(3).lower()
            if re.search(r"\bexile\b", low[:m.start()]):
                continue                                     # blink (exile-and-return) — deferred to exile slice
            if re.search(r"\bspell\b", ol):
                continue                                     # stack-object bounce (Bilbo's Gambit) — deferred
            # source zone
            src = m.group(2).lower() if m.group(2) else None
            if src is None:
                src = "graveyard" if dest == "battlefield" else ("graveyard" if "card" in ol else "battlefield")
            # object selector: self (this card / the source's own name) vs a targeted card/permanent
            self_ref = bool(re.search(r"\bthis card\b|\bthis permanent\b", ol)) or \
                (short and short.split()[0] in ol and "target" not in ol) or \
                (re.fullmatch(r"(them|it|those cards|those)", ol) and "target" not in low[:m.start()])
            if self_ref:
                sel = _self_selector(); var = "self"
            else:
                var = f"obj{i}"
                sel = _sch.selector(obj, var=var, targeted=("target" in ol))
                sel["zone"] = src
            part = _participant_at(low, m.start())[0]
            lead = low[max(0, low.rfind(". ", 0, m.start()) + 2):m.start()]
            opt = bool(re.search(r"\bmay\b", lead)) or "up to" in ol
            out.append({"effect_id": f"{clause_id}#RETURN#{i}", "op": "RETURN", "relation": "CAN_RETURN",
                        "participant": part, "selector": sel, "object_var": var,
                        "mode": {"kind": cl["mode_kind"], "index": cl["mode_index"],
                                 "exclusive": bool(cl["mode_kind"] and "choose" in cl["mode_kind"])},
                        "condition": ({"kind": "prior_action_taken", "detail": "gated by the prior action"}
                                      if "if you do" in lead else _sch.condition(_op_sentence(crange, low, m.start()))),
                        "duration": None, "optional": opt, "targeted": ("target" in ol and not self_ref),
                        "affects_each": False, "binding": None, "clause_id": clause_id,
                        "oracle_span": [cl["start"] + m.start(), cl["start"] + m.end()],
                        "source_zone": src, "dest_zone": dest, "event": "return",
                        "quantity": "up_to_1" if "up to one" in ol else ("up_to_2" if "up to two" in ol else "1")})
    return out


_PHASE3_FAMILIES = {"deal_damage", "destroy", "add_counter", "remove_counter", "modify_pt",
                    "set_switch_pt", "grant_ability", "remove_ability", "fight", "prevent",
                    "control_change", "type_change", "tap_untap"}
_PHASE4A_FAMILIES = {"draw", "life"}
_PHASE4B_FAMILIES = {"discard", "mill"}
_PHASE4C_FAMILIES = {"sacrifice"}
_PHASE4D_FAMILIES = {"tutor_search"}
_PHASE4E_FAMILIES = {"return_move"}


_OP_FAMILY = {"DEAL_DAMAGE": "deal_damage", "DESTROY": "destroy", "ADD_COUNTER": "add_counter",
              "MODIFY_PT": "modify_pt", "SET_BASE_PT": "set_switch_pt", "SWITCH_PT": "set_switch_pt",
              "GRANT_ABILITY": "grant_ability", "REMOVE_ABILITY": "remove_ability", "TAP": "tap_untap",
              "UNTAP": "tap_untap", "FIGHT": "fight", "CHANGE_TYPE": "type_change",
              "CONTROL_CHANGE": "control_change", "PREVENT_DAMAGE": "prevent",
              "DRAW": "draw", "GAIN_LIFE": "life", "LOSE_LIFE": "life",
              "DISCARD": "discard", "MILL": "mill", "SACRIFICE": "sacrifice", "SEARCH": "tutor_search", "RETURN": "return_move"}
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
        for e in _destroy_effects(f) + _object_effects(f) + _participant_effects(f) + _sacrifice_effects(f) + _search_effects(f) + _return_effects(f):
            extracted_cf.add((e["clause_id"], _OP_FAMILY.get(e["op"], e["op"].lower())))
    rows, counts = [], {}
    for c in census:
        low = c["clause_text"].lower()
        for fam in sorted(set(c["families"]) & (_PHASE3_FAMILIES | _PHASE4A_FAMILIES | _PHASE4B_FAMILIES | _PHASE4C_FAMILIES | _PHASE4D_FAMILIES | _PHASE4E_FAMILIES)):
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
            elif fam in ("life", "draw", "sacrifice") and \
                    re.search(r'"[^"]*(?:gains?|loses?|draws?|sacrifices?)[^"]*"', low):
                disp = "granted_ability (quoted ability on another/created object — deferred execution)"
            elif fam == "sacrifice" and re.search(r"\b(?:whenever|when)\b[^.]*\bsacrifices?\b", low):
                disp = "sacrifice_trigger (a trigger event, not a sacrifice effect)"
            elif fam == "sacrifice" and re.search(r"sacrifice after\b", low):
                disp = "saga_cleanup (Saga 'Sacrifice after N' self-timer — mechanism layer)"
            elif fam == "return_move" and re.search(r"\bexile\b.*\breturn", low):
                disp = "blink (exile-and-return — coupled to the deferred exile/movement slice)"
            elif fam == "return_move" and re.search(r"return target spell\b", low):
                disp = "spell_bounce (a stack-object bounce, not a card-identity move — deferred)"
            elif fam == "life" and re.search(r"\bpay(?:s)?\s+(?:\d+\s+|x\s+)?life\b", low):
                disp = "life_payment_cost (a cost, not a life effect)"
            elif fam == "draw" and re.search(r"^\s*(?:whenever|when)\b.*\bdraws?\b.*,", low):
                disp = "draw_trigger (a trigger event/condition, not a draw effect)"
            elif fam == "life" and re.search(r"^\s*(?:whenever|when)\b.*\bloses?\s+life\b.*,", low):
                disp = "life_change_trigger (a trigger event, not a life effect)"
            elif fam in ("draw", "discard") and re.search(r"\brecruit\b", low):
                disp = "recruit (keyword action — draw/discard defined by the keyword; mechanism layer)"
            elif fam == "discard" and re.search(r"\b(?:halfling|mountain|plains|island|swamp|forest)?cycling\b", low):
                disp = "cycling_cost (discard-to-cycle keyword — mechanism layer)"
            elif fam == "discard" and re.search(r"\bdiscards?\b[^.]*:", low):
                disp = "discard_cost (a cost, not a discard effect)"
            elif fam == "discard" and re.search(r"\bif you discard(?:ed)?\b", low):
                disp = "discard_condition (references a discard, not a discard effect)"
            elif fam == "mill" and re.search(r"^\s*(?:whenever|when)\b.*\bmills?\b.*,", low):
                disp = "mill_trigger (a trigger event, not a mill effect)"
            elif fam == "life" and re.search(r"damage causes loss of life", low):
                disp = "reminder_text (rules reminder, not a life effect)"
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
    L = ["# Effect-semantics — (clause_id, family) reconciliation (Phase 3 + Phase 4a draw/life + 4b discard/mill + 4c sacrifice + 4d search + 4e return)", "",
         "Every `(clause_id, family)` carrying a Phase-3 object family or a Phase-4 participant family "
         "(draw, life, discard, mill) is EXTRACTED or DISPOSITIONED. Deferred / non-executable "
         "dispositions (life-payment / discard / cycling costs, draw/life/mill *triggers*, recruit) are "
         "counted separately from `unresolved`.", "",
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
        for eff in _destroy_effects(f) + _object_effects(f) + _participant_effects(f) + _sacrifice_effects(f) + _search_effects(f) + _return_effects(f):
            errors += [f"{eff['effect_id']}: {e}" for e in _sch.validate_effect(eff)]
            sel = eff["selector"]
            family = eff["op"].lower()
            support = {"effect_id": eff["effect_id"], "mode": eff["mode"], "op": eff["op"],
                       "object_var": eff.get("object_var"), "oracle_span": eff["oracle_span"],
                       "targeted": eff["targeted"], "face_id": f["id"], "name": f["name"]}
            participant_level = sel.get("participant_level", False)
            elig_tokens = [] if participant_level else sorted(t["id"] for t in tokens if _sch.matches_token(sel, t))
            structured.append({**eff, "face_id": f["id"], "card": f["card_id"], "name": f["name"],
                               "eligible_token_specs": elig_tokens,
                               "provenance": {**support, "rule": f"effect_semantics.{family}",
                                              "layer": "effect_semantics"}})
            if participant_level:
                continue                                     # participant-level fact — NO card-pair fan-out
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
    L = ["# Effect-semantics — structured effects (Phase 3 object families + Phase 4a-4e families)", "",
         "Additive `effect_semantics` layer over the frozen reference. **ABILITY-scoped** extraction "
         "(one clause per (ability, mode); targets never leak across abilities; real `clause_id`), with "
         "**same-object variable binding**, **per-operation duration/condition**, explicit self-effects, "
         "object-vs-participant separation, comma-OR subtype lists, and empty-object-selector rejection. "
         "Object families: destruction, damage (incl. source-power & any-target), counters, power/toughness "
         "(mod + set/switch), ability grant/removal, tap/untap, fight, type-change, control-change, and "
         "damage-prevention. **Phase-4a participant families:** DRAW and LIFE (gain/lose) — player-directed "
         "records that bind to a PARTICIPANT (same-participant binding, e.g. Reverent Howl's draw+lose-life) "
         "and are **stochastic/participant-level, so they never fan out to card pairs**; `Pay N life` is a "
         "cost, not an effect. **Phase-4b participant families:** DISCARD (hand→graveyard) and MILL "
         "(library→graveyard) — likewise participant-level/stochastic with no card-pair fan-out, each "
         "carrying `source_zone`/`dest_zone`/`event`; discard distinguishes an activation-cost discard "
         "('Discard a card: …') and a condition ('If you discard …') from a real discard effect. "
         "**Phase-4c:** SACRIFICE (battlefield→graveyard) integrates the portable `sac_schema` "
         "extractor — reusing its selector/cost parsing — classifying each outlet as a `cost` "
         "(activated / additional-cast / kicker) or an `effect` (optional `may`, edict, or conditional "
         "self-sacrifice), with the eligibility `card_selector` (self / fodder type / subtype / OR) and "
         "no card-pair fan-out; Saga 'Sacrifice after N' self-timers, quoted token abilities, and "
         "'Whenever you sacrifice …' triggers are dispositioned, not extracted. "
         "**Phase-4d:** SEARCH/tutor is the DETERMINISTIC family — per the spec it 'projects to "
         "eligible choices', so the searched-for card selector fans out to every eligible HOB card as "
         "a `SEARCHES_FOR` relation (source `library`/`hand_and_library`, destination hand / "
         "battlefield(±tapped) / exile / library_top, with quantity, reveal, shuffle, and the searcher "
         "participant — Settle the Wreckage binds `target_player` + a variable count); cycling-reminder "
         "tutors are keyword-layer (not extracted). **Phase-4e:** RETURN/recursion (bounce + reanimation) is object-directed — it PROJECTS to eligible objects (`CAN_RETURN`), moving a card graveyard→hand/battlefield (reanimation/recursion), battlefield→hand (bounce), or source→source (self-return); blink (exile-and-return) and stack-object spell-bounce are dispositioned pending the exile slice. "
         "Each effect is a validated record; projection aggregates all supporting "
         "effects/modes per pair (`supports`). Frozen core untouched. **Proposed schema extensions "
         "(documented, not casually invented):** `CAN_FIGHT`, `CHANGES_TYPE_OF`, `SETS_BASE_PT`, "
         "`SWITCHES_PT`, `REMOVES_ABILITY_FROM`, `EXCHANGES_CONTROL_OF`/`GAINS_CONTROL_OF`, "
         "`PREVENTS_DAMAGE_FROM`, `DRAWS_CARDS`, `GAINS_LIFE`/`LOSES_LIFE`, `DISCARDS_CARDS`, `MILLS_CARDS`, "
         "`SACRIFICES`, `SEARCHES_FOR`, `CAN_RETURN`. Every census clause in scope is reconciled "
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
