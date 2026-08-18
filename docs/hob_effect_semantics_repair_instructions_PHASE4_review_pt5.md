---
phase: Phase 4
iteration: pt5
reviewed_commit: 8320fdd20eb40005bde6a7eff37ac328e66a7962
parent_commit: be6f6b5152812bd95e1e33bab0ece8f4b67e47d6
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 2
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `8320fdd20eb40005bde6a7eff37ac328e66a7962`
(`Effect-semantics Phase 4b: participant/resource discard and mill records`) against
parent `be6f6b5152812bd95e1e33bab0ece8f4b67e47d6`.

Phase 4b improves participant-level DISCARD and MILL extraction and preserves the
accepted Phase 4a draw/life records, but it does not yet preserve all mandatory
resource semantics. In particular, the authoritative structured records omit
discarded-card selectors/bindings and omit the trigger antecedent for a variable
mill effect. Phase 4b should not proceed until these are repaired.

## Evidence Inspected

- `git show --stat --summary 8320fdd20eb40005bde6a7eff37ac328e66a7962`
- `git diff --check be6f6b5152812bd95e1e33bab0ece8f4b67e47d6..8320fdd20eb40005bde6a7eff37ac328e66a7962`
- `git diff --name-status be6f6b5152812bd95e1e33bab0ece8f4b67e47d6..8320fdd20eb40005bde6a7eff37ac328e66a7962`
- `src/hobkg/effect_semantics.py`
- `tests/test_effect_resource.py`
- `data/graph_global/effect_records.jsonl`
- `data/graph_global/card_pair_projection_effect.jsonl`
- `data/graph_global/pair_index.jsonl`
- `reports/effect_reconciliation.md`
- `reports/effect_semantics.md`
- Direct JSON queries for all generated `DISCARD` and `MILL` records.
- Portability search for card-name branches in `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: `89 passed`.
- `pytest -q`
  - Result: `359 passed`.
- Frozen manifest SHA-256 verification against `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- `python -m hobkg.cli effect-build`
  - Result: 189 effects, 126 faces, 7,950 pair projections.
- Repeated `python -m hobkg.cli effect-build`
  - Result: byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `7fd993320d34f1f7b9e479074fb2e94bb24b6208deeb7d51bb14e12f226732da`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`
- `python -m hobkg.cli effect-reconcile`
  - Result: 275 clause/family pairs, 185 extracted, 4 deferred, 0 unresolved.
- Direct projection query for `DISCARDS_CARDS`, `MILLS_CARDS`, `DRAWS_CARDS`,
  `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no resource relations emitted in `card_pair_projection_effect.jsonl`
    or `pair_index.jsonl`.
- Direct comparison of accepted Phase 4a `DRAW`/`GAIN_LIFE`/`LOSE_LIFE` records
  between `b514f37` and `8320fdd`
  - Result: same 52-record subset hash,
    `52cda2c6b04c6095dc9963d1c2fb4b09afa4069a077cf1b1e7db4c045fafcf7d`.

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was detected.

## Findings

### 1. DISCARD records omit discarded-card selectors and object bindings

Impact: authoritative structured semantics.

The new participant-level `DISCARD` records encode participant and amount, but
they do not encode which cards are being discarded from hand. All inspected
`DISCARD` records had `card_selector: null` and `object: null`.

Concrete examples:

- `Stony-Voiced Goblins`: Oracle requires each opponent to discard a card. The
  record correctly has participant `each_opponent` and amount `1`, but no
  selector for one card from each affected opponent's hand.
- `Uncover the Moon-Letters`: Oracle requires you to discard two cards if the
  prior action is taken. The record preserves the `if you do` gate and amount
  `2`, but no selector for the two cards discarded from your hand.
- `Balin, Loremaster`: Oracle requires discarding your hand. The record uses
  amount `hand`, but does not represent the selected set as all cards in your
  hand.
- `Down, Down to Goblin-town`: Oracle reveals a target opponent's hand, then
  you choose a nonland card from it, then that player discards that card. The
  generated `DISCARD` record has participant `target_opponent`, `targeted:
  true`, and amount `1`, but loses the nonland-card selector, the chosen-card
  binding, and the fact that the discarded object is the same card chosen from
  the revealed hand.

Phase 4's stated review standard includes card selectors for discard effects,
not just participant and quantity. The current records therefore prove that a
discard operation exists, but not that the discarded-object semantics were
preserved.

Required correction:

- Add an explicit discarded-card object/selector representation for `DISCARD`
  records.
- Preserve source zone `hand`, destination zone `graveyard`, quantity, and
  card-selection constraints together.
- Preserve same-object bindings such as "that card" in `Down, Down to
  Goblin-town`, including the nonland predicate and antecedent chosen-card
  binding.
- Add tests that fail if a `DISCARD` record lacks the required discarded-card
  selector/binding for the audited examples.

### 2. The Master of Lake-town mill record loses its trigger antecedent and amount binding

Impact: authoritative structured semantics.

Oracle text: "Whenever a player loses life, that player mills that many cards."

The generated record for `The Master of Lake-town` is:

- `op`: `MILL`
- participant: `that_player`
- amount: `variable`
- `quantity_formula`: `{"kind": "variable", "binding": "that many cards"}`
- `condition`: `null`

This loses the trigger condition that a player lost life and under-specifies the
variable binding. "That many" is not an unbound free variable; it is the amount
of life lost by the same player who mills.

Required correction:

- Preserve the trigger antecedent as a condition/event on the mill record.
- Bind `that_player` to the player who lost life.
- Bind the variable mill amount to the life-loss quantity from that triggering
  event.
- Add a regression test that checks this condition and binding directly, not
  merely the presence of a `MILL` record.

## Required Corrections

1. Extend Phase 4b DISCARD records to encode discarded-card selectors and
   object identity, including same-object antecedents.
2. Extend the mill trigger representation for `The Master of Lake-town` so the
   trigger event and "that many" amount binding are explicit.
3. Regenerate `effect_records.jsonl`, `reports/effect_semantics.md`, and
   `reports/effect_reconciliation.md` after the repairs.
4. Keep Phase 4a draw/life records byte-identical unless the reviewer or human
   owner explicitly accepts a reason to modify them.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- Direct JSON assertions that:
  - `Down, Down to Goblin-town` binds the discarded object to the previously
    chosen nonland card from target opponent's revealed hand.
  - `Balin, Loremaster` discards all cards in your hand.
  - `Uncover the Moon-Letters` discards two cards from your hand under the
    `if you do` condition.
  - `Stony-Voiced Goblins` makes each opponent discard one card from that
    opponent's hand.
  - `The Master of Lake-town` includes the player-loses-life trigger condition
    and binds the mill quantity to the life lost.

## Phase Proceed Status

This Phase 4b implementation commit is not accepted. Phase 4 may continue only
with a repair commit addressing the findings above or with an explicit human
decision to refine the phase specification.
