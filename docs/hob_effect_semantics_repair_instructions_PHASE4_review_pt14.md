---
phase: Phase 4
iteration: pt14
reviewed_commit: a5e4be8f8985c50d4eb39443b56c2f675ab2846e
parent_commit: ec73e08de560c875f11487e253165bf2711b4288
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 4
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `a5e4be8f8985c50d4eb39443b56c2f675ab2846e`
(`Effect-semantics Phase 4e: RETURN / recursion (bounce + reanimation)`)
against parent `ec73e08de560c875f11487e253165bf2711b4288`.

The commit adds a deterministic `RETURN` / `CAN_RETURN` slice, keeps the
accepted Phase 4a-4d records byte-identical, keeps non-return pair projections
byte-identical, passes the full test suite, and leaves the frozen graph intact.
However, several generated RETURN records still contradict Oracle text or drop
mandatory bindings. Phase 4e needs repair before acceptance.

## Evidence Inspected

- `git status --short --branch`
- `git fetch origin`
- `git log --oneline --decorate -10 origin/main`
- `git show --stat --summary --format=fuller a5e4be8f8985c50d4eb39443b56c2f675ab2846e`
- `git show -s --format=full a5e4be8f8985c50d4eb39443b56c2f675ab2846e`
- `git diff --check ec73e08de560c875f11487e253165bf2711b4288..a5e4be8f8985c50d4eb39443b56c2f675ab2846e`
- `git diff --name-status ec73e08de560c875f11487e253165bf2711b4288..a5e4be8f8985c50d4eb39443b56c2f675ab2846e`
- `git diff ec73e08de560c875f11487e253165bf2711b4288..a5e4be8f8985c50d4eb39443b56c2f675ab2846e -- src/hobkg/effect_semantics.py`
- `git diff ec73e08de560c875f11487e253165bf2711b4288..a5e4be8f8985c50d4eb39443b56c2f675ab2846e -- tests/test_effect_return.py`
- Direct JSON queries over every generated `RETURN` record in
  `data/graph_global/effect_records.jsonl`.
- Direct Oracle comparison from `data/normalized/faces.jsonl` for every
  generated `RETURN` card.
- Direct JSON query over `data/graph_global/effect_census.jsonl` for all
  `return_move` census rows.
- Direct JSON queries over `card_pair_projection_effect.jsonl` for
  `CAN_RETURN` projection support.
- Portability search for audited return-card names in
  `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_return.py tests/test_effect_search.py tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: `144 passed`.
- `pytest -q`
  - Result: `414 passed`.
- Frozen manifest SHA-256 verification against
  `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- Direct comparison of accepted Phase 4a-4d records
  (`DRAW`, `GAIN_LIFE`, `LOSE_LIFE`, `DISCARD`, `MILL`, `SACRIFICE`,
  `SEARCH`) between accepted commit `2b06642` and reviewed commit `a5e4be8`
  - Result: same 102-record subset hash,
    `f6a3cc60dab108e627704c79e5e07fed5b6ff86f1640a15a3750a805348e6958`.
- Direct comparison of non-return pair projections between accepted commit
  `2b06642` and reviewed commit `a5e4be8`
  - Result: same 8,039-pair subset hash,
    `a06a9959abd4e06887792502f910920241c938bab96c7b8e8a4e506c274b5b38`.
- Direct projection query for `SACRIFICES`, `DISCARDS_CARDS`, `MILLS_CARDS`,
  `DRAWS_CARDS`, `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no participant/resource/sacrifice fan-out emitted in
    `card_pair_projection_effect.jsonl` or `pair_index.jsonl`.
- `python -m hobkg.cli effect-reconcile`
  - Result: 337 clause/family pairs, 227 extracted, 4 deferred, 0 unresolved.
- `python -m hobkg.cli effect-build`, run twice
  - Result both times: 231 effects, 138 faces, 8,654 pair projections,
    including 615 `CAN_RETURN` pairs.
  - Byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `6893fb3de14b9c5e5022a29006271a5f8ac64c045e3599ebe914cfb2eab94273`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `9f8150b946b63e2bb8be715caf2cdd31da05b2480230536560ec409f4e7d675b`
    - `data/graph_global/pair_index.jsonl`
      `e91285701f24496032010b6143d842adefc9c6076ade676cb7ca7568af34c98a`

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was
detected.

## Findings

### 1. `The Mountain-king's Return` drops the mana-value restriction

Impact: authoritative structured semantics and pair projection.

Oracle text:

`II — Return target creature card with mana value 3 or less from your graveyard
to the battlefield.`

The generated `RETURN` record has a graveyard creature-card selector, but its
selector predicates are empty:

- `selector.card_types: ["creature"]`
- `selector.quantifier: "target"`
- `selector.zone: "graveyard"`
- `selector.predicates: {}`

The `CAN_RETURN` projection consequently fans out to 112 creature cards,
including high-mana-value cards. The record must preserve `mana value 3 or
less`, and the projection must use that predicate.

Required correction:

- Add a structured mana-value predicate, such as `mana_value_lte: 3`, to the
  selector.
- Ensure `CAN_RETURN` for `The Mountain-king's Return` only targets eligible
  creature cards.
- Add a regression test that fails if any projected target violates the
  mana-value restriction.

### 2. `The Eagles Are Coming!` loses the chosen-target, owner, and kicker-dependent quantity semantics

Impact: authoritative structured semantics, pair projection, and future
execution semantics.

Oracle text:

`Choose target creature you own. If this spell was kicked, instead choose any
number of target creatures you own. Return each chosen creature to your hand.`

The generated `RETURN` record is:

- `selector.card_types: ["creature"]`
- `selector.controller: "any"`
- `selector.owner: null`
- `selector.quantifier: "each"`
- `targeted: false`
- `quantity: "1"`
- no binding to the previously chosen target creature(s)
- no kicked alternative for "any number"

This drops the owner restriction and the targeting/choice antecedent, and it
misstates the kicked mode as a single-object return. The projection therefore
fans out to every creature card rather than the card identities that could be
creatures owned by the caster under the target-choice instruction.

Required correction:

- Preserve that the returned objects are the previously chosen target
  creature(s), not any creature on the battlefield.
- Preserve `owner: "you"` or an equivalent owned-by-caster restriction.
- Preserve the non-kicked one-target and kicked any-number alternative.
- Add tests for owner restriction, target/choice binding, and kicked quantity.

### 3. Graveyard self-return records keep a battlefield selector zone

Impact: authoritative structured semantics.

Several self-return effects correctly set `source_zone: "graveyard"` but keep
the `_self_selector()` default `selector.zone: "battlefield"`:

- `Silvan Reveler`: `Return this card from your graveyard to your hand.`
- `Gollum the Abandoned`: `Return this card from your graveyard to your hand.`
- `Eagle's Rescue`: `Return this card from your graveyard to the battlefield...`
- `Tom, Bert, and William`: `return them to the battlefield` after dying.

This is the same class of authoritative-zone contradiction that Phase 4d fixed
for SEARCH selectors. The moved object is in the graveyard when returned; the
selector should not say it is a battlefield object.

Required correction:

- Override self-return selector zones to match `source_zone` when the returned
  object is in the graveyard.
- Add a test that every `RETURN` record with `selector.self` has
  `selector.zone == source_zone`.

### 4. `Eagle's Rescue` drops the attached-to destination binding

Impact: authoritative structured semantics and future execution semantics.

Oracle text:

`Return this card from your graveyard to the battlefield attached to target
creature you control with power 1 or less.`

The generated `RETURN` record captures self-return from graveyard to
battlefield, but it has no attachment destination binding and no selector for
the target creature to which the Aura returns attached. The record therefore
loses a mandatory part of the destination semantics.

Required correction:

- Preserve the returned Aura's attached-to target, including
  `target creature you control with power 1 or less`.
- If attachment execution is deferred to another slice, keep a structured
  return record field that explicitly records the attachment destination as
  deferred-but-bound rather than silently dropping it.
- Add a regression test for the attached-to target selector.

## Required Corrections

1. Preserve and project the `mana value 3 or less` restriction for
   `The Mountain-king's Return`.
2. Preserve `The Eagles Are Coming!` chosen-target binding, owner restriction,
   and kicked any-number alternative.
3. Correct self-return selector zones for graveyard self-return records.
4. Preserve `Eagle's Rescue` attached-to destination binding.
5. Regenerate affected artifacts and keep accepted Phase 4a-4d records and
   unrelated pair projections byte-identical unless explicitly authorized.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_return.py tests/test_effect_search.py tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- Direct JSON assertions that:
  - `The Mountain-king's Return` has a mana-value-lte-3 selector predicate and
    does not project to invalid creature cards;
  - `The Eagles Are Coming!` preserves owned chosen target creatures and
    kicked any-number semantics;
  - every graveyard self-return selector has `selector.zone == source_zone`;
  - `Eagle's Rescue` records the attached-to target creature binding;
  - blink/exile-and-return and stack-object spell-bounce remain explicitly
    dispositioned until their respective slices;
  - accepted Phase 4a-4d records remain byte-identical;
  - non-return pair projections remain byte-identical.

## Phase Proceed Status

This Phase 4e implementation commit is not accepted. Phase 4 may continue only
with a repair commit addressing the blocking RETURN findings or with an
explicit human decision to refine the Phase 4e abstraction boundary.
