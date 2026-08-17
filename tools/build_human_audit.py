"""Build the human HOB audit packet from the frozen gold set.

The five adversarial sub-agent pass (reports/manual_gold_set_review.md) is explicitly NOT a
substitute for an external human's final adjudication. This generates that human artifact: every
gold-set item rendered against its PRINTED Oracle text + a plain-English statement of the graph's
claim + the relevant CR reference + provenance, with a verdict field for the human (the user) to
fill. Deterministic; reads only frozen inputs.

Outputs:
  reports/human_audit_worksheet.md      — the human-readable worksheet (fill in verdicts here)
  data/review/human_audit_items.jsonl   — one structured row per item (for recording verdicts later)
"""
import io
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VSET = REPO / "data/graph_global/structural_validation_set.jsonl"
FACES = REPO / "data/normalized/faces.jsonl"
OUT_MD = REPO / "reports/human_audit_worksheet.md"
OUT_JSONL = REPO / "data/review/human_audit_items.jsonl"

# plain-English gloss (oriented SOURCE → TARGET, matching the stored edge direction) + CR anchor
REL = {
    "CAN_ATTACH_TO": ("the source Equipment can legally attach to the target permanent.", "CR 301.5, 701.3"),
    "MODIFIES_WHEN_ATTACHED": ("while attached, the source Equipment modifies the target's P/T or characteristics.",
                               "CR 301.5c"),
    "GRANTS_ABILITY_WHEN_ATTACHED": ("while attached, the source Equipment grants the target an ability/keyword.",
                                     "CR 301.5c"),
    "SACRIFICE_TERMINATES_ATTACHMENT": ("sacrificing the source (the host creature) ends the target Equipment's "
                                        "attachment.", "CR 701.21, 704.5q"),
    "CONTRIBUTES_TO_GATE": ("the source permanent counts toward a threshold the target's ability defines (e.g. the "
                            "target's Storied).", "HOB Storied; CR 607"),
    "ENABLES_TRIGGER": ("the source's effect can satisfy the condition that triggers the target's ability.", "CR 603"),
    "INFRASTRUCTURE_CASTING": ("the source supplies casting infrastructure (mana / cost reduction) the target spell "
                               "can use.", "CR 601, 118"),
    "IS_ELIGIBLE_SACRIFICE_TARGET": ("the source is a legal object that the target's sacrifice cost/effect could "
                                     "sacrifice.", "CR 701.21"),
    "SATISFIES_SACRIFICE_COST": ("the source can be sacrificed to pay the target's sacrifice cost.", "CR 118, 701.21"),
    "SUPPLIES_RESOURCE": ("the source supplies a resource (mana / token / counter / a triggering entry) the target "
                          "uses.", "CR 106/107/122"),
}
_LAYERS = ("mechanical", "audited", "repaired", "mechanism", "equip", "completeness", "lifecycle")

STRATUM = {
    "adventures": ("Modeled as exactly two distinct faces — the creature/permanent AND its Adventure spell.",
                   "CR 715 (Adventurer cards)"),
    "recruit": ("This card's ability instantiates the HOB Recruit keyword-action.", "HOB set mechanic: Recruit"),
    "replacement_effects": ("This card sets up a replacement effect ('… would … instead').", "CR 614/616"),
    "sagas": ("Modeled as a Saga: add lore counters, chapter abilities fire in order, sacrifice after the "
              "final chapter.", "CR 714 (Sagas)"),
    "storied": ("This permanent counts toward the Storied threshold (an artifact, a legendary permanent, "
                "or a Saga).", "HOB set mechanic: Storied"),
    "self_pairs": ("A genuine self-referential effect (the card affects itself), NOT an 'another/other' "
                   "exclusion.", "CR 109.5 / 'another'"),
    "multi_token_or_type": ("This card creates two or more DISTINCT token types.", "CR 111 (tokens)"),
    "null_pairs": ("These two cards have NO mechanical relationship in any projection layer — verify it is "
                   "truly null, not a missed relation.", "n/a (completeness check)"),
    "multi_edge_pairs": ("These two cards are related by ALL of the listed relations, each in the stated "
                         "direction.", None),
}

def _flag_for(stratum, names):
    """Surface ONLY the specific items the prior adversarial sub-agent pass flagged (stratum-aware,
    so common cards appearing in many pairs are not blanket-flagged)."""
    joined = " × ".join(names)
    if stratum == "storied" and any("Óin the Brave" in n for n in names):
        return "sub-agent MINOR: possible spurious QUALIFIES_FOR gate:storied edge (self-double-count?)"
    if stratum == "null_pairs" and any("Belladonna Took" in n for n in names):
        return "sub-agent MAJOR: this 'null' pair may hide a MISSED token-enters trigger (creator → payoff)"
    if stratum == "null_pairs" and any("Rhovanion Rampager" in n for n in names):
        return "sub-agent MAJOR: this 'null' pair may hide a MISSED sacrifice-outlet → dies-trigger relation"
    if stratum == "multi_edge_pairs" and any("Nori" in n for n in names) and any("Kíli" in n for n in names):
        return "sub-agent MINOR: Nori → Kíli SUPPLIES_RESOURCE may be better typed ENABLES_TRIGGER"
    return None


def _pair_index():
    idx = {}
    for r in (json.loads(l) for l in io.open(REPO / "data/graph_global/pair_index.jsonl", encoding="utf-8")
              if l.strip()):
        idx[(r["source_card"], r["target_card"])] = r
    return idx


def _directed_relations(ids, idx):
    """Return the ACTUAL directed relations between the two cards, as (src_id, tgt_id, relation),
    from the frozen pair index — never assume the item's name order is the edge direction."""
    out, seen = [], set()
    a, b = ids[0], ids[-1]
    for s, t in ((a, b), (b, a)):
        row = idx.get((s, t))
        if not row:
            continue
        for lay in _LAYERS:
            for rel in row.get(lay, []):
                if (s, t, rel) not in seen:               # dedupe: one row per directed relation type
                    seen.add((s, t, rel))
                    out.append((s, t, rel, lay))
    return out


def _faces_by_card():
    m = {}
    for f in (json.loads(l) for l in io.open(FACES, encoding="utf-8") if l.strip()):
        m.setdefault(f["card_id"], []).append(f)
    for v in m.values():
        v.sort(key=lambda f: f.get("index", 0))
    return m


def _oracle_block(card_id, fbc):
    out = []
    for f in fbc.get(card_id, []):
        tl = (f.get("type_line") or {}).get("raw", "")
        mc = (f.get("mana_cost") or {}).get("raw", "")
        head = f"**{f['name']}** — {tl}" + (f"  ({mc})" if mc else "")
        body = (f.get("oracle_text") or "").strip() or "_(no rules text)_"
        out.append(head + "\n" + "\n".join("> " + ln for ln in body.split("\n")))
    return "\n>\n".join(out) if out else "_(card not found)_"


def main():
    fbc = _faces_by_card()
    idx = _pair_index()
    strata = [json.loads(l) for l in io.open(VSET, encoding="utf-8") if l.strip()]
    # card_id -> display name, learned from the gold set's own id/name correspondence
    id2name = {}
    for s in strata:
        for it in s["items"]:
            names = it.get("item") if isinstance(it.get("item"), list) else [it.get("item")]
            iids = it.get("ids") if it.get("ids") else [it.get("id")]
            for cid, nm in zip(iids, names):
                id2name[cid] = nm
    md = ["# HOB gold-set — HUMAN audit worksheet", "",
          "**You are the external human adjudicator.** The graph's own structural assertions already "
          "pass, and five adversarial sub-agents did a semantic pass (`reports/manual_gold_set_review.md`) "
          "— but that is explicitly *not* a substitute for your final adjudication. For each item, read "
          "the **printed Oracle text** below and decide whether the graph's **claim** is semantically "
          "correct and correctly directed against the actual card + the cited rule.", "",
          "For each item mark the verdict box and add a note if wrong/unsure:", "",
          "`[x] correct`  ·  `[ ] wrong`  ·  `[ ] unsure`   — then **Notes:** …", "",
          f"Total items: **{sum(len(s['items']) for s in strata)}** across {len(strata)} strata. "
          "⚠ = an item the sub-agent pass already flagged; look closely.", ""]
    rows = []
    n = 0
    for s in sorted(strata, key=lambda x: x["stratum"]):
        stratum = s["stratum"]
        claim_default, cr_default = STRATUM.get(stratum, ("(see item)", None))
        md += [f"---", f"## Stratum: `{stratum}`  ({len(s['items'])} items)", "",
               f"**Claim for this stratum:** {claim_default}"
               + (f"  ·  _{cr_default}_" if cr_default else ""), ""]
        for it in s["items"]:
            n += 1
            names = it.get("item") if isinstance(it.get("item"), list) else [it.get("item")]
            ids = it.get("ids") if it.get("ids") else [it.get("id")]
            flag = _flag_for(stratum, names)
            md.append(f"### {n}. {' × '.join(names)}" + ("  ⚠" if flag else ""))
            # oracle text for each card in the item
            for cid in ids:
                md.append(_oracle_block(cid, fbc))
                md.append(">")
            # the specific claim + CR
            if stratum == "multi_edge_pairs":
                directed = _directed_relations(ids, idx)
                md.append("**Graph claim — each directed relation (verify existence AND direction):**")
                for s_id, t_id, r, lay in directed:
                    g, cr = REL.get(r, ("(relation)", ""))
                    md.append(f"- **{id2name.get(s_id, s_id)}** —`{r}`→ **{id2name.get(t_id, t_id)}**: "
                              f"{g}  _({cr}; layer: {lay})_")
                combo = sorted(it.get("relation_combination", []))
                got = sorted({r for _, _, r, _ in directed})
                extra = [r for r in got if r not in combo]
                if extra:
                    md.append(f"> _(the frozen gold item tested the subset {combo}; the full 7-layer graph "
                              f"also projects {extra} between this pair — all are shown above and audited.)_")
            else:
                md.append(f"**Graph claim:** {it.get('expected', claim_default)}")
                if cr_default:
                    md.append(f"_Rule:_ {cr_default}")
            if flag:
                md.append(f"> ⚠ **{flag}**")
            md += ["", "**Verdict:** `[ ] correct`  `[ ] wrong`  `[ ] unsure`   **Notes:** ", ""]
            rows.append({"n": n, "stratum": stratum, "ids": ids, "item": names,
                         "claim": (it.get("relation_combination") or it.get("expected")),
                         "flagged": bool(flag), "verdict": "", "notes": ""})
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    OUT_JSONL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {n} items -> {OUT_MD.relative_to(REPO)} and {OUT_JSONL.relative_to(REPO)}")
    print(f"flagged (sub-agent findings): {sum(1 for r in rows if r['flagged'])}")


if __name__ == "__main__":
    main()
