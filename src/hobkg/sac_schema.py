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
    if qty is None and is_self:                             # a named/self sacrifice is exactly one object
        qty = 1
    return {"card_types": types, "or_types": or_types, "supertypes": supertypes, "qualifiers": quals,
            "self": is_self, "another": another, "generic_permanent": generic, "quantity": qty}


def _ability_context(oracle: str, clause: str) -> str:
    end = oracle.find(clause) + len(clause) if clause in oracle else len(oracle)
    prefix = oracle[:end].lower()
    if "as an additional cost to cast" in prefix:
        return "cast"
    if re.search(r"\bkicker\b", prefix):
        return "cast"
    trig = None                                             # bind to the LAST trigger governing the clause
    for m in re.finditer(r"\b(when|whenever)\b[^.]*?\b(enters|attacks|dies)\b", prefix):
        trig = m.group(2)
    if trig == "enters":
        return "triggered_etb"
    if trig == "attacks":
        return "triggered_attack"
    if trig == "dies":
        return "triggered_other"
    if ":" in clause or re.search(r"\{[^}]+\}\s*,", clause):
        return "activated"
    if re.search(r"\bwhen(ever)?\b", prefix):
        return "triggered_other"
    return "resolution"


def _cost(clause: str, context: str) -> object:
    """Structured cost as ALT (choose one branch) of ALL (do every atom). None for non-cost outlets."""
    if context not in ("activated_ability", "additional_cast_cost", "kicker"):
        return None
    # the cost prefix = everything up to the first ':' (activated) or the whole clause (cast/kicker)
    prefix = clause.split(":")[0] if context == "activated_ability" else clause
    prefix = re.split(r"\bor pay\b", prefix, flags=re.IGNORECASE)[0]
    conj = []                                               # the ALL atoms of the sacrifice branch
    for mana in _MANA_RE.findall(prefix):
        conj.append({"tap": True} if mana == "{T}" else {"pay": mana})
    conj.append({"sacrifice": True})
    if re.search(r",\s*discard\b", prefix, re.IGNORECASE):
        conj.append({"discard": 1})
    branches = [{"all": conj}]
    om = _OR_PAY_RE.search(clause)                          # "... or pay {N}" -> a second ALT branch
    if om:
        branches.append({"all": [{"pay": om.group(1)}]})
    return {"alt": branches}


def parse_structured(oracle: str, card_name: str = "") -> dict | None:
    """Parse the (first) sacrifice outlet in `oracle` into a structured record, or None if there is
    no outlet. Unknowable fields are set to None / 'unsupported' — the parser never guesses a
    default (cf. the tracer-bullet-#1 review: `kind` must not fall back to activated_cost)."""
    text = oracle or ""
    for raw in [ln.strip() for ln in text.split("\n") if "sacrifice" in ln.lower()]:
        if _TRIGGER_SAC_RE.search(raw):                     # "Whenever you sacrifice ..." is a condition
            continue
        edict = _EDICT_RE.search(raw)
        mphrase = _SAC_PHRASE_RE.search(raw)
        if not mphrase:
            continue
        phrase = mphrase.group(1)
        low = raw.lower()
        sel = _selector(phrase, card_name)
        # an outlet must select a real object to sacrifice; a Saga "Sacrifice after IV" self-timer
        # selects nothing (no type / self / generic permanent) and is therefore NOT an outlet.
        if not (sel["card_types"] or sel["self"] or sel["generic_permanent"]):
            continue
        # actor
        if edict:
            actor = re.sub(r"\s+", "_", edict.group(1).lower())
        else:
            actor = "you"
        # cost_context (NEVER default to activated_cost)
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
        rec = {
            "is_outlet": True,
            "cost_context": context,
            "actor": actor,
            "ability_context": _ability_context(text, raw),
            "modal": modal,
            "selector": sel,
            "cost": _cost(raw, context),
            "restriction_timing": "sorcery" if "activate only as a sorcery" in low else None,
            "clause": raw,
            "oracle_span": _span(text, raw),
        }
        return rec
    return None


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
    if not cost:
        return None
    def atom(a):
        return sorted(f"{k}={v}" for k, v in a.items())
    return sorted(str(sorted([atom(a) for a in br.get("all", [])])) for br in cost.get("alt", []))


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
        if isinstance(e, list):
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
    L = ["# Portability tracer bullet #2 — structured sacrifice schema on real FIN Oracle text", "",
         "Validates the structured clause schema against small, **named, provenanced** samples of "
         "real *Final Fantasy* (FIN) cards (source: `data/raw/fin/scryfall_fin.json`; each carries "
         "its Scryfall `id`). Every card has a **manually-adjudicated** expected structured record "
         "(adjudicated to the rules, not to the parser); the parser output is scored **field by "
         "field** — a wrong or unsupported field fails.", "",
         "Two splits, to answer the tracer-bullet-#1 review directly:",
         f"- **DEV** (parser tuned on these): {dev['cards_fully_correct']}/{dev['cases']} cards, "
         f"{dev['field_accuracy']:.1%} fields.",
         f"- **HELD-OUT** (parser frozen, never tuned on these; scored once): "
         f"**{held['cards_fully_correct']}/{held['cases']} cards, {held['field_accuracy']:.1%} fields**. "
         "This is the honest portability number.", ""]
    L += _section("HELD-OUT split — the portability evidence (parser never tuned on these)",
                  "Real FIN cards chosen and adjudicated AFTER the parser was frozen. Misses are "
                  "reported as-is and become backlog; they are not fixed in this slice.", held)
    L += _section("DEV split — the tuning set (parser was iterated to pass these)",
                  "Full marks here only demonstrate the schema can *represent* these clauses; it is "
                  "train-set accuracy, not evidence of generalisation.", dev)
    L += ["## What the FIN run establishes (and does not)", "",
          "- **Establishes**: the structured schema (cost as `ALT`-of-`ALL`; selector-internal "
          "`or_types`; `actor`; `ability_context`; timing restriction) *represents* real FIN "
          "sacrifice clauses, and — the tracer-bullet-#1 review fix — the parser **flags** what it "
          "cannot model instead of silently mislabelling it (`cost_context` is never defaulted to "
          "activated; edicts are `resolution_effect` with an `actor`, not a cost).",
          "- **Held-out misses = the measured backlog** for the next slices: dual-trigger "
          "`ability_context` (\"enters or attacks\"), coalescing multi-symbol mana (`{1}{B}`) into "
          "one cost atom, and any others surfaced above — each now quantified against real "
          "adjudicated second-set text rather than invented cards.",
          "- The frozen HOB **data/graph layers are untouched**; this module is a read-only parser "
          "over `data/raw/fin/` and its own fixtures (shared loader `_load_dicts` is reused, not changed)."]
    (repo / "reports" / "sac_schema_portability.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"dev": {"cases": dev["cases"], "cards_fully_correct": dev["cards_fully_correct"],
                    "field_accuracy": dev["field_accuracy"]},
            "heldout": {"cases": held["cases"], "cards_fully_correct": held["cards_fully_correct"],
                        "field_accuracy": held["field_accuracy"], "fields_ok": held["fields_ok"],
                        "fields_total": held["fields_total"]}}
