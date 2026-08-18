---
phase: Phase 4
iteration: pt8
reviewed_commit: 73e108c9a21e23048ad36adfe1c13b38bda449e1
parent_commit: 5429b7f22c46ebbcd0330d44f1fae5f37930bc83
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 2
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `73e108c9a21e23048ad36adfe1c13b38bda449e1`
(`Effect-semantics Phase 4c: SACRIFICE`) against parent
`5429b7f22c46ebbcd0330d44f1fae5f37930bc83`.

The commit adds useful Phase 4c `SACRIFICE` records and keeps the accepted
Phase 4a/4b participant records byte-identical. It correctly avoids pair
fan-out and covers many cost/effect distinctions. However, condition extraction
for sacrifice records is still too broad: later "If you do" payoff text is
attached to the sacrifice operation itself, and mandatory conditional
self-sacrifice records do not preserve the actual predicate that gates the
sacrifice. These affect authoritative structured semantics and block
acceptance.

## Evidence Inspected

- `git status --short --branch`
- `git fetch origin`
- `git log --oneline --decorate -16 --all`
- `git show --stat --summary --format=fuller 73e108c9a21e23048ad36adfe1c13b38bda449e1`
- `git show -s --format=full 73e108c9a21e23048ad36adfe1c13b38bda449e1`
- `git diff --check 5429b7f22c46ebbcd0330d44f1fae5f37930bc83..73e108c9a21e23048ad36adfe1c13b38bda449e1`
- `git diff --name-status 5429b7f22c46ebbcd0330d44f1fae5f37930bc83..73e108c9a21e23048ad36adfe1c13b38bda449e1`
- `git diff 5429b7f22c46ebbcd0330d44f1fae5f37930bc83..73e108c9a21e23048ad36adfe1c13b38bda449e1 -- src/hobkg/effect_semantics.py`
- `git diff 5429b7f22c46ebbcd0330d44f1fae5f37930bc83..73e108c9a21e23048ad36adfe1c13b38bda449e1 -- tests/test_effect_sacrifice.py`
- `git diff 5429b7f22c46ebbcd0330d44f1fae5f37930bc83..73e108c9a21e23048ad36adfe1c13b38bda449e1 -- data/graph_global/effect_records.jsonl`
- Direct JSON queries over `data/graph_global/effect_records.jsonl` for every
  generated `SACRIFICE` record.
- Oracle text from `data/normalized/faces.jsonl` for every generated
  `SACRIFICE` record.
- Portability search for audited card names in `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - First run overlapped with another pytest/build writer and failed with
    transient generated-file interference.
  - Isolated rerun result: `109 passed`.
- `pytest -q`
  - Result: `379 passed`.
- Frozen manifest SHA-256 verification against
  `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- Direct projection query for `SACRIFICES`, `DISCARDS_CARDS`, `MILLS_CARDS`,
  `DRAWS_CARDS`, `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no resource/sacrifice relations emitted in
    `card_pair_projection_effect.jsonl` or `pair_index.jsonl`.
- Direct comparison of accepted Phase 4a/4b participant records
  (`DRAW`, `GAIN_LIFE`, `LOSE_LIFE`, `DISCARD`, `MILL`) between `b0759cb` and
  `73e108c`
  - Result: same 69-record subset hash,
    `dae5c1a33cb3d2fd5e75814d7a7d846ebcc771d95b4f885bd779ac708982d3cc`.
- `python -m hobkg.cli effect-build`, run twice
  - Result: 211 effects, 132 faces, 7,950 pair projections.
  - Byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `4e2692e6c903faa4e37b5d4d8a6325d904099331240e042575ca6da0a56f89c2`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`
- `python -m hobkg.cli effect-reconcile`
  - Result: 311 clause/family pairs, 207 extracted, 4 deferred, 0 unresolved.

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was detected.

## Findings

### 1. Later payoff conditions leak onto the sacrifice operation itself

Impact: authoritative structured semantics.

Several generated sacrifice records attach `{"kind": "conditional_effect"}` to
the sacrifice operation because `_sacrifice_effects()` calls `_sch.condition(raw)`
over the full line. In these cards, the `If you do` or `When you do` phrase
belongs to the payoff that follows the sacrifice, not to the sacrifice event.
The sacrifice is the prior optional action or activated cost.

Concrete examples:

- `Rhovanion Rampager`: Oracle says "you may sacrifice another creature. If you
  do, put a number of +1/+1 counters..." The sacrifice record is correctly
  optional, but incorrectly has `condition: {"kind": "conditional_effect"}`.
  The condition gates the counter effect, not the sacrifice.
- `Bolg of the North`: Oracle says "you may sacrifice another creature. When
  you do, Bolg deals damage..." The sacrifice is optional; the later trigger
  concerns the damage effect. The generated sacrifice record still has
  `condition: {"kind": "conditional_effect"}`.
- `The Sackville-Bagginses`: Oracle says "you may sacrifice another creature or
  artifact. If you do, draw a card..." The sacrifice is optional, not
  conditional on itself.
- `Elven Passage`: Oracle activation cost includes "Sacrifice this land", then
  the effect says "You may behold an Elf. If you do, untap that land." The
  generated sacrifice cost has `condition: {"kind": "conditional_effect"}`,
  but the cost is unconditional once the ability is activated.

Required correction:

- Derive the condition for `SACRIFICE` from the sacrifice phrase and its true
  antecedent, not the full line containing later payoff text.
- For "you may sacrifice..." records, use `optional: true` and no condition
  unless the sacrifice itself is independently gated.
- For activated costs, do not attach later effect-side `If you do` conditions
  to the cost record.
- Add regression tests asserting `condition is None` for `Rhovanion Rampager`,
  `Bolg of the North`, `The Sackville-Bagginses`, and `Elven Passage`.

### 2. Conditional self-sacrifice records do not preserve their actual gate

Impact: authoritative structured semantics.

The conditional self-sacrifice records preserve that the sacrifice is
conditional, but not the predicate that makes it happen. This is not enough to
distinguish materially different Oracle gates.

Concrete examples:

- `The Misty Mountains Cold`: Oracle says "Then if you control four or more
  Treasures, sacrifice this Saga." The generated record has only
  `condition: {"kind": "conditional_effect"}`. It does not preserve
  `control four or more Treasures`.
- `Last Light of Durin's Day`: Oracle says "If it has six or more quest
  counters on it, sacrifice it." The generated record again has only
  `condition: {"kind": "conditional_effect"}` and loses the six-or-more quest
  counter threshold.

Required correction:

- Preserve the specific gate for conditional self-sacrifice effects, at least
  as structured detail on the `condition`.
- Suggested minimum representations:
  - `The Misty Mountains Cold`: condition detail for controlling four or more
    Treasures.
  - `Last Light of Durin's Day`: condition detail for six or more quest counters
    on the source enchantment.
- Avoid `cost_context: "unsupported"` for these ordinary resolution effects if
  the record is considered extracted.
- Add tests that fail if these records contain only the generic
  `conditional_effect` marker.

## Repaired Prior Findings

The accepted Phase 4b record set remains byte-identical, including the repaired
`Silvan Reveler`, `Down, Down to Goblin-town`, and `The Master of Lake-town`
records from `PHASE4_review_pt7`.

## Required Corrections

1. Scope `SACRIFICE` conditions to the operation being extracted.
2. Remove false `conditional_effect` conditions from optional sacrifice effects
   and activated sacrifice costs where the condition belongs to a later payoff.
3. Preserve the actual predicates for mandatory conditional self-sacrifice.
4. Regenerate `effect_records.jsonl`, `reports/effect_semantics.md`, and
   `reports/effect_reconciliation.md`.
5. Keep accepted Phase 4a/4b records byte-identical unless a review or human
   decision explicitly authorizes a change.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- Direct JSON assertions that:
  - `Rhovanion Rampager`, `Bolg of the North`, and `The Sackville-Bagginses`
    have optional sacrifice records without a self-referential
    `conditional_effect` condition.
  - `Elven Passage` has an unconditional activated sacrifice cost record.
  - `The Misty Mountains Cold` records the "control four or more Treasures"
    condition.
  - `Last Light of Durin's Day` records the "six or more quest counters"
    condition.
  - `Crude Bent Blade`, `Bolg's Company`, and the accepted Phase 4b records
    remain correct.

## Phase Proceed Status

This Phase 4c implementation commit is not accepted. Phase 4 may continue only
with a repair commit addressing the blocking sacrifice-condition findings or
with an explicit human decision to refine the phase specification.
