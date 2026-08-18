---
protocol: worker_reviewer_handshake_v1
role: reviewer
phase: Phase 4
iteration: pt3
reviewed_commit: 92ec14cf4d3ca1af8b58dcace7aef7f8fa206029
parent_commit: ac4d3ab8fb0e0ad9b40f0029504d651f6599fa0c
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 1
nonblocking_findings: 0
deferred_items: 0
---

# Verdict: REPAIR

Reviewed commit: `92ec14cf4d3ca1af8b58dcace7aef7f8fa206029` (`Effect-semantics Phase 4a repair 2: address review ac4d3ab (optionality + formula quantities)`)

Parent commit: `ac4d3ab8fb0e0ad9b40f0029504d651f6599fa0c` (`Review Phase 4 pt2: REPAIR d40c6f0`)

The pt2 optionality and formula-quantity blockers are fixed, and all pt1 repairs remain fixed. Phase 4a still needs one narrow repair: participant-effect conditions are still assigned from the whole clause, so an `if` belonging to a later or sibling instruction can incorrectly condition an earlier draw.

## Evidence Inspected

- Governing instructions and protocol:
  - `INSTRUCTIONS.md`
  - `docs/review_event_protocol.md`
  - `docs/hob_effect_semantics_repair_instructions.md`
  - `docs/phase4-requirements.md`
- Prior Phase 4 reviews:
  - `docs/hob_effect_semantics_repair_instructions_PHASE4_review_pt1.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE4_review_pt2.md`
- Reports and recent project record:
  - `reports/effect_census.md`
  - `reports/effect_reconciliation.md`
  - `reports/effect_semantics.md`
  - recent tail of `LABNOTEBOOK.md`
- Git/history:
  - `git status --short --branch`
  - `git fetch origin`
  - `git log --oneline --decorate -12 --all`
  - `git show --stat --summary 92ec14c`
  - `git diff --check ac4d3ab..92ec14c`
  - `git diff --name-status ac4d3ab..92ec14c`
  - `git diff --stat --summary ac4d3ab..92ec14c`
- Changed files:
  - `src/hobkg/effect_semantics.py`
  - `tests/test_effect_participant.py`
  - `data/graph_global/effect_records.jsonl`
  - append-only log/notebook entries
- Generated records inspected directly:
  - `data/graph_global/effect_records.jsonl`
  - `data/graph_global/card_pair_projection_effect.jsonl`
  - `data/graph_global/pair_index.jsonl`
  - `data/normalized/faces.jsonl`

## Tests And Commands Run

- `git diff --check ac4d3ab..92ec14c`
  - Passed.
- Source portability check:
  - `Select-String` for the reviewed card names in `src/hobkg/effect_semantics.py` found examples in comments/docstrings only, not card-name implementation branches.
- `pytest tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: 74 passed.
- Frozen manifest hash check against `data/graph_global/frozen_manifest.json`
  - Result: all protected frozen artifacts matched.
- Pair fan-out check:
  - `card_pair_projection_effect.jsonl` and `pair_index.jsonl` unchanged for effect projection; no deterministic `DRAWS_CARDS`, `GAINS_LIFE`, or `LOSES_LIFE` card-pair fan-out.
- `pytest -q`
  - Result: 344 passed in 39.96s.
- `python -m hobkg.cli effect-build`
  - Result: 172 effects on 121 faces; 7,950 pairs.
- `python -m hobkg.cli effect-reconcile`
  - Result: 244 `(clause_id, family)` pairs; 168 extracted; 4 deferred/nonexecutable; 0 unresolved.
- Two serial `python -m hobkg.cli effect-build` runs:
  - Stable `data/graph_global/effect_records.jsonl` SHA-256: `7af97162c70a095519f02c7a27167519060756888ead11591c43461a0b810397`
  - Stable `data/graph_global/card_pair_projection_effect.jsonl` SHA-256: `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`

## Frozen Artifact Status

Accepted. The frozen core remains byte-identical to `data/graph_global/frozen_manifest.json`.

Verified protected files:

- `data/graph/conditions.jsonl`
- `data/graph/edges.jsonl`
- `data/graph/gates.jsonl`
- `data/graph/nodes.jsonl`
- `data/graph_global/conditions.jsonl`
- `data/graph_global/edges.jsonl`
- `data/graph_global/nodes.jsonl`

No frozen-baseline change was detected.

## Resolved Findings

All Phase 4 pt1 blockers remain fixed:

- Reverent Howl and Meager Meal target-player records are targeted.
- Down, Down to Goblin-town and The Sackville-Bagginses target-opponent life loss records are targeted.
- Gleaming Splendor records two target players each drawing one card.
- Gandalf, Wandering Wizard records the drawing participant as owner.
- Supper for Spiders no longer emits immediate life gain from the quoted Food ability.
- Bard, King of Dale no longer emits the replaced draw event as direct `DRAW 1`.
- Gollum, Riddle Master's participant alternatives carry explicit `choose_one` mode metadata.

Both Phase 4 pt2 blockers are fixed:

- Old Thrush's mandatory life gain is `optional: false`.
- Ragged Short Spear and The Sackville-Bagginses draws are mandatory effects gated by `prior_action_taken`, not optional draw effects.
- The Master of Lake-town's draw count is formulaic: `amount: "formula"` with `quantity_formula.kind: "per_each"`.
- Balin, Loremaster and Uncover the Moon-Letters carry `quantity_formula` bindings for `X`.
- Uncover's own draw remains optional because `may` governs the draw verb.

## Finding

### Blocking 1: participant-effect conditions still leak across sibling instructions

Impact: authoritative structured semantics.

The repair correctly made optionality operation-scoped, but conditions still fall back to `_sch.condition(crange)` for the whole clause. This attaches an `if` from a later or sibling instruction to earlier draw records that are not actually conditional on that `if`.

Concrete Oracle examples:

> Balin, Loremaster: "Whenever Balin or another Dwarf you control enters, you may discard your hand. Draw X cards, where X is the number of cards discarded this way. If you have an enduring story, Balin deals X damage to each opponent."

Generated `DRAW` record:

```json
{
  "name": "Balin, Loremaster",
  "op": "DRAW",
  "amount": "X",
  "condition": {"kind": "conditional_effect"},
  "quantity_formula": {
    "kind": "variable",
    "var": "X",
    "binding": "the number of cards discarded this way"
  }
}
```

The enduring-story `if` gates the later damage to each opponent, not the draw. The draw is instead formula-bound to the prior discard count. A generic `conditional_effect` on the draw is inaccurate.

> Silvan Reveler: "When this creature enters, draw a card, then discard a card. If you discard a land card this way, put it from your graveyard onto the battlefield tapped."

Generated `DRAW` record:

```json
{
  "name": "Silvan Reveler",
  "op": "DRAW",
  "amount": "1",
  "condition": {"kind": "conditional_effect"}
}
```

The draw is unconditional on enter. The later `if` applies to moving the discarded land, not to drawing the card.

> Uncover the Moon-Letters: "Whenever you cast a noncreature spell, you may draw X cards, where X is the amount of mana spent to cast that spell. If you do, discard two cards."

Generated `DRAW` record:

```json
{
  "name": "Uncover the Moon-Letters",
  "op": "DRAW",
  "optional": true,
  "condition": {"kind": "conditional_effect"}
}
```

The `if you do` gates the later discard, not the optional draw itself. The draw should be optional with its X formula binding, not also conditioned by the later discard consequence.

Required correction: compute condition per operation/span, as the pt2 repair now does for optionality. Do not attach a later/sibling `if` to a participant effect unless that condition actually governs that operation. Preserve true conditions such as Beorn's "Then if you control three or more Bears, draw two cards", Azog's "If you controlled that creature, draw a card", Smaug's intervening-if trigger, Belladonna Took's resolution-count alternatives, and Plunder's cast-from-graveyard replacement.

## Concrete Oracle Examples

Correct after this repair:

- Old Thrush: mandatory life gain is no longer optional.
- Ragged Short Spear and The Sackville-Bagginses: conditional draws are gated by the optional prior action.
- The Master of Lake-town: formula draw quantity is not represented as fixed total 1.
- Balin and Uncover: `X` quantity bindings are present.

Still incorrect:

- Balin's draw carries a condition from the later damage instruction.
- Silvan Reveler's draw carries a condition from the later land-movement instruction.
- Uncover's optional draw carries a condition from the later discard instruction.

## Required Corrections

1. Replace clause-wide condition fallback for participant records with operation-scoped condition assignment.
2. Add regression tests proving:
   - Balin's `DRAW` record has no unrelated enduring-story/later-damage condition.
   - Silvan Reveler's enter draw is unconditional.
   - Uncover's `DRAW` record is optional and formula-bound, but not conditioned by its later `If you do, discard two cards`.
   - True participant-effect conditions remain attached for Beorn, Azog, Smaug, Belladonna Took, and Plunder.

## Acceptance Tests For The Next Commit

The next repair commit should be accepted only if all of the following hold:

- `git diff --check 92ec14c..<repair-commit>` is clean.
- Frozen manifest checks pass.
- `pytest` passes.
- Two serial `python -m hobkg.cli effect-build` runs are byte-identical.
- `python -m hobkg.cli effect-reconcile` reports 0 unresolved and keeps deferred/nonexecutable separate.
- Participant draw/life records still do not fan out into card-pair projection.
- Direct JSONL checks confirm all pt1 and pt2 repairs remain fixed.
- Direct JSONL checks confirm participant-effect conditions are operation-scoped and do not leak from sibling instructions.

## May The Phase Proceed?

No. Phase 4a still requires repair before moving to the remaining Phase 4 families.
