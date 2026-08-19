---
protocol: review_event_protocol_v1
role: reviewer
phase: Phase 4
iteration: pt17
reviewed_commit: c107682d7ec82dcd2e85d9cce8bc96be2cf8336e
parent_commit: ea7c3c7a348facc458448d2d7c9a6153216e5687
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 2
nonblocking_findings: 0
---

# Phase 4f EXILE review

Reviewed implementation commit `c107682d7ec82dcd2e85d9cce8bc96be2cf8336e` against parent `ea7c3c7a348facc458448d2d7c9a6153216e5687`.

## Verdict

REPAIR. The bounded EXILE/blink implementation has useful coverage and the full test suite passes, but two authoritative records violate mandatory zone and binding semantics. Phase 4f is not accepted until both are corrected and regression-tested.

## Blocking findings

### 1. Settle the Wreckage loses the target-player and attacking restrictions

The generated `CAN_EXILE` record for `Settle the Wreckage` has `participant: "you"`, `selector.controller: "any"`, and an empty `selector.predicates` object. Its quantity is `all`, but it does not encode “all attacking creatures target player controls.” The committed Oracle text is explicit: “Exile all attacking creatures target player controls.” The resulting projection therefore permits arbitrary HOB creatures instead of only attacking creatures controlled by the selected player, and it does not bind the exile operation to the same `target_player` used by the subsequent variable-count search.

Evidence:

- `data/graph_global/effect_records.jsonl` records the Settle exile with `participant: "you"`, `controller: "any"`, and no `attacking` predicate.
- `src/hobkg/effect_semantics.py:1220-1233` builds the selector from only the object phrase and derives the participant independently at the match start, so the embedded `target player controls` text is not preserved.
- `tests/test_effect_exile.py:28-31` checks only creature type, quantity, and zones; it does not assert target-player binding, controller restriction, or `predicates.attacking`.

Repair requirements:

- Bind the exile participant to `target_player`.
- Preserve the selected-player controller restriction in the selector and preserve the `attacking` predicate.
- Keep the Settle search's variable quantity bound to the number of those exiled objects and add a negative projection test for nonattacking/nonmatching creatures.

### 2. Gollum's graveyard exile has the wrong source zone

The generated generic-card record for `Gollum the Abandoned` says `source_zone: "battlefield"` and `selector.zone: "battlefield"`, although the Oracle text is “exile up to one target card from an opponent's graveyard.” The record is correctly retained as non-projected because the card class is generic, but a non-projected record still must preserve its authoritative zone and participant restrictions. This is a material zone-transition error, not a projection-policy choice.

Evidence:

- `data/graph_global/effect_records.jsonl` records Gollum's `EXILE` with battlefield as both source zone and selector zone.
- `src/hobkg/effect_semantics.py:1170-1172` permits only `your`, `their`, `an?`, or `its owner's` as a source-zone prefix. It cannot consume `an opponent's`, so the optional source-group fails and line 1218 defaults to `battlefield`.
- `tests/test_effect_exile.py:45-51` checks only generic-card non-projection and does not assert `graveyard` or opponent binding.

Repair requirements:

- Parse possessive participant phrases such as `an opponent's` when identifying a source zone.
- Preserve `source_zone: "graveyard"` and `selector.zone: "graveyard"`, plus the opponent restriction, while retaining the explicit generic-card non-projection disposition.
- Add a direct regression assertion for the zone and participant/owner restriction.

## Verification performed

- `pytest -q`: 431 passed.
- `git diff --check c107682^ c107682`: clean.
- Direct inspection of the committed generated records confirmed both blockers above.

The passing suite does not establish acceptance because its new EXILE tests omit the two mandatory restrictions. Existing accepted Phase 4a-4e behavior should remain byte-identical in the repair, apart from the explicitly corrected EXILE/blink records and projections.

## Acceptance condition

After a repair commit, rerun the full suite, reconciliation, and two clean deterministic builds. Confirm that Settle projects only the intended attacking creatures under the target-player binding, Gollum retains the graveyard source zone and opponent restriction without generic projection, and accepted prior-family records and unrelated projections remain unchanged.

