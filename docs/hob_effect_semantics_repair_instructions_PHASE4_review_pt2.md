---
protocol: worker_reviewer_handshake_v1
role: reviewer
phase: Phase 4
iteration: pt2
reviewed_commit: d40c6f02120b99560568d02470df88fa37249f45
parent_commit: 3867e4b7a821a686d91500e82e12348db61773a6
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 2
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed commit: `d40c6f02120b99560568d02470df88fa37249f45` (`Effect-semantics Phase 4a repair: address review 3867e4b (participant metadata)`)

Parent commit: `3867e4b7a821a686d91500e82e12348db61773a6` (`Review Phase 4 pt1: REPAIR c5f32f9`)

The repair fixes the six blocking findings from Phase 4 review pt1, but Phase 4a is still not acceptable because the generated participant records still misrepresent mandatory optionality and formula quantities. These are authoritative structured-semantics defects, not test failures.

## Evidence Inspected

- Governing instructions and protocol:
  - `INSTRUCTIONS.md`
  - `docs/review_event_protocol.md`
  - `docs/hob_effect_semantics_repair_instructions.md`
  - `docs/phase4-requirements.md`
- Prior review:
  - `docs/hob_effect_semantics_repair_instructions_PHASE4_review_pt1.md`
- Reports and recent project record:
  - `reports/effect_census.md`
  - `reports/effect_reconciliation.md`
  - `reports/effect_semantics.md`
  - recent tail of `LABNOTEBOOK.md`
- Git/history:
  - `git status --short --branch`
  - `git fetch origin`
  - `git log --oneline --decorate -12 --all`
  - `git show --stat --summary d40c6f0`
  - `git diff --check 3867e4b..d40c6f0`
  - `git diff --name-status 3867e4b..d40c6f0`
  - `git diff --stat --summary 3867e4b..d40c6f0`
- Changed files:
  - `src/hobkg/effect_schema.py`
  - `src/hobkg/effect_semantics.py`
  - `tests/test_effect_participant.py`
  - `data/graph_global/effect_records.jsonl`
  - `reports/effect_reconciliation.md`
  - `reports/effect_semantics.md`
  - append-only log/notebook entries
- Generated records inspected directly:
  - `data/graph_global/effect_records.jsonl`
  - `data/graph_global/card_pair_projection_effect.jsonl`
  - `data/graph_global/pair_index.jsonl`
  - `data/normalized/faces.jsonl`

## Tests And Commands Run

- `git diff --check 3867e4b..d40c6f0`
  - Passed.
- `pytest tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: 69 passed.
- Frozen manifest hash check against `data/graph_global/frozen_manifest.json`
  - Result: all protected frozen artifacts matched.
- Pair fan-out check:
  - `card_pair_projection_effect.jsonl` and `pair_index.jsonl` unchanged relative to parent for effect projection; no `DRAWS_CARDS`, `GAINS_LIFE`, or `LOSES_LIFE` pairs.
- `pytest -q`
  - Result: 339 passed in 40.27s.
- `python -m hobkg.cli effect-build`
  - Result: 172 effects on 121 faces; 7,950 pairs.
- `python -m hobkg.cli effect-reconcile`
  - Result: 244 `(clause_id, family)` pairs; 168 extracted; 4 deferred/nonexecutable; 0 unresolved.
- Two serial `python -m hobkg.cli effect-build` runs:
  - Stable `data/graph_global/effect_records.jsonl` SHA-256: `78b5d495f02e79b4a12ce323fb9306b9d599db54c55c589cbd1b61b8059a558e`
  - Stable `data/graph_global/card_pair_projection_effect.jsonl` SHA-256: `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`

The full suite dirtied known generated/report files in the working tree during review. They were not staged.

## Frozen Artifact Status

Accepted. The frozen core remains byte-identical to `data/graph_global/frozen_manifest.json`.

Verified protected files:

- `data/graph/conditions.jsonl`
- `data/graph/edges.jsonl`
- `data/graph/gates.jsonl`
- `data/graph/nodes.jsonl`
- `data/graph_global/conditions.jsonl`
- `data/graph_global/edges.jsonl`
- `data/graph_global/nodes.jsonl`

No frozen-baseline change was detected.

## Resolved Pt1 Findings

The six Phase 4 pt1 blockers are fixed in the generated records:

- Meager Meal, Reverent Howl, Down, Down to Goblin-town, and The Sackville-Bagginses now preserve targeted participant status.
- Gleaming Splendor now records `target_player`, `targeted: true`, `affects_each: true`, and `participant_quantity: 2`.
- Gandalf, Wandering Wizard now binds the draw participant to `owner`.
- Supper for Spiders no longer emits the quoted Food activated ability as immediate `GAIN_LIFE`; reconciliation records it as a granted ability / deferred execution case.
- Bard, King of Dale no longer emits a direct `DRAW 1` for the replaced draw event; only the replacement `DRAW 2` remains.
- Gollum, Riddle Master participant alternatives now carry `mode.kind: choose_one`, `exclusive: true`, and distinct mode indices.

## Findings

### Blocking 1: optionality still leaks from sibling instructions

Impact: authoritative structured semantics.

The extractor still marks a participant effect optional when any `may` appears in the whole clause, even if the `may` applies to a different instruction or to the condition that enables the effect.

Concrete Oracle example:

> Old Thrush: "When this creature enters, you gain 2 life. You may search your library for a basic land card, reveal it, then shuffle and put that card on top."

Generated record:

```json
{
  "name": "Old Thrush",
  "op": "GAIN_LIFE",
  "amount": "2",
  "participant": "you",
  "optional": true,
  "condition": null
}
```

The life gain is mandatory. Only the later search instruction is optional. This violates the Phase 4 requirement that optionality remain distinct and not live only in prose.

Related cases need careful treatment rather than a blanket rule:

- Ragged Short Spear: "you may discard a card. If you do, draw two cards" should be a conditional draw gated by the optional discard, not simply `optional: true`.
- The Sackville-Bagginses: "you may sacrifice ... If you do, draw a card..." likewise needs a condition/cost binding rather than plain optionality on the draw.
- Balin, Loremaster: "you may discard your hand. Draw X cards, where X is the number of cards discarded this way" needs the optional discard cost/choice and variable quantity binding represented explicitly.

Required correction: compute optionality per operation/span and distinguish an optional effect from a mandatory effect conditioned on an optional prior action.

### Blocking 2: formula quantities remain fixed or under-specified

Impact: authoritative structured semantics.

The generated records still collapse explicit formula quantities into fixed amounts or omit the formula binding.

Concrete Oracle example:

> The Master of Lake-town: "When The Master of Lake-town dies, draw a card for each graveyard with seven or more cards in it."

Generated record:

```json
{
  "name": "The Master of Lake-town",
  "op": "DRAW",
  "amount": "1",
  "scaling": "for each graveyard with seven or more cards in it."
}
```

This is not a fixed one-card draw; it is `1 * number_of_graveyards_with_seven_or_more_cards`. Recording `amount: "1"` as the main quantity contradicts the Oracle effect unless the formula is made authoritative.

Additional examples:

- Balin, Loremaster: "Draw X cards, where X is the number of cards discarded this way" records `amount: "X"` but no `scaling` / binding for X.
- Uncover the Moon-Letters: "draw X cards, where X is the amount of mana spent to cast that spell" records `amount: "X"` but no `scaling` / binding for X.

Required correction: represent formula quantities as structured variable quantities, not fixed counts. For `X`, carry the `where X is ...` binding. For "for each" quantities, make the multiplier and counted set explicit enough that consumers do not read `amount: "1"` as the total.

## Concrete Oracle Examples

Correct after this repair:

- Reverent Howl: target player draws two and loses 2 life, same participant variable, targeted.
- Meager Meal: target player life gain is targeted.
- Gleaming Splendor: two target players each draw one card.
- Gandalf, Wandering Wizard: owner draws three cards.
- Supper for Spiders: quoted Food life-gain ability is not immediate.
- Bard, King of Dale: no false direct draw of the replaced event.
- Gollum, Riddle Master: participant modes are explicit alternatives.

Still incorrect:

- Old Thrush: mandatory gain 2 life is marked optional.
- Ragged Short Spear / The Sackville-Bagginses: conditional draws caused by optional prior actions are represented as optional effects rather than conditionally enabled effects.
- The Master of Lake-town: formula draw count is represented as fixed `amount: "1"` plus a prose scaling string.
- Balin, Loremaster / Uncover the Moon-Letters: `X` draw quantities lack structured `where X is ...` bindings.

## Required Corrections

1. Preserve optionality per operation, not per whole clause.
2. Distinguish optional effects from mandatory effects gated by an optional cost/action.
3. Represent `X` and `for each` draw quantities as structured formulas/bindings.
4. Add regression tests that inspect generated `effect_records.jsonl` or `build_effects(write=False)["_structured"]` for:
   - Old Thrush life gain `optional: false`.
   - Ragged Short Spear and The Sackville-Bagginses draw effects carrying conditional/cost-paid gates rather than plain optionality.
   - The Master of Lake-town draw count represented as formulaic, not total amount 1.
   - Balin and Uncover preserving the `where X is ...` binding.

## Acceptance Tests For The Next Commit

The next repair commit should be accepted only if all of the following hold:

- `git diff --check d40c6f0..<repair-commit>` is clean.
- Frozen manifest checks pass.
- `pytest` passes.
- Two serial `python -m hobkg.cli effect-build` runs are byte-identical.
- `python -m hobkg.cli effect-reconcile` reports 0 unresolved and keeps deferred/nonexecutable separate.
- Participant draw/life records still do not fan out into card-pair projection.
- Direct JSONL checks confirm all pt1 repairs remain fixed.
- Direct JSONL checks confirm the optionality and formula-quantity corrections above.

## May The Phase Proceed?

No. Phase 4a still requires repair before moving to the remaining Phase 4 families.
