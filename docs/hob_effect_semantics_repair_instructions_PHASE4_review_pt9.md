---
phase: Phase 4
iteration: pt9
reviewed_commit: 143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1
parent_commit: a6d1cd65d7c94b206a8d01b818667dec68d7f470
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 1
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed implementation commit `143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1`
(`Effect-semantics Phase 4c repair: address review a6d1cd6`) against parent
`a6d1cd65d7c94b206a8d01b818667dec68d7f470`.

The two blocking findings from `PHASE4_review_pt8` are repaired: later payoff
conditions no longer gate the sacrifice operation itself, and conditional
self-sacrifice records now preserve the specific gates for `The Misty Mountains
Cold` and `Last Light of Durin's Day`. However, direct inspection found one
remaining sacrifice-cost completeness defect: `Elven Passage` drops the printed
`Pay 1 life` co-cost from the structured cost payload. This affects
authoritative structured semantics and blocks Phase 4c acceptance.

## Evidence Inspected

- `git status --short --branch`
- `git fetch origin`
- `git log --oneline --decorate -16 --all`
- `git show --stat --summary --format=fuller 143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1`
- `git show -s --format=full 143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1`
- `git diff --check a6d1cd65d7c94b206a8d01b818667dec68d7f470..143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1`
- `git diff --name-status a6d1cd65d7c94b206a8d01b818667dec68d7f470..143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1`
- `git diff a6d1cd65d7c94b206a8d01b818667dec68d7f470..143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1 -- src/hobkg/effect_semantics.py`
- `git diff a6d1cd65d7c94b206a8d01b818667dec68d7f470..143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1 -- tests/test_effect_sacrifice.py`
- `git diff a6d1cd65d7c94b206a8d01b818667dec68d7f470..143ec1df22a0d8c1ad5cc2a4b6520a925d9cf1f1 -- data/graph_global/effect_records.jsonl`
- Direct JSON queries over every generated `SACRIFICE` record.
- Oracle text from `data/normalized/faces.jsonl` for every generated
  `SACRIFICE` record.
- Portability search for audited card names in `src/hobkg/effect_semantics.py`.

## Tests and Commands Run

- `pytest tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - First parallel run overlapped with the full suite and hit generated-file
    interference.
  - Isolated rerun result: `111 passed`.
- `pytest -q`
  - Result: `381 passed`.
- Frozen manifest SHA-256 verification against
  `data/graph_global/frozen_manifest.json`
  - Result: `frozen_failures 0`.
- Direct projection query for `SACRIFICES`, `DISCARDS_CARDS`, `MILLS_CARDS`,
  `DRAWS_CARDS`, `GAINS_LIFE`, and `LOSES_LIFE`
  - Result: no sacrifice/resource relations emitted in
    `card_pair_projection_effect.jsonl` or `pair_index.jsonl`.
- Direct comparison of accepted Phase 4a/4b participant records
  (`DRAW`, `GAIN_LIFE`, `LOSE_LIFE`, `DISCARD`, `MILL`) between `b0759cb` and
  `143ec1d`
  - Result: same 69-record subset hash,
    `dae5c1a33cb3d2fd5e75814d7a7d846ebcc771d95b4f885bd779ac708982d3cc`.
- `python -m hobkg.cli effect-reconcile`
  - Result: 311 clause/family pairs, 207 extracted, 4 deferred, 0 unresolved.
- `python -m hobkg.cli effect-build`, run twice
  - Result: 211 effects, 132 faces, 7,950 pair projections.
  - Byte-identical hashes:
    - `data/graph_global/effect_records.jsonl`
      `781f21247c0e13256d3086af29f8e4ca6b0f23c457efb506bcef6cd323103a9c`
    - `data/graph_global/card_pair_projection_effect.jsonl`
      `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`

## Frozen-Artifact Status

The protected frozen graph artifacts still match
`data/graph_global/frozen_manifest.json`. No frozen-baseline change was detected.

## Findings

### 1. `Elven Passage` sacrifice cost drops the printed life-payment co-cost

Impact: authoritative structured semantics.

Oracle text:

`{T}, Pay 1 life, Sacrifice this land: Search your library for a basic land card,
put it onto the battlefield tapped, then shuffle. You may behold an Elf. If you
do, untap that land.`

The generated `SACRIFICE` record correctly removes the false
`conditional_effect` from pt8 and identifies the operation as an activated cost:

```json
"name": "Elven Passage",
"op": "SACRIFICE",
"role": "cost",
"cost_context": "activated_ability",
"condition": null,
"cost": {
  "alt": [{
    "all": [
      {"tap": true},
      {"sacrifice": {"self": true, "quantity": 1}}
    ]
  }]
}
```

This structured cost omits the mandatory `Pay 1 life` atom. Other activated
sacrifice records preserve their co-costs, such as mana and tap on `Lake-town`,
`Goblin-town`, `Iron Hills`, `Mirkwood`, `Giant's Boulder`, and `Troop of
Ponies`. The life payment is therefore a real cost-vs-effect semantic that is
lost only because the cost parser does not currently emit a life-payment atom.

This is not a projection issue and does not affect frozen artifacts, but it
does affect the authoritative structured semantics for the extracted sacrifice
outlet.

Required correction:

- Include a structured life-payment cost atom for activated sacrifice records
  whose printed cost contains `Pay N life`.
- Add a regression test for `Elven Passage` asserting that its `cost.alt[0].all`
  contains tap, pay-life, and self-sacrifice atoms.
- Preserve the pt8 repairs: `Elven Passage.condition` must remain `null`, and
  the later `If you do` must not gate the sacrifice cost.

## Repaired Prior Findings

The pt8 findings are repaired in the generated records:

- `Rhovanion Rampager`, `Bolg of the North`, and `The Sackville-Bagginses` now
  have optional sacrifice records with `condition: null`.
- `Elven Passage` no longer attaches the later payoff `If you do` to the
  sacrifice cost.
- `The Misty Mountains Cold` now records a `controls_count` gate for controlling
  four or more Treasures.
- `Last Light of Durin's Day` now records a `counter_threshold` gate for six or
  more quest counters.

These repairs should be preserved in the next commit.

## Required Corrections

1. Add life-payment co-cost extraction to the structured `SACRIFICE` cost for
   `Elven Passage` and any future sacrifice outlet with the same pattern.
2. Add direct tests for this cost atom while preserving the operation-scoped
   condition behavior from pt8.
3. Regenerate `effect_records.jsonl` and any affected reports.
4. Keep accepted Phase 4a/4b records byte-identical unless explicitly
   authorized otherwise.

## Acceptance Tests for the Next Commit

The next review should include at least these checks:

- `pytest tests/test_effect_sacrifice.py tests/test_effect_resource.py tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
- `pytest -q`
- Frozen manifest SHA-256 verification.
- Two consecutive `python -m hobkg.cli effect-build` runs with byte-identical
  generated hashes.
- `python -m hobkg.cli effect-reconcile`.
- Direct JSON assertions that:
  - `Elven Passage` has a structured `Pay 1 life` cost atom in the same
    activated-cost branch as tap and self-sacrifice.
  - `Elven Passage.condition` remains `null`.
  - `Rhovanion Rampager`, `Bolg of the North`, and `The Sackville-Bagginses`
    remain optional and ungated at the sacrifice operation.
  - `The Misty Mountains Cold` and `Last Light of Durin's Day` keep their
    specific conditional self-sacrifice gates.
  - Accepted Phase 4a/4b records remain byte-identical.

## Phase Proceed Status

This Phase 4c repair commit is not accepted. Phase 4 may continue only with a
repair commit addressing the missing life-payment cost atom or with an explicit
human decision to refine the phase specification.
