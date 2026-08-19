---
phase: Phase 4
iteration: pt15
reviewed_commit: 3ba48084c87c011e542b389e224edc764d5dcd3e
parent_commit: 7dcd692c7b26b7bd67834e7b72d50a4bd74002af
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 1
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `3ba48084c87c011e542b389e224edc764d5dcd3e`
(`Effect-semantics Phase 4e repair: address review 7dcd692 (RETURN
restrictions/bindings/zones)`) against parent
`7dcd692c7b26b7bd67834e7b72d50a4bd74002af`.

The commit repairs the four structured-record defects identified in pt14:
the Mountain-king mana-value predicate, Eagles ownership/choice/kicker
metadata, graveyard self-return zones, and Eagle's Rescue attachment target.
Those authoritative records are now materially improved. Phase 4e still
requires repair because the Eagles projection remains semantically broader
than its chosen-object binding.

## Evidence Inspected

- Exact commit metadata, parent diff, changed source, tests, generated records,
  projection artifacts, pair index, and effect report.
- All generated `RETURN` records, including The Mountain-king's Return, The
  Eagles Are Coming!, Silvan Reveler, Gollum the Abandoned, Eagle's Rescue,
  and Tom, Bert, and William.
- `src/hobkg/effect_schema.py` projection eligibility and
  `src/hobkg/effect_semantics.py` RETURN extraction.
- Oracle/card data in `data/normalized/cards.jsonl` and face records.
- Reconciliation at `(clause_id, family)` granularity.

## Tests and Commands Run

- `git fetch origin`
- `git diff --check 7dcd692..3ba4808`
- Targeted Phase 4/RETURN suite: `148 passed`.
- Full suite: `418 passed`.
- `python -m hobkg.cli effect-reconcile`: `337` clause/family pairs,
  `227` extracted, `4` deferred, `0` unresolved.
- Frozen manifest verification: `frozen_failures 0`.
- Two `python -m hobkg.cli effect-build` runs: byte-identical.
  Hashes: `effect_records=13777f47d16903be9b419ea09f20d0106b249e8d5194bf3eb375d5de6a1a7047`,
  `card_pair_projection_effect=673fde56ec1725b3c5af4d389e9b9568b0496ff52c7aaa8de498a133af6c19ec`,
  `pair_index=e751f2911de22dbea8c90632cb560f12e4c51e8679a3ea022699c904714e1f68`.
- Accepted Phase 4a-4d record subset unchanged from `2b06642166571bddb59de368b62eab6784d4db08`:
  hash `f6a3cc60dab108e627704c79e5e07fed5b6ff86f1640a15a3750a805348e6958`,
  `102` records.
- Non-RETURN projection subset unchanged from `2b06642166571bddb59de368b62eab6784d4db08`:
  hash `a06a9959abd4e06887792502f910920241c938bab96c7b8e8a4e506c274b5b38`,
  `8039` pairs.

## Frozen-Artifact Status

All protected artifacts still match `data/graph_global/frozen_manifest.json`.
No frozen-baseline change was detected.

## Findings

### Blocking: The Eagles Are Coming! still has an overbroad CAN_RETURN projection

Impact: authoritative pair projection and downstream execution semantics.
The structured record correctly preserves important information:

- `selector.owner: "you"`;
- `targeted: true`;
- `binding: {"kind": "chosen_target", "of": "you"}`;
- `quantity: "1"` with `quantity_alt: {"non_kicked": "1", "kicked": "any"}`.

However, `data/graph_global/card_pair_projection_effect.jsonl` still contains
`112` `CAN_RETURN` pairs for this source, one for every projected creature
card. The projection path in `src/hobkg/effect_semantics.py` calls
`matches_card()` and `project()`, while `matches_card()` does not apply
`selector.owner` and `project()` has no chosen-object identity or antecedent
representation. The generated projection therefore still treats

`Choose target creature you own. If this spell was kicked, instead choose any
number of target creatures you own. Return each chosen creature to your hand.`

as a generic ability to return every creature card, even though the effect is
bound to the previously chosen target creature or creatures. This is the same
projection defect pt14 explicitly required to be corrected; the new tests
assert the record fields but do not assert the projection disposition.

Required correction: either make the projection preserve the owner and chosen-
object semantics under the declared abstraction boundary, or explicitly
disposition this effect from `CAN_RETURN` projection while retaining the full
structured record and a reconciliation reason. Do not silently emit the broad
112-pair relation. Add a regression test that fails if this source retains a
generic all-creatures projection without an explicit documented disposition.

## Accepted Corrections

The following pt14 findings are corrected and independently verified:

- The Mountain-king's Return has `selector.predicates.mana_value_lte: 3` and
  projects to `65` eligible cards rather than `112`.
- The Eagles Are Coming! record has the owned target, chosen-target binding,
  and kicked any-number alternative.
- Self-return records with `source_zone: graveyard` use a graveyard selector.
- Eagle's Rescue preserves a deferred attachment selector for a creature you
  control with power 1 or less.

## Acceptance Tests For Next Commit

1. Query the Eagles structured record and verify owner, target binding, and
   kicked quantity remain present.
2. Query projections and prove that no generic all-creatures `CAN_RETURN`
   relation remains for The Eagles Are Coming!, or document an explicit
   non-projected/deferred disposition with reconciliation coverage.
3. Run the targeted and full test suites, including a projection regression for
   this exact failure.
4. Re-run reconciliation, frozen-manifest verification, and two deterministic
   effect builds.
5. Confirm accepted Phase 4a-4d records and non-RETURN projections remain
   unchanged.

## Phase Status

This review accepts the four pt14 record repairs but does not accept Phase 4e.
Phase 4 may not proceed to acceptance while the Eagles projection remains
overbroad. Acceptance of a later repair commit will still be bounded to Phase
4e; it will not by itself declare the whole Phase 4 closed.
