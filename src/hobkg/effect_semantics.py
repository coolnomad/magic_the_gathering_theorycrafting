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
    kind, branches = _modes(text)
    out = []
    idx = 0
    for br in branches:
        for sentence in br["text"].split("."):
            m = _DESTROY_RE.search(sentence)
            if not m:
                continue
            qty, excl, qword, phrase = m.group(1), m.group(2), (m.group(3) or "").lower(), m.group(4).strip()
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
            rec = {"effect_id": f"{face['id']}#DESTROY#{idx}", "op": "DESTROY", "relation": "CAN_DESTROY",
                   "participant": _sch.participant(sentence), "selector": sel,
                   "mode": {"kind": kind, "index": br["index"]},
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
#  Phase 3 — the other targeted-object families, with same-object variable binding #
# --------------------------------------------------------------------------- #
_ABIL_KW = ["flying", "trample", "vigilance", "lifelink", "deathtouch", "menace", "reach", "haste",
            "hexproof", "indestructible", "first strike", "double strike", "ward", "protection",
            "prowess", "defender", "shroud"]
_TARGET_RE = re.compile(r"((?:up to \w+ |one or two |another |other |each |all )?)target\s+", re.I)
_TDELIM = re.compile(r"\.|,|;|\bgets?\b|\bgains?\b|\bfights?\b|\bbecomes?\b|\band\b|\bif\b|\bthen\b|"
                     r"\buntil\b|\bto\b|\bequal\b|$", re.I)
_PRON = re.compile(r"\b(it|that creature|that permanent|those|them)\b", re.I)


def _abilities(phrase: str):
    low = phrase.lower()
    return sorted({k for k in _ABIL_KW if re.search(r"\b" + re.escape(k) + r"\b", low)})


def _targets_in(clause: str):
    """Every 'target <selector>' in a clause, assigned stable vars obj0, obj1, … (in text order)."""
    out = []
    for m in _TARGET_RE.finditer(clause):
        qtext = m.group(1).lower()
        rest = clause[m.end():]
        d = _TDELIM.search(rest)
        phrase = (rest[:d.start()] if d else rest).strip()
        if not phrase:
            continue
        quant = "up_to_2" if "one or two" in qtext else "target"
        um = re.search(r"up to (\w+)", qtext)
        if um:
            quant = f"up_to_{_sch._NUM.get(um.group(1), um.group(1))}"
        sel = _sch.selector(phrase, var=f"obj{len(out)}", targeted=True, quantifier=quant)
        for w in ("other", "another"):
            if w in qtext:
                sel["exclusions"] = sorted(set(sel["exclusions"]) | {w})
        out.append({"var": sel["var"], "start": m.start(), "selector": sel})
    return out


def _before(targets, pos):
    cand = [t for t in targets if t["start"] <= pos]
    return cand[-1] if cand else (targets[0] if targets else None)


def _after(targets, pos):
    cand = [t for t in targets if t["start"] >= pos]
    return cand[0] if cand else None


# per-op: (relation, regex, object side 'before'|'after', extractor(match)->payload)
def _object_effects(face: dict):
    """Structured object-operation effects per (ability, mode) clause, binding operations that act on
    the SAME object to one object variable (Warg mode-1 counter+grant; Reverent Howl pump+grant), and
    distinct objects to distinct vars (Troll Negotiations counter on obj0, fight obj1)."""
    text = _blank_reminders(face.get("oracle_text") or "")
    kind, branches = _modes(text)
    short = face["name"].split(",")[0].lower()
    out = []
    for br in branches:
        clause = br["text"]
        cbase = text.find(clause) if clause in text else 0
        targets = _targets_in(clause)
        clause_id = f"{face['id']}#a?.m{br['index']}" if kind else f"{face['id']}#a?"
        ops = []

        def emit(relation, op, obj, extra, span):
            if not obj:
                return
            ops.append({"op": op, "relation": relation, "object_var": obj["var"],
                        "selector": obj["selector"], "span": [cbase + span[0], cbase + span[1]], **extra})

        for m in re.finditer(r"deals?\s+(\d+|x)\s+damage\s+to\b", clause, re.I):
            emit("CAN_DEAL_DAMAGE_TO", "DEAL_DAMAGE", _after(targets, m.end()),
                 {"amount": m.group(1).lower(), "source_var": "self"}, m.span())
        # source-power damage: "<your creature> deals damage equal to its power to <target>" (Quarrel)
        for m in re.finditer(r"deals?\s+damage\s+(equal to its power\s+)?to\b", clause, re.I):
            subj, obj = _before(targets, m.start()), _after(targets, m.end())
            if subj and obj and subj["var"] != obj["var"]:
                ops.append({"op": "DEAL_DAMAGE", "relation": "CAN_DEAL_DAMAGE_TO", "object_var": obj["var"],
                            "selector": obj["selector"], "source_var": subj["var"],
                            "source_selector": subj["selector"],
                            "amount": "equal_to_source_power" if m.group(1) else "unspecified",
                            "span": [cbase + m.start(), cbase + m.end()]})
        for m in re.finditer(r"put\s+(\w+)\s+(\+1/\+1|\-1/\-1|[a-z]+)\s+counters?\s+on\b", clause, re.I):
            w = m.group(1).lower()
            n = 1 if w in ("a", "an") else _sch._NUM.get(w, w)
            emit("ADDS_COUNTER_TO", "ADD_COUNTER", _after(targets, m.end()),
                 {"n": n, "counter": m.group(2)}, m.span())
        for m in re.finditer(r"gets?\s+([+\-][\dXx]+/[+\-][\dXx]+)", clause, re.I):
            emit("MODIFIES_POWER_TOUGHNESS", "MODIFY_PT", _before(targets, m.start()),
                 {"pt_mod": m.group(1)}, m.span())
        for m in re.finditer(r"gains?\s+([A-Za-z][A-Za-z ,]*?(?:and [A-Za-z ]+)?)(?=\s+until|\.|,|;|$)", clause, re.I):
            abils = _abilities(m.group(1))
            if abils:
                emit("GRANTS_ABILITY_TO", "GRANT_ABILITY", _before(targets, m.start()), {"abilities": abils}, m.span())
        for m in re.finditer(r"\b(taps?|untaps?)\b", clause, re.I):
            rel = "CAN_UNTAP" if m.group(1).lower().startswith("untap") else "CAN_TAP"
            emit(rel, m.group(1).upper().rstrip("S"), _after(targets, m.end()), {}, m.span())
        for m in re.finditer(r"\bfights?\b", clause, re.I):
            subj, obj = _before(targets, m.start()), _after(targets, m.end())
            if subj and obj:
                ops.append({"op": "FIGHT", "relation": "CAN_FIGHT", "object_var": subj["var"],
                            "selector": subj["selector"], "fight_target_var": obj["var"],
                            "fight_target_selector": obj["selector"], "span": [cbase + m.start(), cbase + m.end()]})
        for m in re.finditer(r"becomes?\s+(?:a|an)\s+(\w+)\b", clause, re.I):
            typ = m.group(1).lower()
            if typ in _sch.PERMANENT_TYPES:
                emit("CHANGES_TYPE_OF", "CHANGE_TYPE", _before(targets, m.start()),
                     {"added_type": typ, "in_addition": "in addition" in clause.lower()}, m.span())

        # a same-object replacement bound to a damaged target (Pinecone: 'If that creature would die … exile it instead')
        repl = re.search(r"if (?:that creature|it) would die[^.]*?exile it instead", clause, re.I)
        for op in ops:
            if op["op"] == "DEAL_DAMAGE" and repl:
                op["replacement"] = {"kind": "die_would_exile_instead", "object_var": op["object_var"]}
        # a spell-level cost reduction conditioned on the target (Magnificent End: '… less to cast if it
        # targets a tapped creature') — attach to the targeted object effect
        cm = re.search(r"costs? (\{[^}]+\}) less to cast if it targets a (\w+) creature", text, re.I)
        for op in ops:
            if cm and op["selector"]["targeted"]:
                op["cost_modification"] = {"amount": cm.group(1),
                                           "condition": {"kind": "conditional_cost",
                                                         "predicate": f"target_is_{cm.group(2).lower()}"}}

        for i, op in enumerate(ops):
            sub = op.pop("span")
            rec = {"effect_id": f"{face['id']}#{op['op']}#{br['index']}#{i}", "op": op["op"],
                   "relation": op["relation"], "participant": "you", "selector": op["selector"],
                   "object_var": op["object_var"], "mode": {"kind": kind, "index": br["index"]},
                   "condition": _sch.condition(clause), "duration": _sch.duration(clause),
                   "optional": "may " in clause.lower(),
                   "targeted": op["selector"]["targeted"], "affects_each": op["selector"]["affects_each"],
                   "binding": None, "clause_id": clause_id, "oracle_span": sub,
                   **{k: v for k, v in op.items() if k not in ("op", "relation", "object_var", "selector")}}
            out.append(rec)
    return out


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

    def project(src, sel, relation, family, support):
        for tgt in cards:
            if any(_sch.matches_card(sel, cf) for cf in by_card[tgt]):
                key = (src, tgt, relation)
                if key not in agg:                          # unique pair, AGGREGATE all supporting effects/modes
                    agg[key] = {"source_card": src, "target_card": tgt, "relation": relation,
                                "self_pair": src == tgt, "generic": True, "origin": "effect_semantics",
                                "family": family, "supports": []}
                agg[key]["supports"].append(support)

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
    L = ["# Effect-semantics — structured effects (Phase 3: targeted-object families)", "",
         "Additive `effect_semantics` layer over the frozen reference. Families: destruction, damage, "
         "counters, power/toughness, ability grants, tap/untap, fight, and type-change. Each effect is "
         "a validated record (selector + participant + mode + condition + duration + targeting/"
         "quantifier + **same-object variable binding** + Oracle-span provenance); deterministic "
         "projection fans each targeted effect to every eligible card, **aggregating all supporting "
         "effects/modes per pair** (`supports`). Frozen core untouched. Two predicates are proposed "
         "schema extensions (documented): `CAN_FIGHT`, `CHANGES_TYPE_OF`.", "",
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
