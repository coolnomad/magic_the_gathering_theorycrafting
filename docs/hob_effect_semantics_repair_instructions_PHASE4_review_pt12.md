---
phase: Phase 4
iteration: pt12
reviewed_commit: 203315dc40a9c54f6196fca7bfffecf388db5ac2
parent_commit: db7751f75b6831e511fbe5ab0bce5d979244ed56
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 2
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `203315dc40a9c54f6196fca7bfffecf388db5ac2`
(`Effect-semantics Phase 4d repair: address review db7751f (search zone +
antecedent bindings)`) against parent
`db7751f75b6831e511fbe5ab0bce5d979244ed56`.

The commit repairs the three blocking findings from
`PHASE4_review_pt11`: searched selectors now use the searched zone instead of
`battlefield`, `Settle the Wreckage` has an explicit "that many" binding to the
prior exile count, and `Last Light of Durin's Day` is gated by a prior action
rather than only a generic conditional marker. Full tests pass, the frozen
manifest is clean, and the generated files are deterministic.

However, direct review of all generated `SEARCH` records found remaining
authoritative-search contradictions. Phase 4d still needs repair before
acceptance.

## Evidence Inspected

- `git status --short --branch`
- `git log --oneline --decorate -8 origin/main`
- `git show --stat --summary --format=fuller 203315dc40a9c54f6196fca7bfffecf388db5ac2`
- `git show -s --format=full 203315dc40a9c54f6196fca7bfffecf388db5ac2`
- `git diff --check db7751f75b6831e511fbe5ab0bce5d979244ed56..203315dc40a9c54f6196fca7bfffecf388db5ac2`
- `git diff --name-status db7751f75b6831e511fbe5ab0bce5d979244ed56..203315dc40a9c54f6196fca7bfffecf388db5ac2`
- `git diff db7751f75b6831e511fbe5ab0bce5d979244ed56..203315dc40a9c54f6196fca7bfffecf388db5ac2 -- src/hobkg/effect_semantics.py`
- `git diff db7751f75b6831e511fbe5ab0bce5d979244ed56..203315dc40a9c54f6196fca7bfffecf388db5ac2 -- tests/test_effect_search.py`
- `git diff db7751f75b6831e511fbe5ab0bce5d979244ed56..203315dc40a9c54f6196fca7bfffecf388db5ac2 -- data/graph_global/effect_records.jsonl`
- Direct JSON queries over every generated `SEARCH` record in
  `data/graph_global/effect_records.jsonl`.
- Direct Oracle comparison from `data/normalized/faces.jsonl` for every
  generated `SEARCH` card.
- Direct JSON query over `card_pair_projection_effect.jsonl` for
  `SEARCHES_FOR`.
- Portability search for audited search-card names in
  `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_search.py tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: `129 passed`.
- `pytest -q`
  - Result: `399 passed`.
- Frozen manifest SHA-256 verification against
  `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- Direct comparison of accepted Phase 4a/4b/4c records
  (`DRAW`, `GAIN_LIFE`, `LOSE_LIFE`, `DISCARD`, `MILL`, `SACRIFICE`) between
  accepted commit `42d5000` and reviewed commit `203315d`
  - Result: same 91-record subset hash,
    `c0ddae1393fb6f5551cf0b935ef13fa30fcc7edb9ee3bfcc3c7c6ac534c34f1e`.
- Direct comparison of non-search pair projections between accepted commit
  `42d5000` and reviewed commit `203315d`
  - Result: same 7,950-pair subset hash,
    `460296b52b187b2a42beb4b3e90f442c0d594ba73edeaa508ca7d852bfc2586c`.
- Direct projection query for `SACRIFICES`, `DISCARDS_CARDS`, `MILLS_CARDS`,
  `DRAWS_CARDS`, `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no participant/resource/sacrifice fan-out emitted in
    `card_pair_projection_effect.jsonl` or `pair_index.jsonl`.
- `python -m hobkg.cli effect-reconcile`
  - Result: 324 clause/family pairs, 218 extracted, 4 deferred, 0 unresolved.
- `python -m hobkg.cli effect-build`, run twice
  - Result both times: 222 effects, 135 faces, 8,039 pair projections,
    including 89 `SEARCHES_FOR` pairs.
  - Byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `7686ad90c7ccafb93e74d5874c47bb57b5207ef4be1e45a3d6484d4ca8f8166`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `61c409d350d6e1d3e340c03ab8ae4894b7850df9eb7ed089300cd4d087a25e35`
    - `data/graph_global/pair_index.jsonl`
      `4e93f673be65e051913ee7356c7410703551d34ce5f5168cc4889965f5be66ce`

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was
detected.

## Findings

### 1. `Troop of Ponies` collapses split destinations into one battlefield-tapped destination

Impact: authoritative structured semantics, pair projection, and future
execution semantics.

Oracle text:

`Search your library for up to two basic land cards, reveal them, put one onto
the battlefield tapped and the other into your hand, then shuffle.`

The generated `SEARCH` record preserves the library source, up-to-two quantity,
basic land selector, reveal, and shuffle. It does not preserve the destination
split. The record says:

- `quantity: "up_to_2"`
- `dest_zone: "battlefield"`
- `dest_tapped: true`
- no second destination, no per-object destination binding, and no indication
  that only one searched card goes to the battlefield while the other goes to
  hand.

This overstates the battlefield placement and makes the projection support read
as though every matching basic land searched by `Troop of Ponies` is put onto
the battlefield tapped. The Oracle clause instead has two destination roles:
one selected basic land goes to battlefield tapped and another selected basic
land goes to hand. If only one card is found, only the applicable chosen object
can move; the record still needs to preserve the split object roles.

Required correction:

- Represent split searched objects and destinations explicitly, for example
  separate object variables or a structured `destinations` list with counts,
  zones, tapped flags, and same-search binding.
- Ensure `SEARCHES_FOR` supports for `Troop of Ponies` do not imply that all
  found basic lands are battlefield-tapped outputs.
- Add a regression test that checks `Troop of Ponies` has one searched basic
  land destination of `battlefield` with `tapped: true` and one searched basic
  land destination of `hand`.

### 2. `Last Light of Durin's Day` makes a conditional shuffle unconditional

Impact: authoritative structured semantics and future execution semantics.

Oracle text:

`If you do, search your hand and/or library for a Dragon card and put it onto
the battlefield. If you search your library this way, shuffle.`

The repaired record correctly has:

- `source_zone: "hand_and_library"`
- `selector.zone: "hand_and_library"`
- `condition: {"kind": "prior_action_taken", ...}`
- `dest_zone: "battlefield"`

But it still has `shuffle: true` with no condition. Because the search can be
satisfied from hand, the shuffle is conditional on actually searching the
library. The record therefore overstates the operation by making a library
shuffle mandatory whenever the search effect resolves.

Required correction:

- Preserve the shuffle condition for hand/library searches, for example
  `shuffle_condition: {"kind": "searched_zone", "zone": "library"}` or an
  equivalent structured binding.
- Add a regression test that `Last Light of Durin's Day` does not encode an
  unconditional shuffle when the searched source is `hand_and_library`.

## Repaired Findings From pt11

The following pt11 blockers are now resolved in the reviewed commit:

- Every generated `SEARCH` selector has a zone matching `source_zone`, and none
  of the generated search selectors still use `battlefield`.
- `Settle the Wreckage` has
  `quantity_formula: {"kind": "variable", "source": "prior_exile_count",
  "of": "target_player", "binding": "the number of attacking creatures exiled
  this way"}`.
- `Last Light of Durin's Day` no longer uses only
  `{"kind": "conditional_effect"}` for the search; it is now represented as a
  prior-action gate.

## Required Corrections

1. Preserve split search destinations and per-object destination bindings for
   `Troop of Ponies`.
2. Preserve the conditional-library-search shuffle for `Last Light of Durin's
   Day`.
3. Regenerate affected generated artifacts after the repair.
4. Keep accepted Phase 4a/4b/4c records and non-search projections
   byte-identical unless explicitly authorized otherwise.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_search.py tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- Direct JSON assertions that:
  - all `SEARCH` selector zones are compatible with `source_zone`;
  - `Settle the Wreckage` still binds "that many" to exiled attacking
    creatures controlled by the target player;
  - `Last Light of Durin's Day` still binds the search to the prior
    self-sacrifice and conditionally shuffles only if the library was searched;
  - `Troop of Ponies` preserves one searched basic land going to battlefield
    tapped and another going to hand;
  - accepted Phase 4a/4b/4c records remain byte-identical;
  - non-search pair projections remain byte-identical.

## Phase Proceed Status

This Phase 4d implementation commit is not accepted. Phase 4 may continue only
with a repair commit addressing the blocking SEARCH findings or with an
explicit human decision to refine the Phase 4d abstraction boundary.
