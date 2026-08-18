---
phase: Phase 4
iteration: pt6
reviewed_commit: 1577a43ae9870ea07fcb6803cf7fbda32506ff0a
parent_commit: 6552b7b3736df08305e7bae7a9d6bfcd4bed4915
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 1
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `1577a43ae9870ea07fcb6803cf7fbda32506ff0a`
(`Effect-semantics Phase 4b repair: address review 6552b7b`) against parent
`6552b7b3736df08305e7bae7a9d6bfcd4bed4915`.

The commit addresses the two findings from `PHASE4_review_pt5` for the named
audited records: discard records now carry a discarded-card selector, `Down,
Down to Goblin-town` preserves the chosen nonland-card same-object binding, and
`The Master of Lake-town` preserves the life-loss trigger and variable amount
binding. However, the generalized selector extraction leaks a later conditional
predicate into an earlier discard instruction, producing an incorrect
authoritative record for `Silvan Reveler`. This is blocking.

## Evidence Inspected

- `git status --short --branch`
- `git fetch origin`
- `git log --oneline --decorate -12 --all`
- `git show --stat --summary --format=fuller 1577a43ae9870ea07fcb6803cf7fbda32506ff0a`
- `git show -s --format=full 1577a43ae9870ea07fcb6803cf7fbda32506ff0a`
- `git diff --check 6552b7b3736df08305e7bae7a9d6bfcd4bed4915..1577a43ae9870ea07fcb6803cf7fbda32506ff0a`
- `git diff --name-status 6552b7b3736df08305e7bae7a9d6bfcd4bed4915..1577a43ae9870ea07fcb6803cf7fbda32506ff0a`
- `git diff 6552b7b3736df08305e7bae7a9d6bfcd4bed4915..1577a43ae9870ea07fcb6803cf7fbda32506ff0a -- src/hobkg/effect_semantics.py`
- `git diff 6552b7b3736df08305e7bae7a9d6bfcd4bed4915..1577a43ae9870ea07fcb6803cf7fbda32506ff0a -- tests/test_effect_resource.py`
- Direct JSON queries over `data/graph_global/effect_records.jsonl` for every
  `DISCARD` and `MILL` record.
- Oracle text from `data/normalized/faces.jsonl` for `Silvan Reveler`, `Down,
  Down to Goblin-town`, and `The Master of Lake-town`.
- Portability search for audited card names in `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: `95 passed`.
- `pytest -q`
  - Result: `365 passed`.
- Frozen manifest SHA-256 verification against
  `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- Direct projection query for `DISCARDS_CARDS`, `MILLS_CARDS`, `DRAWS_CARDS`,
  `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no resource relations emitted in `card_pair_projection_effect.jsonl`
    or `pair_index.jsonl`.
- Direct comparison of accepted Phase 4a `DRAW`/`GAIN_LIFE`/`LOSE_LIFE` records
  between `b514f37` and `1577a43`
  - Result: same 52-record subset hash,
    `52cda2c6b04c6095dc9963d1c2fb4b09afa4069a077cf1b1e7db4c045fafcf7d`.
- `python -m hobkg.cli effect-build`, run twice
  - Result: 189 effects, 126 faces, 7,950 pair projections.
  - Byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `47e9b731f273b45035255c7f35c599b31bfdb36930fc7082e38513d5a4168957`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`
- `python -m hobkg.cli effect-reconcile`
  - Result: 275 clause/family pairs, 185 extracted, 4 deferred, 0 unresolved.

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was detected.

## Findings

### 1. `Silvan Reveler` discard selector incorrectly requires a land card

Impact: authoritative structured semantics.

Oracle text:

`When this creature enters, draw a card, then discard a card. If you discard a
land card this way, put it from your graveyard onto the battlefield tapped.`

The actual discard instruction is unconditional about card type: you draw a
card, then discard a card. The land predicate belongs only to the following
conditional movement instruction, which is not part of Phase 4b's discard
effect.

Generated `DISCARD` record in `1577a43`:

```json
"name": "Silvan Reveler",
"op": "DISCARD",
"amount": "1",
"card_selector": {
  "chooser": "you",
  "count": "1",
  "owner": "you",
  "predicates": {"type": "land"},
  "zone": "hand"
}
```

This contradicts Oracle text by narrowing the discarded-card selector to lands.
The likely cause is `_discard_selector()` scanning `low[ms:ms + 90]`, which
allows text from the later sentence, `If you discard a land card this way`, to
modify the selector for the earlier `discard a card` operation.

The test suite misses this regression: `test_phase4b_condition_phrase_is_not_a_second_discard`
checks that only one discard record exists for `Silvan Reveler`, but it does not
assert that the one record's `card_selector` remains unconstrained.

Required correction:

- Scope discard-card selector predicate extraction to the matched discard phrase
  and its true object phrase, not to later condition sentences.
- Preserve `Silvan Reveler` as discarding one unconstrained card from your hand.
- Add a regression assertion that `Silvan Reveler` has no land predicate on the
  `DISCARD` record.
- Re-run the full generated-artifact checks after repair.

## Repaired Prior Findings

The two `PHASE4_review_pt5` findings are repaired for the named acceptance
examples:

- `Down, Down to Goblin-town` now has `card_selector.owner:
  target_opponent`, `chooser: you`, `predicates.nonland: true`, `object:
  that_card`, and `antecedent.same_object: true`.
- `The Master of Lake-town` now has `condition.kind: triggered`, event
  `Whenever a player loses life`, binds for `player_who_lost_life` and
  `life_lost`, and a trigger-sourced variable `quantity_formula`.

Those fixes should be preserved in the next repair.

## Required Corrections

1. Remove the false `land` predicate from `Silvan Reveler`'s DISCARD
   `card_selector`.
2. Make the selector parser operation-scoped so future "If you discard a
   <predicate> card this way" clauses do not back-propagate into an earlier
   unconstrained discard effect.
3. Add tests that distinguish a discard effect's selector from a later
   condition referring to what was discarded.
4. Regenerate `effect_records.jsonl` and any reports affected by the repair.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- Direct JSON assertions that:
  - `Silvan Reveler` discards one unconstrained card from your hand.
  - `Down, Down to Goblin-town` still binds the discarded object to the
    previously chosen nonland card from target opponent's revealed hand.
  - `The Master of Lake-town` still includes the player-loses-life trigger and
    binds the mill quantity to the life lost.
  - Every `DISCARD` record still carries a hand-zone card selector with owner,
    chooser, and count.

## Phase Proceed Status

This Phase 4b repair commit is not accepted. Phase 4 may continue only with a
repair commit addressing the blocking `Silvan Reveler` selector regression or
with an explicit human decision to refine the phase specification.
