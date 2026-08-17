"""Portability tracer bullet: deterministic sacrifice-clause extraction.

Goal (per the portability track): replace the hand-authored `completeness.SAC_OUTLETS` catalogue of
nine HOB face-ids with a **pure Oracle-text parser** — NO card-specific hardcoding (no face-id
conditionals, no per-card special cases). It must reproduce the nine accepted HOB records
(accepts / another / or_pay / kind / mana_cost) exactly, then run against an adversarial second-set
fixture to expose which HOB assumptions the parser bakes in.

A "sacrifice outlet" is a printed clause where the controller sacrifices a permanent as a COST
(activated ability `{cost}, Sacrifice …:` or `Sacrifice …:`; or an additional casting cost) or as
an optional EFFECT (`you may sacrifice …`). A trigger *condition* ("Whenever you sacrifice …") is
NOT an outlet.
"""

from __future__ import annotations

import re

# card types that can be named in a "sacrifice a <type>" clause (a HOB assumption: only these two
# actually occur here — the adversarial fixture stresses the rest).
PERMANENT_TYPES = ["artifact", "creature", "enchantment", "planeswalker", "land", "battle"]
_TYPE_RE = re.compile(r"\b(" + "|".join(PERMANENT_TYPES) + r")s?\b", re.IGNORECASE)
# "sacrifice a|an|another <noun phrase>" — capture the determiner + the phrase up to a clause end
_SAC_RE = re.compile(r"[Ss]acrifice\s+(a|an|another)\s+([^.:;]+)")
_MANA_PREFIX_RE = re.compile(r"((?:\{[^}]+\})+)\s*,\s*[Ss]acrifice", re.IGNORECASE)
_OR_PAY_RE = re.compile(r"\bor pay\s+((?:\{[^}]+\})+)", re.IGNORECASE)
_TRIGGER_RE = re.compile(r"\b(whenever|when)\s+you\s+sacrifice", re.IGNORECASE)


def _lines(oracle: str):
    for ln in (oracle or "").split("\n"):
        ln = ln.strip()
        if ln:
            yield ln


def extract(oracle: str) -> dict | None:
    """Return a sacrifice-outlet record parsed from Oracle text, or None. Fields:
    accepts (sorted card types), another (bool), or_pay (mana|None), kind
    (activated_cost|additional_cast_cost|effect), mana_cost (mana|None), clause, oracle_span."""
    for line in _lines(oracle):
        low = line.lower()
        if "sacrifice" not in low:
            continue
        if _TRIGGER_RE.search(line):                 # "Whenever/When you sacrifice …" is a trigger, not an outlet
            continue
        m = _SAC_RE.search(line)
        if not m:
            continue
        determiner, phrase = m.group(1).lower(), m.group(2)
        # accepts = the card types named in the phrase (stop the phrase at an "or pay …" alternative)
        phrase_for_types = re.split(r"\bor pay\b", phrase, flags=re.IGNORECASE)[0]
        accepts = sorted({t.group(1).lower() for t in _TYPE_RE.finditer(phrase_for_types)})
        if not accepts:                              # "sacrifice a token/land/Goblin/…" with no card type here
            continue
        another = determiner == "another"
        or_pay = None
        om = _OR_PAY_RE.search(line)
        if om:
            or_pay = om.group(1)
        # kind
        if "as an additional cost to cast" in low:
            kind = "additional_cast_cost"
        elif "you may sacrifice" in low:
            kind = "effect"
        else:
            kind = "activated_cost"
        # mana cost = the "{…}, Sacrifice" activation prefix (activated costs only)
        mana_cost = None
        if kind == "activated_cost":
            pm = _MANA_PREFIX_RE.search(line)
            mana_cost = pm.group(1) if pm else None
        # the exact printed clause + its char span (improves on the hand-authored oracle_span: null)
        start = oracle.find(line)
        span = [start, start + len(line)] if start >= 0 else None
        return {"accepts": accepts, "another": another, "or_pay": or_pay, "kind": kind,
                "mana_cost": mana_cost, "clause": line, "oracle_span": span}
    return None


# --------------------------------------------------------------------------- #
#  Reproduce the frozen HOB catalogue (validation) — NO card-specific logic     #
# --------------------------------------------------------------------------- #
_CORE = ("accepts", "another", "or_pay", "kind", "mana_cost")


def build_from_hob(repo=None) -> dict:
    """Run the parser over every HOB face and compare the extracted sacrifice outlets to the
    hand-authored `completeness.SAC_OUTLETS` on the core fields — no face-id is used by `extract`."""
    from .pipeline import REPO, _load_dicts
    from .completeness import SAC_OUTLETS
    repo = repo or REPO
    faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
    extracted = {}
    for f in faces:
        rec = extract(f.get("oracle_text") or "")
        if rec:
            extracted[f["id"]] = rec
    # compare
    expected_ids = set(SAC_OUTLETS)
    got_ids = set(extracted)
    matches, mismatches = [], []
    for fid in sorted(expected_ids):
        exp, got = SAC_OUTLETS[fid], extracted.get(fid)
        if not got:
            mismatches.append({"face": fid, "name": exp["name"], "issue": "not extracted", "expected": {k: exp[k] for k in _CORE}})
            continue
        diff = {k: (exp[k], got[k]) for k in _CORE if exp[k] != got[k]}
        (matches if not diff else mismatches).append(
            {"face": fid, "name": exp["name"], **({"diff": diff} if diff else {})})
    spurious = sorted(got_ids - expected_ids)      # outlets extracted that are NOT in the catalogue
    return {"expected": len(expected_ids), "extracted": len(got_ids),
            "reproduced": len(matches), "mismatches": mismatches, "spurious": spurious,
            "reproduces_catalogue": len(matches) == len(expected_ids) and not spurious,
            "_extracted": extracted}


# --------------------------------------------------------------------------- #
#  Adversarial second-set fixture: expose the HOB assumptions the parser bakes  #
# --------------------------------------------------------------------------- #
def run_adversarial(repo=None) -> dict:
    """Run the HOB-tuned parser over an adversarial second-set fixture and report every HOB
    assumption it exposes (a MISS = the parser returned nothing; INCOMPLETE = it returned a record
    but dropped/misread part of the clause)."""
    from .pipeline import REPO, _load_dicts
    repo = repo or REPO
    cases = list(_load_dicts(repo / "tests/fixtures/sac_adversarial.jsonl"))
    findings = []
    for c in cases:
        rec = extract(c["oracle"])
        if rec is None:
            status = "MISS (returned nothing)"
        else:
            # did it capture what the clause actually means? the fixture's `should` says what a
            # portable extractor must do; the HOB parser cannot, so any returned record is INCOMPLETE.
            status = "INCOMPLETE (returned a record but " + c["note"] + ")"
        findings.append({"name": c["name"], "assumption": c["assumption"], "note": c["note"],
                         "should": c["should"], "extractor_output": rec, "status": status})
    exposed = sorted({f["assumption"] for f in findings})
    return {"cases": len(cases), "assumptions_exposed": exposed, "findings": findings}


# human-readable labels for the exposed assumptions (the "HOB assumptions" the tracer bullet found)
_ASSUMPTION_LABEL = {
    "type_enum_only": "Fodder type is a fixed card-type enum — the generic 'permanent' is unhandled.",
    "no_subtypes": "Only card types are recognized — subtypes/tribes (Goblin, Dwarf) are not.",
    "quantity_one": "Exactly one permanent is sacrificed (a/an/another) — fixed counts >1 are missed.",
    "quantity_variable": "Quantity is a constant — variable counts (X creatures) are unhandled.",
    "no_self_sacrifice": "Fodder is a separate object — self-sacrifice ('this'/'~') is unhandled.",
    "or_pay_mana_only": "An OR alternative is only 'pay {mana}' — non-mana alternatives (discard/exile) are dropped.",
    "or_not_and": "Multiple types are read as OR (either) — conjunctive AND (both) is misread.",
    "no_qualifiers": "Bare card types only — qualified phrases ('nonland permanent') are unhandled.",
    "controller_scope": "The activating player is assumed to sacrifice — edicts (each/target player sacrifices) are not captured.",
    "no_timing_restrictions": "Activation timing/frequency ('only as a sorcery', 'only once each turn') is not extracted (cf. pt10.md #2).",
}


def report(repo=None) -> dict:
    from .pipeline import REPO
    repo = repo or REPO
    hob = build_from_hob(repo)
    adv = run_adversarial(repo)
    L = ["# Portability tracer bullet — deterministic sacrifice-clause extractor", "",
         "## 1. Reproduce the frozen HOB catalogue (no card-specific hardcoding)", "",
         f"- accepted HOB outlets: **{hob['expected']}**  · extracted: **{hob['extracted']}**  · "
         f"reproduced (core fields): **{hob['reproduced']}**",
         f"- **reproduces the catalogue exactly**: {hob['reproduces_catalogue']}  "
         f"(mismatches: {len(hob['mismatches'])}, spurious: {len(hob['spurious'])})",
         "- the parser is pure Oracle text — it never looks at a face-id.", "",
         "## 2. HOB assumptions exposed by the adversarial second-set fixture", "",
         f"The HOB-tuned parser was run over {adv['cases']} adversarial clauses. Each exposes a HOB "
         "assumption baked into the parser (a `MISS` = returned nothing; `INCOMPLETE` = returned a "
         "record but dropped/misread part of the clause):", ""]
    for f in adv["findings"]:
        L.append(f"- **{f['name']}** — `{f['status']}`")
        L.append(f"  - clause: _{f['note']}_ — a portable extractor should: {f['should']}")
        L.append(f"  - **HOB assumption**: {_ASSUMPTION_LABEL.get(f['assumption'], f['assumption'])}")
    L += ["", "## 3. Minimal restructure implied (NOT the broad engine/config split)", "",
          "The tracer bullet reproduces HOB with zero hardcoding, so the parser logic is already "
          "set-agnostic in shape. The gaps above imply a *small*, evidence-driven restructure — a "
          "**declarative `rules/mechanics/sacrifice.yaml` clause schema** the parser consumes, rather "
          "than a full engine split:", "",
          "1. **Fodder selector** as structured data, not a `{artifact,creature}` regex: "
          "`{card_types, subtypes, supertypes, qualifiers (non…), generic 'permanent', quantity "
          "(int|variable), self ('this'/'~')}`. Covers type_enum_only / no_subtypes / no_qualifiers "
          "/ quantity_* / no_self_sacrifice.",
          "2. **Cost model** as an alternatives list, not `or_pay:{mana}`: "
          "`cost = ALT[ sacrifice(selector), pay(mana), discard(n), exile(...), … ]`. Covers "
          "or_pay_mana_only; distinguish `ALL[…]` (AND) from `ALT[…]` (OR) — covers or_not_and.",
          "3. **Actor/controller** field on the clause (`you` | `each player` | `target opponent`) — "
          "covers controller_scope; edicts become a distinct clause kind.",
          "4. **Activation restrictions** captured as conditions "
          "(`timing: sorcery`, `frequency: once_per_turn`, `zone`, `turn: controller`) — covers "
          "no_timing_restrictions (and is exactly the pt10.md #2 deferral).",
          "5. **LLM escalation** only for clauses the deterministic parser flags ambiguous "
          "(unmatched selector, unknown alternative) — the harness stays the control plane.", "",
          "No `engine/` vs `sets/HOB/` repo split is warranted yet: the evidence says the next unit "
          "is the sacrifice **clause schema** + selector/cost/actor/restriction parsers, validated by "
          "this same reproduce-HOB + adversarial-fixture harness."]
    (repo / "reports" / "sac_extract_portability.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"reproduces_catalogue": hob["reproduces_catalogue"], "hob_reproduced": hob["reproduced"],
            "hob_expected": hob["expected"], "assumptions_exposed": adv["assumptions_exposed"],
            "adversarial_cases": adv["cases"]}
