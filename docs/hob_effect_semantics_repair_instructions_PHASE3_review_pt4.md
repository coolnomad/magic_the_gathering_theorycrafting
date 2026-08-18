# Verdict: changes required

Reviewed commit: `d0047e46ce91ac1e8bd7c9997680af65ec6a2dcf` (`Effect-semantics Phase 3c: semantic completeness of object records (review pt3)`)

Preceding reviewed commit: `8dd2d7d` (`Effect-semantics Phase 3b: selector + projection correctness`)

The Phase 3c semantic repairs are substantively correct, but the commit is not acceptable as-is because it includes unrelated/stale generated documentation churn and fails `git diff --check`. Require a cleanup commit before Phase 4 proceeds.

## Evidence Inspected

- Instructions and prior reviews:
  - `INSTRUCTIONS.md`
  - `docs/hob_effect_semantics_repair_instructions.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE1_review_pt1.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE1_review_pt2.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE2_review_pt1.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE2_review_pt2.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt1.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt2.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt3.md`
- Recent project record:
  - relevant tail of `LABNOTEBOOK.md`
  - `reports/effect_census.md`
  - `reports/effect_reconciliation.md`
  - `reports/effect_semantics.md`
- Git/history:
  - `git log --oneline --decorate -20`
  - `git status --short --branch`
  - `git fetch origin`
  - `git log --oneline --decorate -8 origin/main`
  - `git show --stat --summary d0047e4`
  - `git diff --check 8dd2d7d..d0047e4`
  - `git diff --name-status 8dd2d7d..d0047e4`
  - `git diff --stat --summary 8dd2d7d..d0047e4`
  - `git diff --check HEAD -- src/hobkg/effect_schema.py src/hobkg/effect_semantics.py tests/test_effect_object.py data/graph_global/effect_records.jsonl data/graph_global/card_pair_projection_effect.jsonl`
  - `git diff --name-status HEAD`
  - `git diff --stat --summary HEAD`
- Changed Phase 3c files:
  - `src/hobkg/effect_schema.py`
  - `src/hobkg/effect_semantics.py`
  - `tests/test_effect_object.py`
  - `data/graph_global/effect_records.jsonl`
  - `data/graph_global/card_pair_projection_effect.jsonl`
  - `LABNOTEBOOK.md`
  - `CONVERSATION_LOG.md`
  - `reports/coverage.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt3.md`

I also inspected generated records directly from:

- `data/graph_global/effect_records.jsonl`
- `data/graph_global/card_pair_projection_effect.jsonl`
- `data/graph_global/pair_index.jsonl` where relevant to composition
- `data/normalized/faces.jsonl` for printed Oracle text

## Tests And Commands Run

- `git fetch origin`
  - Required escalation initially because the sandbox could not open `.git/FETCH_HEAD`.
  - Result: success; final refs show `d0047e4` at `HEAD` and `origin/main`.
- `git diff --check 8dd2d7d..d0047e4`
  - Result: failed. `CONVERSATION_LOG.md:4871` has trailing whitespace.
- `python -m hobkg.cli effect-build`
  - Result: 120 effects on 90 faces; 7,950 effect projection pairs.
- `python -m hobkg.cli effect-reconcile`
  - Result: 174 `(clause_id, family)` pairs; 119 extracted; 4 deferred/nonexecutable; 0 unresolved.
- Frozen hash check against `data/graph_global/frozen_manifest.json`
  - Result: all seven protected frozen artifacts matched their manifest SHA-256 values.
- `pytest tests/test_frozen_manifest.py tests/test_effect_object.py tests/test_effect_destroy.py`
  - Initial result before clean regeneration: failed on stale/inconsistent generated state.
  - After serial `effect-build`: relevant targeted tests passed.
- `pytest tests/test_effect_object.py::test_thorin_mountain_king_damage_source_is_the_attached_creature tests/test_effect_object.py::test_no_unconditional_effect_when_the_clause_gates_it`
  - Result after serial rebuild: 2 passed.
- `pytest tests/test_effect_destroy.py::test_bilbo_and_stir_destroy_all_creatures -vv`
  - Result: passed.
- `pytest tests/test_effect_destroy.py -q`
  - Result: 16 passed.
- `pytest`
  - Final unsandboxed result: 320 passed in 45.74s.
- Deterministic rebuild:
  - Ran `python -m hobkg.cli effect-build` twice serially.
  - Stable hashes:
    - `effect_records.jsonl`: `B863C258716BCFB21CCAECA3A0261289A7A09DF570F3BC7FFEA21A796BDC2CB2`
    - `card_pair_projection_effect.jsonl`: `C23544803DBADBEAD65873631B9988A09EED5E01BEA02C10565BCE8F0C0937D2`

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

## Findings

### Blocking: unrelated `reports/coverage.md` rewrite

Severity: documentation/generated artifact correctness.

`d0047e4` rewrites `reports/coverage.md` from the existing full coverage report into a much older-looking "HOB Phase 1 - Coverage Report" shape. This file is not part of the Phase 3c object-effect repair, and the rewrite drops the richer union/pair/frozen-layer coverage summary previously present.

This is not just harmless formatting: it changes project-facing status documentation and makes the repo report less informative immediately before later phases depend on coverage and provenance evidence.

Required correction: restore `reports/coverage.md` to the pre-`d0047e4` content unless the implementation agent can justify and regenerate the coverage report through the documented coverage pipeline as an intentional, current Phase 3c artifact.

### Blocking: `git diff --check` fails

Severity: repository hygiene.

`git diff --check 8dd2d7d..d0047e4` reports trailing whitespace in `CONVERSATION_LOG.md:4871`.

Required correction: remove the trailing whitespace in an append-only-safe way. Since this is inside an append-only log, do not rewrite substantive content; only strip the trailing space on that line or append a correction if the project owner treats whitespace cleanup as disallowed.

### Nonblocking: generated-artifact tests rewrite shared JSONL files

Severity: test robustness / generated artifact hygiene.

During review, one full-suite run observed a transient JSON parse failure reading `card_pair_projection_effect.jsonl` with leading NUL bytes. The file was clean immediately afterward, the affected test passed alone, `tests/test_effect_destroy.py` passed as a group, and the final full suite passed. This does not block Phase 3c acceptance, but repeated tests that rewrite checked-in generated artifacts are brittle on Windows and can leave stale or partially rewritten files after interrupted runs.

Recommended follow-up: write generated outputs atomically, or route test rebuilds through `write=False` / temporary output paths unless the test is explicitly verifying checked-in artifact generation.

### Nonblocking: pair support records still require dereferencing for conditions

Severity: projection provenance / consumer ergonomics.

The authoritative structured records now preserve conditions, predicates, durations, and replacement bindings. Projection rows still carry compact `supports[]` entries with `effect_id`, mode, op, span, and target status; a consumer must dereference `effect_id` to see the full condition or selector predicate.

This is acceptable for Phase 3 because the structured layer is authoritative and projections retain the effect ID, but Phase 6 ordered overlay/projection integration should either embed condition/duration summaries in supports or document that consumers must dereference the structured effect record.

## Concrete Oracle Examples

The blocking Phase 3b issues are resolved in the regenerated structured records:

- Great Ugly-Looking Goblin:
  - Oracle: "Each creature you control with a +1/+1 counter on it has menace."
  - Structured record now has selector predicate `has_counter: "+1/+1"`, `controller: "you"`, `affects_each: true`, and `quantifier: "each"`.
- Most Decrepit Old Bird:
  - Oracle: "Threshold - This creature gets +1/+1 as long as there are seven or more cards in your graveyard."
  - Structured record now has `condition: {"kind": "threshold", "detail": "seven_or_more_cards_in_graveyard"}` and self-bound `MODIFY_PT`.
- Ori, Keeper of Songs and Óin the Brave:
  - Oracle: "As long as you have an enduring story..."
  - Their self-bound P/T and ability-grant effects now carry `condition: {"kind": "gate", "gate": "enduring_story"}`.
- Thorin Oakenshield and Fíli the Pathfinder:
  - Enduring-story mass effects now carry the same `enduring_story` gate condition.
- Dáin's Company and Bolg's Company:
  - Oracle requires control of another Dwarf/Goblin.
  - Records now carry `condition: {"kind": "controls_another", "subtype": "dwarf"}` and `{"kind": "controls_another", "subtype": "goblin"}` respectively.
- Gnashing of Teeth:
  - Oracle first mode: "Target creature gets -5/-5 until end of turn. If that creature would die this turn, exile it instead."
  - The targeted `MODIFY_PT` record now carries `replacement: {"kind": "die_would_exile_instead", "object_var": "obj0", "duration": "this_turn"}`.
- Old Fat Spider Can't See Me:
  - Both the hexproof grant and prevention chapter now carry `duration: "as_long_as_source_on_battlefield"`.
- Thorin, Mountain-king:
  - Oracle binds damage source to "that creature" after Equipment becomes attached.
  - Regenerated record now has a distinct damage target `obj2` and source `obj1` with source selector `card_types: ["creature"]`, `controller: "you"`, and no Equipment subtype.
- Along the Crooked Way:
  - Selector now preserves both `goblin` and uninstantiated `orc`; projection naturally finds only the currently instantiated Goblin/Orc-eligible HOB objects.

I also spot-checked the broader Phase 3 acceptance set, including Warg Tactics, Reverent Howl, Pinecone Strike, Magnificent End, Stone by Sunlight, Troll Negotiations, Quarrel, Concerted Care, Gaze in Wonder, Moment of Glory, The Black Arrow, The Arkenstone, Mirkwood, Mirkwood Meditator, Burglar's Plot, Sting, Master's Councillors, Dwarven Mattock, and Crude Bent Blade. The checked structured records match the intended Phase 3 abstraction boundary.

## Required Corrections

No blocking semantic correction is required for the Phase 3c effect semantics themselves.

Before proceeding, the implementation agent must:

1. Restore or correctly regenerate `reports/coverage.md`.
2. Fix the `git diff --check` trailing-whitespace failure in `CONVERSATION_LOG.md`.
3. Leave the Phase 3c source, tests, and effect artifacts intact unless a further semantic issue is found.
4. Re-run `python -m hobkg.cli effect-build`, `python -m hobkg.cli effect-reconcile`, and `pytest`.

## Acceptance Tests For The Next Commit

The cleanup commit should be accepted if all of the following hold:

- `git show --stat --summary <cleanup-commit>` shows only the review-response cleanup plus any append-only log/doc entries.
- `git diff --check 8dd2d7d..<cleanup-commit>` is clean.
- `reports/coverage.md` is restored to the prior coverage report or regenerated through the documented current coverage pipeline with an explicit explanation.
- `python -m hobkg.cli effect-build` emits 120 effects and 7,950 effect projection pairs, or any count change is explained by a real semantic delta.
- Two serial `effect-build` runs produce byte-identical:
  - `data/graph_global/effect_records.jsonl`
  - `data/graph_global/card_pair_projection_effect.jsonl`
- `python -m hobkg.cli effect-reconcile` reports 0 unresolved and keeps deferred/nonexecutable cases counted separately.
- `pytest` passes.
- Direct JSONL checks confirm:
  - Great Ugly-Looking Goblin has `has_counter: "+1/+1"`.
  - Most Decrepit Old Bird has `threshold`.
  - Ori, Óin, Thorin Oakenshield, and Fíli carry `enduring_story`.
  - Dáin's Company and Bolg's Company carry `controls_another`.
  - Gnashing of Teeth has a same-object death-to-exile replacement.
  - Old Fat Spider's hexproof and prevention both have source-presence duration.
  - Thorin, Mountain-king's damage source is the attached creature, not Equipment.
  - `Goblin or Orc` selectors retain `orc` even with zero HOB Orc permanents.
- Frozen-manifest checks still pass.

## May The Phase Proceed?

Not yet. The Phase 3c semantic repairs are accepted, but the commit as a repository change needs cleanup before Phase 4 begins.
