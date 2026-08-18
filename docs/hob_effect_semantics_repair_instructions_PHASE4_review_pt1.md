---
protocol: worker_reviewer_handshake_v1
role: reviewer
phase: Phase 4
iteration: pt1
reviewed_commit: c5f32f9fc12f787636fc90528d28e446a7ab5730
parent_commit: c9e249e6d1f771536a478507c90ce5239d1264b9
review_commit: PENDING_IN_THIS_COMMIT
verdict: REPAIR
blocking_findings: 6
nonblocking_findings: 1
deferred_items: 0
---

# Verdict: REPAIR

Reviewed commit: `c5f32f9fc12f787636fc90528d28e446a7ab5730` (`Effect-semantics Phase 4a: participant/resource draw and life records`)

Parent commit: `c9e249e6d1f771536a478507c90ce5239d1264b9` (`Document worker-reviewer handshake protocol`)

Phase 4a is not accepted. The commit correctly adds participant-level draw/life records without card-pair fan-out, but several generated records contradict Oracle text or omit mandatory participant/mode/quantity semantics. The failures are in the authoritative structured effect records, not merely in tests or reports.

## Evidence Inspected

- Governing instructions and protocol:
  - `INSTRUCTIONS.md`
  - `docs/review_event_protocol.md`
  - `docs/hob_effect_semantics_repair_instructions.md`
  - `docs/phase4-requirements.md`
- Prior relevant reviews:
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt3.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt4.md`
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt5.md`
- Recent project record and reports:
  - recent tail of `LABNOTEBOOK.md`
  - `reports/effect_census.md`
  - `reports/effect_reconciliation.md`
  - `reports/effect_semantics.md`
- Git/history:
  - `git status --short --branch`
  - `git fetch origin`
  - `git log --oneline --decorate -8 origin/main`
  - `git show --stat --summary c5f32f9`
  - `git diff --check c9e249e..c5f32f9`
  - `git diff --name-status c9e249e..c5f32f9`
  - `git diff --stat --summary c9e249e..c5f32f9`
- Changed Phase 4a files:
  - `src/hobkg/effect_schema.py`
  - `src/hobkg/effect_semantics.py`
  - `tests/test_effect_participant.py`
  - `data/graph_global/effect_records.jsonl`
  - `reports/effect_reconciliation.md`
  - `reports/effect_semantics.md`
  - append-only log/notebook entries
- Generated records inspected directly:
  - `data/graph_global/effect_records.jsonl`
  - `data/graph_global/card_pair_projection_effect.jsonl`
  - `data/graph_global/pair_index.jsonl`
  - `data/normalized/faces.jsonl`

## Tests And Commands Run

- `git fetch origin`
  - Initial sandboxed attempt failed on `.git/FETCH_HEAD`; rerun with approval succeeded.
- `git diff --check c9e249e..c5f32f9`
  - Passed.
- `pytest tests/test_effect_participant.py tests/test_effect_object.py tests/test_effect_destroy.py -q`
  - Result: 62 passed.
- `python -m hobkg.cli effect-build`
  - Result: 174 effects on 122 faces; 7,950 pairs.
- `python -m hobkg.cli effect-reconcile`
  - Result: 244 `(clause_id, family)` pairs; 169 extracted; 4 deferred/nonexecutable; 0 unresolved.
- Frozen manifest hash check against `data/graph_global/frozen_manifest.json`
  - Result: all protected frozen artifacts matched.
- `pytest -q`
  - Result: 332 passed in 39.22s.
- Two serial `python -m hobkg.cli effect-build` runs
  - Stable `data/graph_global/effect_records.jsonl` SHA-256: `19b17c5ee88dea261db27a1266a982f1b52c4cf676b0e5a8003d1caae43ce5f5`
  - Stable `data/graph_global/card_pair_projection_effect.jsonl` SHA-256: `c23544803dbadbead65873631b9988a09eed5e01bea02c10565bce8f0c0937d2`
- Pair fan-out check:
  - `card_pair_projection_effect.jsonl` and `pair_index.jsonl` have no `DRAWS_CARDS`, `GAINS_LIFE`, or `LOSES_LIFE` pairs.

The full suite dirtied `reports/coverage.md` and `data/review/llm_*.jsonl` in the working tree during review. These were not staged or reviewed as part of the implementation diff.

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

### Blocking 1: targeted participant effects lose targeting status

Impact: authoritative structured semantics.

Participant-level records always use `targeted: false` and `selector.targeted: false`, even when Oracle text explicitly targets a player or opponent. This drops a mandatory target restriction/status required by the Phase 4 instructions.

Concrete records:

- Meager Meal: "Target player gains 2 life." emits `participant: "target_player"` but `targeted: false`.
- Reverent Howl mode 1: "Target player draws two cards and loses 2 life." emits both participant records with `targeted: false`.
- Down, Down to Goblin-town: "Target opponent loses 1 life and you gain 1 life." emits the opponent life loss with `targeted: false`.
- The Sackville-Bagginses: "target opponent loses 1 life" emits `targeted: false`.

Required correction: participant records need their own targeting/mass/quantity metadata. At minimum, `target_player` and `target_opponent` records must carry `targeted: true` and the selector metadata must agree.

### Blocking 2: "Two target players each draw a card" is bound to the wrong participant and loses quantity

Impact: authoritative structured semantics.

Gleaming Splendor Oracle text:

> {2}{W}: Two target players each draw a card.

The generated `DRAW` record has:

```json
"participant": "you",
"targeted": false,
"affects_each": false,
"amount": "1"
```

This should be two target players, not `you`. It also needs to preserve both the target quantity (`two target players`) and mass/each status over those targets.

Required correction: add participant parsing for numeric target-player selectors such as `two target players each`, including `participant`, `targeted`, `quantity`, and `affects_each` or equivalent.

### Blocking 3: owner/controller participant binding is incomplete

Impact: authoritative structured semantics.

Gandalf, Wandering Wizard Oracle text:

> {6}: Gandalf's owner shuffles him into their library and draws three cards.

The generated `DRAW` record has:

```json
"participant": "you",
"amount": "3"
```

The participant is the card's owner, not necessarily `you`. This is a real player-binding error, and it will matter for future movement/permission integration.

Required correction: parse possessive owner/controller subjects such as `<source>'s owner`, `<source>'s controller`, `its owner`, and `its controller` into participant bindings rather than defaulting to `you`.

### Blocking 4: quoted or granted abilities are extracted as immediate source effects

Impact: authoritative structured semantics and future execution semantics.

Supper for Spiders Oracle text:

> They are Food artifacts with "{2}, {T}, Sacrifice this artifact: You gain 3 life."

The generated record emits an immediate `GAIN_LIFE` effect for Supper for Spiders:

```json
"op": "GAIN_LIFE",
"amount": "3",
"participant": "you",
"duration": "this_turn"
```

That life gain is not performed when Supper for Spiders resolves. It is part of a quoted activated ability granted to the returned Food artifacts. Phase 4a must not turn granted/quoted abilities into immediate participant effects.

Required correction: blank or separately classify quoted granted abilities before participant extraction, with a reconciliation disposition such as granted ability / token-object ability / deferred execution rather than `extracted` as a source life effect.

### Blocking 5: replacement draw text emits the replaced draw as a real draw effect

Impact: authoritative structured semantics.

Bard, King of Dale Oracle text:

> If you would draw a card except the first one you draw in each of your draw steps, draw two cards instead.

The generated records include both:

- `DRAW amount: "1"` for the event that would be replaced;
- `DRAW amount: "2"` with `replacement: {"kind": "draw_instead"}`.

The first record is not a draw effect caused by Bard. It is the event being replaced. Emitting it as a direct `DRAWS_CARDS` effect contradicts the replacement effect semantics and inflates draw coverage.

Required correction: replacement-effect antecedents such as `would draw a card` must not be emitted as ordinary draw operations. The structured record should represent the replacement/prevention semantics explicitly, or mark unsupported execution semantics as deferred rather than extracting a false direct draw.

### Blocking 6: modal participant effects are flattened with `mode: null`

Impact: authoritative structured semantics.

Gollum, Riddle Master Oracle text:

> Whenever an opponent casts a spell with mana value of the chosen quality, choose one that hasn't been chosen — ... Each opponent loses 2 life and you gain 2 life. ... Draw a card.

The generated `GAIN_LIFE`, `LOSE_LIFE`, and `DRAW` participant records all have:

```json
"mode": {"kind": null, "index": null}
```

These are alternatives under a "choose one that hasn't been chosen" structure, not an unconditional bundle. The governing instructions require modes and alternatives to remain distinct and not become simultaneous unconditional effects.

Required correction: extend ability/mode segmentation or participant extraction so bullet alternatives under triggered "choose one" abilities preserve mode identity and mutual-exclusion/choice semantics for participant records.

### Nonblocking 1: some conditional quantities remain under-specified

Impact: semantic completeness / future execution ergonomics.

Some records retain only generic `conditional_effect` or miss useful quantity scaling. For example, The Master of Lake-town has "draw a card for each graveyard with seven or more cards in it" but the record only shows `amount: "1"` and no scaling in the checked generated output. Belladonna Took records preserve `conditional_effect` but not first/second-resolution details.

These are likely part of the broader Phase 4 quantity/condition work, but the next repair should at least avoid representing variable quantities as fixed amounts when the amount is explicitly formulaic.

## Concrete Oracle Examples

Correct examples in this commit:

- Reverent Howl correctly binds the same `participant_var` to the target player that draws two and loses 2 life.
- Rage into the Valley correctly binds `you` for draw and life loss.
- Gollum, Riddle Master's life mode correctly distinguishes `each_opponent` from `you`.
- Pay-life costs such as My Precious / Desolation Prowler / Elven Passage are not emitted as `LOSE_LIFE` effects.
- Draw/life participant records do not fan out into card-pair projection.

Incorrect examples requiring repair:

- Meager Meal, Reverent Howl, Down, Down to Goblin-town, and The Sackville-Bagginses lose participant targeting status.
- Gleaming Splendor binds "Two target players each draw a card" to `you`.
- Gandalf, Wandering Wizard binds "Gandalf's owner ... draws three cards" to `you`.
- Supper for Spiders emits a quoted Food activated ability as immediate life gain.
- Bard, King of Dale emits the replaced draw event as a direct draw effect.
- Gollum, Riddle Master loses the "choose one that hasn't been chosen" modal alternatives.

## Required Corrections

1. Preserve participant targeting, each/mass status, and participant quantities in draw/life records.
2. Correct numeric target participant selectors, including Gleaming Splendor's two target players.
3. Bind owner/controller participant subjects correctly.
4. Prevent quoted/granted abilities from being extracted as immediate draw/life source effects.
5. Represent draw replacement effects without emitting the replaced event as a direct draw.
6. Preserve mode/alternative semantics for participant effects in triggered "choose one" abilities.
7. Add regression tests that inspect the generated structured records for each blocker above, not only helper-level extraction assumptions.

## Acceptance Tests For The Next Commit

The repair commit should be accepted only if all of the following hold:

- `git diff --check c5f32f9..<repair-commit>` is clean.
- Frozen manifest checks pass.
- `pytest` passes.
- Two serial `python -m hobkg.cli effect-build` runs are byte-identical.
- `python -m hobkg.cli effect-reconcile` reports 0 unresolved and keeps deferred/nonexecutable separate.
- `card_pair_projection_effect.jsonl` and `pair_index.jsonl` still contain no deterministic `DRAWS_CARDS`, `GAINS_LIFE`, or `LOSES_LIFE` card-pair fan-out.
- Direct JSONL checks confirm:
  - Reverent Howl and Meager Meal target-player records have `targeted: true`.
  - Down, Down to Goblin-town and The Sackville-Bagginses target-opponent life loss has `targeted: true`.
  - Gleaming Splendor records two target players, each drawing one card, not `you`.
  - Gandalf, Wandering Wizard records the drawing participant as owner.
  - Supper for Spiders does not emit immediate `GAIN_LIFE` from the quoted Food ability.
  - Bard, King of Dale does not emit a direct `DRAW 1` for the replaced draw event.
  - Gollum, Riddle Master's life and draw alternatives carry explicit mode/choice metadata.

## May The Phase Proceed?

No. Phase 4a requires repair before moving on to discard, sacrifice, mill, search, counterspells, or the `SUPPLIES_RESOURCE` review.
