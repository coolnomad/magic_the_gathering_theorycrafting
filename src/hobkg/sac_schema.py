"""Portability tracer bullet #2: a STRUCTURED sacrifice-clause schema, validated on real second-set
(FIN) Oracle text against manually-adjudicated expectations, scored field-by-field.

This directly answers the review of tracer bullet #1 (commit c67fcc5):

  * the flat `accepts:[...]` model is lossy — it cannot tell "sacrifice an artifact **or** a
    creature" from "sacrifice an artifact **and** a creature", and it silently drops non-mana cost
    components. Here the cost is a structured `ALT` (choose one) of `ALL` (do all) atoms, and the
    fodder `selector` carries its own `or_types` flag — the two OR/AND axes are separated.
  * `kind` defaulted to `activated_cost` for anything unrecognised. Here `cost_context` is only
    `activated_ability` when a colon-delimited activation is actually present; an edict inside an
    ETB trigger (`Each player sacrifices ...`) is `resolution_effect` with `actor: each_player`,
    never a cost.
  * the "adversarial" validation was tautological (it stamped INCOMPLETE without comparing to
    expected output). Here `score()` compares the parser's structured record to an adjudicated
    expected record FIELD BY FIELD; a wrong field fails. The FIN score is therefore genuine
    cross-set evidence — including the fields the parser still cannot handle (it flags them
    `unsupported` rather than guessing, and the scorer counts those as misses against the human
    adjudication).

A "sacrifice outlet" = a printed clause in which a player sacrifices a game object selected by a
fodder description (as a cost, as an optional effect, or as an edict). A Saga's "Sacrifice after N"
self-timer and a "Whenever you sacrifice ..." trigger are NOT outlets (`is_outlet: false`).
"""

from __future__ import annotations

import json
import re

PERMANENT_TYPES = ["artifact", "creature", "enchantment", "planeswalker", "land", "battle", "vehicle"]
_SUPERTYPES = ["legendary", "basic", "snow", "world"]
_NUMWORD = {"a": 1, "an": 1, "another": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

_TYPE_RE = re.compile(r"\b(" + "|".join(PERMANENT_TYPES) + r")s?\b", re.IGNORECASE)
_SUPER_RE = re.compile(r"\b(" + "|".join(_SUPERTYPES) + r")\b", re.IGNORECASE)
_QUALIFIER_RE = re.compile(r"\b(non-?[A-Za-z]+|token|tapped|attacking|nonland)\b")
# "<actor> sacrifice(s) <phrase>" — actor may be the imperative 'you'/absent (cost) or an edict target
_EDICT_RE = re.compile(
    r"\b(each player|each opponent|target opponent|target player|its controller|that player)\s+sacrifices\b",
    re.IGNORECASE)
_MAY_RE = re.compile(r"\byou may sacrifice\b", re.IGNORECASE)
_TRIGGER_SAC_RE = re.compile(r"\b(whenever|when)\s+(a\s+)?(you|player|another)\b[^.]*\bsacrifices?\b", re.IGNORECASE)
# the fodder phrase after an imperative/optional/edict 'sacrifice', stop at clause end
_SAC_PHRASE_RE = re.compile(r"[Ss]acrifices?\s+(.+?)(?:[.:;]|$)")
_MANA_RE = re.compile(r"(\{[^}]+\})")
_OR_PAY_RE = re.compile(r"\bor pay\s+((?:\{[^}]+\})+)", re.IGNORECASE)

SCORED_FIELDS = ("is_outlet", "cost_context", "actor", "ability_context", "modal",
                 "sel_card_types", "sel_or_types", "sel_supertypes", "sel_qualifiers",
                 "sel_self", "sel_another", "sel_quantity", "cost", "restriction_timing")


# --------------------------------------------------------------------------- #
#  Parser: Oracle text -> structured record (no card-id / per-card branches)     #
# --------------------------------------------------------------------------- #
def _quantity(phrase: str) -> object:
    low = phrase.lower().strip()
    if low.startswith("any number of"):
        return "any"
    if re.match(r"x\b", low):
        return "X"
    if re.search(r"\bhalf\b", low):
        return "half_rounded_down" if "rounded down" in low else ("half_rounded_up" if "rounded up" in low else "half")
    m = re.match(r"(a|an|another|one|two|three|four|five)\b", low)
    if m:
        return _NUMWORD[m.group(1)]
    return None                                             # could not determine -> unsupported


def _selector(phrase: str, card_name: str) -> dict:
    """Structured fodder selector from the noun phrase after 'sacrifice'."""
    p = re.split(r"\bor pay\b", phrase, flags=re.IGNORECASE)[0]          # drop the 'or pay {N}' alt
    low = p.lower()
    types = sorted({t.group(1).lower() for t in _TYPE_RE.finditer(p)})
    # selector-internal OR: "artifact or creature" (one object of either type)
    or_types = bool(re.search(r"\b" + _TYPE_RE.pattern + r"\s+or\s+" + _TYPE_RE.pattern + r"\b", p, re.IGNORECASE)) \
        and len(types) >= 2
    supertypes = sorted({s.group(1).lower() for s in _SUPER_RE.finditer(p)})
    quals = sorted({q.group(1).lower() for q in _QUALIFIER_RE.finditer(p) if q.group(1).lower() not in types})
    another = bool(re.search(r"\banother\b", low))
    short = card_name.split(",")[0].split(" //")[0].strip().lower()
    is_self = bool(re.search(r"\bthis (creature|permanent|artifact|enchantment|vehicle|token|aura)\b", low)) \
        or (short and short in low) or "~" in p
    generic = bool(re.search(r"\bpermanents?\b", low)) and not types
    qty = _quantity(p)
    if is_self:
        # a self-sacrifice targets THIS specific object; the type word in "this creature" is
        # incidental, not a selector constraint (cf. "Sacrifice <cardname>" naming no type at all).
        types, or_types = [], False
        if qty is None:
            qty = 1                                        # a named/self sacrifice is exactly one object
    return {"card_types": types, "or_types": or_types, "supertypes": supertypes, "qualifiers": quals,
            "self": is_self, "another": another, "generic_permanent": generic, "quantity": qty}


_TRIG_MAP = {"enters": "etb", "attacks": "attack", "dies": "dies"}


def _trig_kws(sentence: str):
    return [_TRIG_MAP[k] for k in ("enters", "attacks", "dies") if re.search(r"\b" + k + r"\b", sentence)]


def _ability_context(oracle: str, clause: str) -> str:
    """The context governing THIS clause. Scoped to the clause's own line (plus the modal intro line
    for a bulleted choice), so an unrelated trigger elsewhere on the card is not misattributed."""
    cl = clause.lower()
    if "as an additional cost to cast" in cl:
        return "cast"
    if re.match(r"\s*kicker\b", cl):
        return "cast"
    if re.search(r"\bwhen(ever)?\b", cl):                   # trigger on the clause's own line
        kws = _trig_kws(cl)                                 # one trigger may name several events
        return "triggered_" + "_or_".join(kws) if kws else "triggered_other"
    lines = oracle.split("\n")
    idx = next((i for i, ln in enumerate(lines) if clause in ln), None)
    if idx and "choose" in lines[idx - 1].lower() and re.search(r"\bwhen(ever)?\b", lines[idx - 1].lower()):
        kws = _trig_kws(lines[idx - 1].lower())             # modal edict: trigger is the intro line
        return "triggered_" + "_or_".join(kws) if kws else "triggered_other"
    if ":" in clause or re.search(r"\{[^}]+\}\s*,", clause):
        return "activated"
    return "resolution"


_BRACE_RUN_RE = re.compile(r"(?:\{[^}]+\})+")


def _cost(clause: str, context: str, selector: dict) -> object:
    """Structured cost as ALT (choose one branch) of ALL (do every atom). Each sacrifice atom carries
    its OWN selector, so 'sacrifice A and B' / branch-specific fodder are representable (review pt1
    #2). None for non-cost outlets."""
    if context not in ("activated_ability", "additional_cast_cost", "kicker"):
        return None
    prefix = clause.split(":")[0] if context == "activated_ability" else clause
    prefix = re.split(r"\bor pay\b", prefix, flags=re.IGNORECASE)[0]
    conj = []                                               # the ALL atoms of the sacrifice branch
    for tok in prefix.split(","):                           # comma-separated cost components
        run = "".join(_BRACE_RUN_RE.findall(tok))           # coalesce adjacent mana symbols: {1}{B} -> one
        if not run:
            continue
        if run == "{T}":
            conj.append({"tap": True})
        else:
            conj.append({"pay": run})
    conj.append({"sacrifice": _sel_sig(selector)})
    if re.search(r",\s*discard\b", prefix, re.IGNORECASE):
        conj.append({"discard": 1})
    branches = [{"all": conj}]
    om = _OR_PAY_RE.search(clause)                          # "... or pay {N}" -> a second ALT branch
    if om:
        branches.append({"all": [{"pay": om.group(1)}]})
    return {"alt": branches}


def _sel_sig(sel: dict) -> dict:
    """Compact, canonical selector signature carried on a sacrifice cost atom."""
    return {"card_types": sorted(sel.get("card_types") or []), "or_types": bool(sel.get("or_types")),
            "supertypes": sorted(sel.get("supertypes") or []), "qualifiers": sorted(sel.get("qualifiers") or []),
            "self": bool(sel.get("self")), "another": bool(sel.get("another")), "quantity": sel.get("quantity")}


def extract_all(oracle: str, card_name: str = "") -> list[dict]:
    """Return EVERY sacrifice outlet in `oracle` as a structured record (review pt1 #3: a face can
    carry several sacrifice clauses). Unknowable fields are None / 'unsupported' — the parser never
    guesses a default (`cost_context` is not forced to activated). Empty list = no outlet."""
    text = oracle or ""
    out = []
    for raw in [ln.strip() for ln in text.split("\n") if "sacrifice" in ln.lower()]:
        if _TRIGGER_SAC_RE.search(raw):                     # "Whenever you sacrifice ..." is a condition
            continue
        edict = _EDICT_RE.search(raw)
        mphrase = _SAC_PHRASE_RE.search(raw)
        if not mphrase:
            continue
        sel = _selector(mphrase.group(1), card_name)
        # an outlet must select a real object to sacrifice; a Saga "Sacrifice after IV" self-timer
        # selects nothing (no type / self / generic permanent) and is therefore NOT an outlet.
        if not (sel["card_types"] or sel["self"] or sel["generic_permanent"]):
            continue
        low = raw.lower()
        actor = re.sub(r"\s+", "_", edict.group(1).lower()) if edict else "you"
        if "as an additional cost to cast" in low:
            context = "additional_cast_cost"
        elif re.match(r"kicker\b", low):
            context = "kicker"
        elif edict:
            context = "resolution_effect"
        elif _MAY_RE.search(raw):
            context = "effect"
        elif ":" in raw and re.search(r"[Ss]acrifice[^:]*:", raw):   # a real colon-delimited activation
            context = "activated_ability"
        else:
            context = "unsupported"
        modal = bool(re.search(r"\bchoose (one|two)\b", text.lower())) and edict is not None
        out.append({
            "is_outlet": True,
            "cost_context": context,
            "actor": actor,
            "ability_context": _ability_context(text, raw),
            "modal": modal,
            "selector": sel,
            "cost": _cost(raw, context, sel),
            "restriction_timing": "sorcery" if "activate only as a sorcery" in low else None,
            "clause": raw,
            "oracle_span": _span(text, raw),
        })
    return out


def parse_structured(oracle: str, card_name: str = "") -> dict | None:
    """The FIRST sacrifice outlet (or None) — a convenience wrapper over extract_all()."""
    all_ = extract_all(oracle, card_name)
    return all_[0] if all_ else None


def _span(oracle: str, clause: str):
    i = oracle.find(clause)
    return [i, i + len(clause)] if i >= 0 else None


# --------------------------------------------------------------------------- #
#  Non-tautological scorer: structured expected vs structured got, field by field #
# --------------------------------------------------------------------------- #
def _flatten(rec: dict | None) -> dict:
    if rec is None:
        return {"is_outlet": False}
    s = rec.get("selector") or {}
    return {"is_outlet": rec.get("is_outlet", True), "cost_context": rec.get("cost_context"),
            "actor": rec.get("actor"), "ability_context": rec.get("ability_context"),
            "modal": rec.get("modal", False), "sel_card_types": sorted(s.get("card_types") or []),
            "sel_or_types": s.get("or_types", False), "sel_supertypes": sorted(s.get("supertypes") or []),
            "sel_qualifiers": sorted(s.get("qualifiers") or []), "sel_self": s.get("self", False),
            "sel_another": s.get("another", False), "sel_quantity": s.get("quantity"),
            "cost": _canon_cost(rec.get("cost")), "restriction_timing": rec.get("restriction_timing")}


def _canon_cost(cost) -> object:
    """Canonical, order-independent form of a structured cost (atoms may carry nested selectors)."""
    if not cost:
        return None
    return sorted(json.dumps(sorted(json.dumps(a, sort_keys=True) for a in br.get("all", [])))
                  for br in cost.get("alt", []))


def score(expected: dict, got: dict | None) -> dict:
    """Compare adjudicated `expected` (flat, using SCORED_FIELDS) to the parser output field by
    field. Returns {field: {expected, got, ok}} plus fields_ok / fields_total. NOT tautological:
    a wrong field fails; a field the parser flagged unsupported (None) fails against a real value."""
    gflat = _flatten(got)
    out = {}
    ok = 0
    for f in SCORED_FIELDS:
        if f not in expected:
            continue
        e, g = expected[f], gflat.get(f)
        if f == "cost":
            e = _canon_cost(e)                              # expected stores a raw cost dict; canonicalize both sides
        elif isinstance(e, list):
            e = sorted(e)
        good = (e == g)
        out[f] = {"expected": e, "got": g, "ok": good}
        ok += int(good)
    total = len(out)
    return {"fields": out, "fields_ok": ok, "fields_total": total}


# --------------------------------------------------------------------------- #
#  Run against the real FIN fixture and report                                  #
# --------------------------------------------------------------------------- #
def run_fin(repo=None, fixture="tests/fixtures/fin_sacrifice.jsonl") -> dict:
    from .pipeline import REPO, _load_dicts
    repo = repo or REPO
    cases = list(_load_dicts(repo / fixture))
    results = []
    tot_ok = tot = 0
    for c in cases:
        got = parse_structured(c["oracle_text"], c.get("name", ""))
        sc = score(c["expected"], got)
        tot_ok += sc["fields_ok"]
        tot += sc["fields_total"]
        results.append({"name": c["name"], "id": c["id"], "set": c.get("set", "fin"),
                        "collector_number": c.get("collector_number"), "got": got, "score": sc})
    perfect = sum(1 for r in results if r["score"]["fields_ok"] == r["score"]["fields_total"])
    return {"set": "fin", "cases": len(cases), "cards_fully_correct": perfect,
            "fields_ok": tot_ok, "fields_total": tot,
            "field_accuracy": round(tot_ok / tot, 4) if tot else 0.0, "results": results}


def _clause_exact(expected_clause: dict, got_clause: dict | None) -> bool:
    sc = score(expected_clause, got_clause)
    return sc["fields_ok"] == sc["fields_total"] and sc["fields_total"] > 0


def run_setwide(repo=None, fixture="tests/fixtures/fin_sacrifice_setwide.jsonl") -> dict:
    """Set-wide evaluation over EVERY adjudicated FIN face containing 'sacrif' (review pt1 #1). Reports
    face-level detection precision/recall (outlet vs non-outlet), clause-level exact match (the
    PRIMARY metric — review pt1 metric note), and per-field micro accuracy (secondary/diagnostic).
    The parser is frozen; this fixture is adjudicated separately. Returns {available: False} until the
    fixture exists (so the parser can be committed and frozen BEFORE the unseen fixture is added)."""
    from .pipeline import REPO, _load_dicts
    repo = repo or REPO
    path = repo / fixture
    if not path.exists():
        return {"available": False}
    cases = list(_load_dicts(path))
    tp = fp = fn = tn = 0
    clause_exact = clause_total = 0
    field_ok = field_tot = 0
    fp_faces, fn_faces, imperfect = [], [], []
    for c in cases:
        exp_clauses = (c["expected"].get("clauses") or [])
        got = sorted(extract_all(c["oracle_text"], c.get("name", "")),
                     key=lambda r: (r.get("oracle_span") or [0])[0])
        exp_pos, got_pos = bool(exp_clauses), bool(got)
        tp += exp_pos and got_pos
        fp += (not exp_pos) and got_pos
        fn += exp_pos and (not got_pos)
        tn += (not exp_pos) and (not got_pos)
        if got_pos and not exp_pos:
            fp_faces.append(c["name"])
        if exp_pos and not got_pos:
            fn_faces.append(c["name"])
        clause_total += len(exp_clauses)
        face_perfect = (exp_pos == got_pos)
        for i, ec in enumerate(exp_clauses):                # align by text order (near-all faces = 1 clause)
            gc = got[i] if i < len(got) else None
            ok = _clause_exact(ec, gc)
            clause_exact += int(ok)
            sc = score(ec, gc)
            field_ok += sc["fields_ok"]
            field_tot += sc["fields_total"]
            face_perfect = face_perfect and ok
        if not face_perfect:
            imperfect.append(c["name"])
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return {"available": True, "faces": len(cases), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 4), "recall": round(rec, 4),
            "clause_exact": clause_exact, "clause_total": clause_total,
            "clause_exact_rate": round(clause_exact / clause_total, 4) if clause_total else 0.0,
            "field_ok": field_ok, "field_total": field_tot,
            "field_accuracy": round(field_ok / field_tot, 4) if field_tot else 0.0,
            "fp_faces": fp_faces, "fn_faces": fn_faces, "imperfect": imperfect}


def _section(title, note, fin):
    L = [f"## {title}", "", note, "",
         f"- cards: **{fin['cases']}**  · fully-correct (all fields): **{fin['cards_fully_correct']}**",
         f"- field accuracy: **{fin['fields_ok']}/{fin['fields_total']} = {fin['field_accuracy']:.1%}**", ""]
    for r in fin["results"]:
        sc = r["score"]
        misses = [f for f, v in sc["fields"].items() if not v["ok"]]
        L.append(f"### {r['name']}  ·  FIN #{r['collector_number']}  ·  `{r['id']}`")
        L.append(f"- score: **{sc['fields_ok']}/{sc['fields_total']}**"
                 + ("  — all fields correct" if not misses else ""))
        for f in misses:
            v = sc["fields"][f]
            L.append(f"  - **{f}**: expected `{v['expected']}` · parser `{v['got']}`")
        L.append("")
    return L


def report(repo=None) -> dict:
    from .pipeline import REPO
    repo = repo or REPO
    dev = run_fin(repo, "tests/fixtures/fin_sacrifice.jsonl")
    held = run_fin(repo, "tests/fixtures/fin_sacrifice_heldout.jsonl")
    sw = run_setwide(repo)
    L = ["# Portability tracer bullet #2 — structured sacrifice schema on real FIN Oracle text", "",
         "Structured sacrifice-clause schema + parser + a non-tautological field-by-field scorer, "
         "validated on **real, source-provenanced** *Final Fantasy* (FIN) Oracle text "
         "(`data/raw/fin/scryfall_fin.json`; every fixture record carries its Scryfall `id` and its "
         "text is byte-identical to source). Expected structures are adjudicated **to the rules, not "
         "to the parser** — and are **agent-authored reference annotations, NOT an independent human "
         "gold set** (review pt1 #5).", ""]
    if sw.get("available"):
        L += ["## PRIMARY — set-wide FIN evaluation (every face containing “sacrif”)", "",
              "Detection is over ALL adjudicated FIN faces; clause-level exact match is the primary "
              "quality metric (per-field micro accuracy is secondary — it is inflated by easy default "
              "fields such as `modal=False` / empty lists / `restriction_timing=None`).", "",
              f"- faces adjudicated: **{sw['faces']}**  (TP {sw['tp']} · FP {sw['fp']} · FN {sw['fn']} · TN {sw['tn']})",
              f"- **detection precision {sw['precision']:.1%} · recall {sw['recall']:.1%}** (outlet vs non-outlet)",
              f"- **clause-level exact match: {sw['clause_exact']}/{sw['clause_total']} = "
              f"{sw['clause_exact_rate']:.1%}**  ← primary",
              f"- per-field micro accuracy: {sw['field_ok']}/{sw['field_total']} = {sw['field_accuracy']:.1%} "
              "(secondary/diagnostic)"]
        if sw["fp_faces"]:
            L.append(f"- false-positive faces (parser saw an outlet, adjudication did not): {sw['fp_faces']}")
        if sw["fn_faces"]:
            L.append(f"- false-negative faces (adjudicated outlet the parser missed): {sw['fn_faces']}")
        if sw["imperfect"]:
            L.append(f"- faces with any clause/field error: {sw['imperfect']}")
        L.append("")
    else:
        L += ["## PRIMARY — set-wide FIN evaluation", "",
              "_Pending: the set-wide adjudicated fixture is added in the FOLLOWING commit, so this "
              "parser can be committed and **frozen first** (review pt1 #4 — independent auditability). "
              "Run `sac-schema` again once `tests/fixtures/fin_sacrifice_setwide.jsonl` exists._", ""]
    L += ["## Regression sets (parser tuned/known — not fresh evidence)", "",
          f"- DEV (11 curated, parser tuned to these): {dev['cards_fully_correct']}/{dev['cases']} "
          f"cards exact, {dev['field_accuracy']:.1%} fields.",
          f"- HELD-OUT (the original 6 pt#2 cases, now with the three known parser errors fixed): "
          f"{held['cards_fully_correct']}/{held['cases']} cards exact, {held['field_accuracy']:.1%} fields. "
          "These previously exposed self-`this creature` type-leak, dual `enters or attacks` trigger, "
          "and multi-symbol mana `{1}{B}` — all now fixed and kept as regression fixtures.", ""]
    L += _section("HELD-OUT regression detail", "The six pt#2 held-out cards (unchanged text).", held)
    L += ["## What this establishes (and does not)", "",
          "- The structured schema (cost = `ALT`-of-`ALL` with a **selector on each sacrifice atom**; "
          "selector-internal `or_types`; `actor`; `ability_context` incl. dual triggers; timing "
          "restriction) represents real FIN sacrifice clauses; `extract_all()` returns EVERY clause "
          "on a face; the parser flags what it cannot model rather than mislabelling it.",
          "- It does **not** yet establish a complete portable extractor: the set-wide false "
          "positives / false negatives / imperfect faces above are the measured backlog.",
          "- These are agent-authored reference annotations, not independent human semantic "
          "validation. The frozen HOB **data/graph layers are untouched** (read-only parser)."]
    (repo / "reports" / "sac_schema_portability.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"setwide": sw,
            "dev": {"cases": dev["cases"], "cards_fully_correct": dev["cards_fully_correct"],
                    "field_accuracy": dev["field_accuracy"]},
            "heldout": {"cases": held["cases"], "cards_fully_correct": held["cards_fully_correct"],
                        "field_accuracy": held["field_accuracy"]}}
