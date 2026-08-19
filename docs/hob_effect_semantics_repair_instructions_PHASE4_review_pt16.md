---
phase: Phase 4
iteration: pt16
reviewed_commit: cec67643efd6ef13a3eabe9302c8001727f9e669
parent_commit: 8a840d39b290632ecae3999aab844eb90750ef1d
review_commit: PENDING_IN_THIS_COMMIT
verdict: ACCEPT
blocking_findings: 0
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: ACCEPT

Reviewed implementation commit `cec67643efd6ef13a3eabe9302c8001727f9e669`
(`Effect-semantics Phase 4e repair 2: address review 8a840d3
(chosen-target return not projected)`) against parent
`8a840d39b290632ecae3999aab844eb90750ef1d`.

The commit resolves the sole pt15 blocker. The Eagles Are Coming! record is
retained with its owner restriction, chosen-target binding, and kicked quantity
alternative, while its runtime-bound target is explicitly excluded from static
card-pair projection. Ordinary RETURN effects continue to project normally.
Phase 4e is accepted as a bounded slice. This review does not declare the
whole Phase 4 closed.

## Evidence Inspected

- Exact commit metadata, parent diff, changed source, regression tests,
  generated effect records, pair projection, pair index, and reports.
- `src/hobkg/effect_semantics.py` projection disposition for
  `binding.kind == "chosen_target"`.
- Direct records for The Eagles Are Coming!, The Mountain-king's Return,
  Eagle's Rescue, and the repaired graveyard self-returns.
- Direct projection counts and pair-index rows for the Eagles source.
- Reconciliation at `(clause_id, family)` granularity.

## Tests and Commands Run

- `git fetch origin`
- `git diff --check 8a840d39..cec67643`
- Targeted Phase 4/RETURN suite: `150 passed`.
- Full suite: `420 passed`.
- `python -m hobkg.cli effect-reconcile`: `337` clause/family pairs,
  `227` extracted, `4` deferred, `0` unresolved.
- Frozen manifest verification: `frozen_failures 0`.
- Two `python -m hobkg.cli effect-build` runs: byte-identical.
  Hashes: `effect_records=36804534690b453b148f1e27e51d664e4ebe9270426724d655d3d8a3cf9e9c8b`,
  `card_pair_projection_effect=3da8fe4d5c115e82e94d891c3b541668396b922df375514b96b304cb68249264`,
  `pair_index=6db68fa1983b08a1958cf50c02fd168963be005d872ab418870615a34d8e5e27`.
- Accepted Phase 4a-4d record subset unchanged from
  `2b06642166571bddb59de368b62eab6784d4db08`: hash
  `f6a3cc60dab108e627704c79e5e07fed5b6ff86f1640a15a3750a805348e6958`,
  `102` records.
- Non-RETURN projection subset unchanged from the same accepted baseline:
  hash `a06a9959abd4e06887792502f910920241c938bab96c7b8e8a4e506c274b5b38`,
  `8039` pairs.

## Frozen-Artifact Status

All protected artifacts still match `data/graph_global/frozen_manifest.json`.
No frozen-baseline change was detected.

## Findings

None blocking or nonblocking.

The prior blocker is resolved as follows:

- The structured Eagles RETURN record retains `owner: "you"`,
  `binding: {"kind": "chosen_target", "of": "you"}`,
  `quantity: "1"`, and `quantity_alt: {"non_kicked": "1", "kicked": "any"}`.
- It carries `projection: "not_projected (bound to a prior chosen target)"`.
- It emits zero `CAN_RETURN` pairs, avoiding the previous generic 112-card
  false-positive projection.
- Reconciliation still counts the clause as extracted rather than silently
  dropping it.
- The source-independent implementation branches on the declarative binding
  kind, not on a card name, UUID, or audited pair.
- Ordinary RETURN projection remains active: The Mountain-king's Return
  projects to 65 mana-value-eligible creature cards; other non-bound RETURN
  sources remain represented.

## Acceptance Tests For Future Changes

1. Preserve the Eagles structured record and explicit non-projection reason.
2. Ensure no generic `CAN_RETURN` pair is emitted for a chosen-target-bound
   effect unless a future schema can represent the runtime object identity.
3. Keep ordinary RETURN projection and Mountain-king's mana-value filtering
   intact.
4. Run targeted and full tests, reconciliation, frozen-manifest verification,
   and two deterministic effect builds.
5. Confirm accepted Phase 4a-4d records and non-RETURN projections remain
   unchanged.

## Phase Status

Phase 4e RETURN/recursion is accepted as a bounded implementation slice.
Phase 4 as a whole remains open for any remaining draw, discard, sacrifice,
life, mill, search, counterspell, resource, and later phase work.
