# HOB Manual Gold-Set Semantic Review

**Date:** 2026-08-16. **Method:** the stratified sample (spec §Manual gold set) was hand-reviewed
*semantically* — each item read against its printed Oracle text and the MTG comprehensive rules,
not merely against the graph's own structural assertions. To reduce self-review bias (the graph's
author reviewing their own work), the review was conducted by **five independent adversarial
reviewer agents** (fresh context, instructed to hunt for errors, rules-grounded only), then
synthesized here.

**Epistemic status:** this is a substantive adversarial semantic pass, NOT a substitute for an
external human's final adjudication — a human should still spot-check. It found real issues (below)
and confirmed the bulk of the graph is semantically correct.

## Verdict by stratum

| Stratum | Reviewed | Result |
|---|---|---|
| Recruit (10) | all 10 | **CLEAN** — draw→discard order, nonland-discard conditionality, 1/1 W Human Soldier, per-card trigger all correct |
| Bard, King of Dale | draw + token replacement | **CLEAN** — both replacement effects, correct quantities |
| Storied gate + 9 cards | gate + payoffs | **CLEAN** — counts exactly {artifact, legendary, Saga} as a union; legendary artifacts count ONCE (no double-count); enduring story persists; all 9 payoffs wired |
| Sagas (8) | all 8 | **CLEAN** — lore counters, chapter triggers, sacrifice-after-final-chapter, Storied-qualifying all correct |
| Multi-token (The Misty Mountains Cold) | token specs | **CLEAN** — Treasure + Dragon specs exact; inv#7 (Treasure = artifact = Storied-qualifying) holds |
| Adventures (17) | all 17 | **CLEAN** — exactly two distinct faces, correct roles/names/types/costs, no face conflation, correct non-creature reminder wording |
| Equipment (12) | all 12 | **CLEAN** — every equip cost, P/T mod, and granted keyword matches Oracle exactly; attachment-conditioned; alt modes + auto-attach + additional costs correct; no reverse relation |
| Self-pairs (10) | all 10 | **CLEAN** — all genuinely reflexive, none routed through an "another/other" exclusion |
| Multi-edge pairs (6 of 30 sampled) | correctness + direction | **CLEAN** — every asserted relation individually correct and correctly directed |
| Replacement effects (6) | REPLACES labels | **CLEAN** — all 6 are genuine CR-616 "would…instead" replacements |
| Null pairs (20) | true-null vs missed | **18 truly null**, 2 reveal missed-relation classes (below) |

**No false positives were found** — every asserted relation the reviewers checked is individually
correct and correctly directed; self-effects are genuinely reflexive; every REPLACES is real.

## Findings (severity-sorted)

### MAJOR — completeness gaps (false negatives), not wrong assertions
1. **Second-draw enablers are incomplete (~13 of ~39 real drawers).** The `gate:second-draw` count
   is fed only by draw operations that produce the canonical `event:card-drawn` / the state
   increment (`op:recruit:draw` + Beorn the Fierce, Old Fat Spider, The Chief Warg). **~26 HOB cards
   that genuinely draw a card are NOT wired as enablers** because their draw is modeled with a
   non-canonicalized primitive (`resource:card`, `resource:cards`, `resource:card_in_hand`,
   `obj:draw`) that never reaches the counter — e.g. Belladonna Took, Kíli, Bilbo (both), Gollum,
   The Master of Lake-town, Balin, The Arkenstone, Allure of Power, Thrór's Map, Plunder the
   Trollshaws, etc. Every one can produce a controller's 2nd draw and should be an ENABLES_TRIGGER
   enabler of Master's Councillors / Bard the Bowman / Lakeshore Apothecary. **Fix:** canonicalize
   the fragmented draw primitives so all genuine card-draw ops feed `state:cards-drawn-this-turn`.
   (This is in the additive `mechanism_repair` layer — not the frozen graph.)
2. **Two unmodeled trigger classes** (surfaced by 2 of the 20 null pairs), each a whole mechanism
   family, not a one-off:
   - **Token-enters triggers** — a token creator (amass/Eagles/Head of the Hunt's Wolf) → a
     "whenever a token you control enters…" payoff (Belladonna Took). No creator links to it.
   - **Sacrifice-outlet → dies-triggers** — a repeatable "Sacrifice another creature" outlet
     (Tom, Bert, and William) → a "when this creature dies…" trigger (Rhovanion Rampager). Sac
     outlets carry no outgoing ENABLES_TRIGGER to dies-triggered abilities.
   These are analogous to the pt4 targeted-repair rounds (a fresh audit → repair → reprojection
   would close them). **Decision needed:** in scope for a further repair round, or accepted-deferred?

### MINOR
3. **Óin the Brave has a spurious `QUALIFIES_FOR gate:storied` edge** sourced from the "Storied"
   keyword span itself, in addition to the correct legendary-class edge (78 QUALIFIES_FOR edges /
   77 distinct sources — Óin is the only duplicate). Possessing Storied does not make a permanent
   count toward the threshold. Harmless if the count dedups by object; a self-double-count if it
   counts by edge. This edge is in the **frozen Phase 4 graph** → fixing it is a sanctioned
   corrective re-freeze (needs go-ahead).
4. **Second-draw counter reset scope** is `start_of_controllers_turn`; "your second card each turn"
   should reset at *every* turn boundary (so a 2nd draw on an opponent's turn is counted). Loose;
   low practical impact in HOB.
5. **Three redundant second-draw event nodes** (`event:draw-second-card`, `-each-turn`,
   `_each_turn`) — reconciled via the gate's `output_events`, but an un-normalized naming smell.
6. **Nori → Kíli** is labelled `SUPPLIES_RESOURCE`; `ENABLES_TRIGGER` is a more precise fit (a
   Dwarf's entry firing Kíli's tribal ETB). Relation correct + directed; only the label is loose.
7. **Data hygiene:** stored `type_line`/keyword separators contain a `�` replacement character
   (an upstream em-dash/bullet encoding artifact). Cosmetic; affects display, not meaning.

## Regression-fixture note
The clean strata (Recruit, Storied, Sagas, Adventures, Equipment, self-pairs, multi-edge,
replacements) are confirmed correct and serve as regression fixtures. The `structural_validation_set`
already encodes deterministic assertions for them; this semantic pass corroborates those assertions
against the printed Oracle text.
