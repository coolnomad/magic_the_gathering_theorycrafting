---
protocol: review_event_protocol_v1
role: reviewer
phase: Phase 4
iteration: pt18
reviewed_commit: a8ead2f780fa6f0ef79fd6e6b30f0c333bf3f962
parent_commit: 107060c280526a73af01def1993c3210ffcd7da8
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 1
nonblocking_findings: 0
---

# Phase 4f repair review

Reviewed implementation commit `a8ead2f780fa6f0ef79fd6e6b30f0c333bf3f962` against parent `107060c280526a73af01def1993c3210ffcd7da8`.

## Verdict

REPAIR. The commit fixes both pt17 blockers for `Settle the Wreckage` and `Gollum the Abandoned`, but its generalized controller-detection branch regresses the existing `Celebrate the Mountain-king` EXILE record by losing its `for each opponent` participant semantics.

## Blocking finding

### Celebrate the Mountain-king loses the per-opponent mass-edict binding

The Oracle text is: “When this enchantment enters, for each opponent, exile up to one target nonland permanent that player controls until this enchantment leaves the battlefield.” In the reviewed commit, the generated record now has `participant: "controller"` and `selector.controller: "controller"`. The parent record had `participant: "each_opponent"`; the new branch at `src/hobkg/effect_semantics.py:1228-1231` matches the embedded phrase `that player controls` and overwrites the participant with `controller`.

This drops the outer `for each opponent` scope and changes a per-opponent edict into an unspecified controller-bound effect. It also changes an existing authoritative record outside the two pt17 repairs. The record must retain the outer participant (`each_opponent`) while expressing that the selected permanent is controlled by that opponent, using the repository's established participant/controller representation.

Evidence:

- Direct extraction from the reviewed commit returns `participant: "controller"`, `selector.controller: "controller"` for `Celebrate the Mountain-king`.
- `data/normalized/faces.jsonl` contains the explicit `for each opponent` Oracle clause.
- The change is introduced by the generic `that player controls` branch in `src/hobkg/effect_semantics.py`, not by the requested Settle or Gollum correction.
- The focused exile/return tests pass (`30 passed`), but no test asserts that Celebrate preserves `each_opponent`.

Repair requirements:

- Preserve `participant: "each_opponent"` for Celebrate's mass-edict effect.
- Preserve the selected permanent's controller relation to each iterated opponent without replacing the outer participant with `controller`.
- Add a regression test for the full participant/controller semantics and confirm the Settle and Gollum repairs remain fixed.

## Verification performed

- `pytest -q tests/test_effect_exile.py tests/test_effect_return.py`: 30 passed.
- `git diff --check a8ead2f^ a8ead2f`: clean.
- Full `pytest -q` was attempted but ended with 431 passed and 2 unrelated generated-artifact/infrastructure failures (`test_suppressions_remove_the_wrong_relations` and `test_pair_index_is_complete_37249`); this does not alter the focused semantic finding.

## Acceptance condition

After repair, rerun the focused and full suites, reconciliation, and two deterministic builds. Confirm the Settle target-player/attacking predicate and Gollum graveyard zone fixes, while keeping Celebrate's `each_opponent` binding and accepted prior-family artifacts unchanged.

