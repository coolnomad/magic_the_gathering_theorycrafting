# HOB Effect-Semantics Review Agent Handoff

Use this file to start a fresh review-agent session for the HOB mechanistic-graph effect-semantics repair.

## Role

You are the independent technical reviewer, not the implementation agent.

Your job is to monitor commits produced by the executor agent, inspect each new commit directly, verify claims against code and generated artifacts, run tests, and write review documents under `docs/`.

Do not modify implementation code unless the user explicitly changes your role. Creating new review documents in `docs/` is authorized. Preserve existing user/executor changes. Do not reset, checkout over, delete, or rewrite unrelated work.

## Repository Rules

At session start:

1. Read `INSTRUCTIONS.md` completely.
2. Follow append-only discipline for `LABNOTEBOOK.md` and `CONVERSATION_LOG.md`.
3. Append a conversation-log entry before the turn is complete, unless the repo has an active hook that reliably does it.
4. Treat the frozen HOB core as protected. It must remain byte-identical to `data/graph_global/frozen_manifest.json`.

Protected frozen artifacts currently listed in the manifest:

- `data/graph/conditions.jsonl`
- `data/graph/edges.jsonl`
- `data/graph/gates.jsonl`
- `data/graph/nodes.jsonl`
- `data/graph_global/conditions.jsonl`
- `data/graph_global/edges.jsonl`
- `data/graph_global/nodes.jsonl`

## Required Context To Read

Read these before reviewing new work:

- `docs/hob_effect_semantics_repair_instructions.md`
- all `docs/*PHASE*_review*.md` files in chronological order
- relevant recent entries in `LABNOTEBOOK.md`
- `reports/effect_census.md`
- `reports/effect_reconciliation.md`
- `reports/effect_semantics.md`
- the most recent review document, currently:
  - `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt4.md`

## Current Status

Accepted before Phase 3c:

- Phase 1: complete clause-level census and frozen baseline.
- Phase 2: general effect schema and destruction vertical slice.
- Phase 3b: selector and projection correctness at commit `8dd2d7d`.

Latest reviewed implementation commit:

```text
d0047e46ce91ac1e8bd7c9997680af65ec6a2dcf Effect-semantics Phase 3c: semantic completeness of object records (review pt3)
```

Review verdict for `d0047e4`:

```text
changes required
```

Important nuance: the Phase 3c semantic repairs were accepted, but the commit needs repository cleanup before Phase 4 should proceed.

Blocking findings from `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt4.md`:

1. `reports/coverage.md` was rewritten to an older Phase 1-style coverage report, unrelated to Phase 3c and dropping richer current coverage detail.
2. `git diff --check 8dd2d7d..d0047e4` failed on trailing whitespace in `CONVERSATION_LOG.md:4871`.

Nonblocking follow-ups recorded:

- Generated-artifact tests rewrite shared JSONL files; prefer atomic writes or temp outputs for tests.
- Projection `supports[]` entries require dereferencing `effect_id` to see full conditions/durations; Phase 6 should document or embed summaries.

## What Phase 3c Fixed Semantically

When reviewing the cleanup commit, confirm these are still true:

- Great Ugly-Looking Goblin:
  - selector keeps `predicates.has_counter: "+1/+1"`.
- Most Decrepit Old Bird:
  - effect condition is `threshold`.
- Ori, Keeper of Songs:
  - self P/T and vigilance effects carry `enduring_story`.
- Óin the Brave:
  - self P/T and haste effects carry `enduring_story`.
- Thorin Oakenshield:
  - mass ward grant carries `enduring_story`.
- Fíli the Pathfinder:
  - mass P/T grant carries `enduring_story`.
- Dáin's Company:
  - lifelink grant carries `controls_another` with subtype `dwarf`.
- Bolg's Company:
  - haste grant carries `controls_another` with subtype `goblin`.
- Gnashing of Teeth:
  - first mode `MODIFY_PT` carries `die_would_exile_instead` replacement bound to the same target var for `this_turn`.
- Old Fat Spider Can't See Me:
  - hexproof grant and prevention both carry `as_long_as_source_on_battlefield`.
- Thorin, Mountain-king:
  - damage source is the creature Equipment became attached to, not an Equipment object.
  - expected source selector: `card_types: ["creature"]`, `controller: "you"`, no `equipment` subtype.
- Oracle-recognized but uninstantiated subtypes:
  - `Goblin or Orc` selectors retain `orc` even though current HOB projection has zero Orc permanents.

## Review Procedure For Each New Commit

Start with:

```bash
git status --short --branch
git fetch origin
git log --oneline --decorate -12 --all
```

Identify:

- latest implementation commit to review;
- preceding reviewed commit;
- whether there are dirty local files that are not part of the commit.

Inspect the commit:

```bash
git show --stat --summary <commit>
git diff --check <parent>..<commit>
git diff --name-status <parent>..<commit>
git diff --stat --summary <parent>..<commit>
```

Read every changed source file, test, generated artifact, report, and review/spec entry relevant to the phase. Do not rely on commit messages.

## Required Verification Commands

Run the strongest available checks. Prefer the full suite when possible:

```bash
python -m hobkg.cli effect-build
python -m hobkg.cli effect-reconcile
pytest
```

If sandbox restrictions cause temp/cache failures, rerun `pytest` with approval/escalation rather than accepting a partial run.

Verify frozen artifacts by hashing each path in `data/graph_global/frozen_manifest.json` and comparing to its recorded SHA-256. Also rely on:

```bash
pytest tests/test_frozen_manifest.py
```

Check deterministic rebuilds:

```bash
python -m hobkg.cli effect-build
# record hashes of effect_records.jsonl and card_pair_projection_effect.jsonl
python -m hobkg.cli effect-build
# hashes must match
```

Important generated files:

- `data/graph_global/effect_records.jsonl`
- `data/graph_global/card_pair_projection_effect.jsonl`
- `data/graph_global/pair_index.jsonl`

## Direct Record Inspection

Do not stop when tests pass. Query generated JSONL records directly.

For each named regression card, compare printed Oracle text to structured effect record and projection:

- Warg Tactics
- Reverent Howl
- Pinecone Strike
- Magnificent End
- Stone by Sunlight
- Troll Negotiations
- Quarrel
- Concerted Care
- Gaze in Wonder
- Moment of Glory
- Gnashing of Teeth
- The Black Arrow
- The Arkenstone
- Great Ugly-Looking Goblin
- Mirkwood
- Mirkwood Meditator
- Old Fat Spider Can't See Me
- Burglar's Plot
- Sting, Bilbo's Sword
- Master's Councillors
- Dwarven Mattock
- Crude Bent Blade
- Thorin, Mountain-king
- Thorin Oakenshield
- Fíli the Pathfinder
- Ori, Keeper of Songs
- Óin the Brave
- Dáin's Company
- Bolg's Company
- Most Decrepit Old Bird

For each record, check:

- printed Oracle text;
- operation family;
- selector;
- participant;
- object variables and same-object bindings;
- modes and alternatives;
- conditions/gates;
- durations;
- quantities;
- targeting vs mass status;
- projection targets;
- provenance.

## Reconciliation Standard

Reconciliation at `(clause_id, family)` granularity is necessary but not sufficient.

An effect is not complete merely because one operation exists for the family. Check preservation of:

- target and participant restrictions;
- object identity;
- pronouns and antecedents;
- modes and alternatives;
- costs versus effects;
- optionality;
- conditions and gates;
- durations;
- quantities;
- selector predicates;
- source and destination zones;
- stochastic versus deterministic selection;
- alternate supporting mechanisms.

Count deferred/nonexecutable cases separately from unresolved cases.

## Portability Standard

Reusable extraction code must not branch on card names, UUIDs, or audited pairs.

Card-specific tests are required. Card-specific implementation branches are not acceptable unless they are declarative set-local exceptions with explicit provenance and justification.

Do not allow a set-observed vocabulary to erase valid Oracle semantics merely because no current HOB object instantiates the class.

## Review Document Requirements

For every reviewed implementation commit, create a new Markdown file in `docs/` using the existing naming pattern. Never overwrite an earlier review.

Example next names:

- `docs/hob_effect_semantics_repair_instructions_PHASE3_review_pt5.md`
- `docs/hob_effect_semantics_repair_instructions_PHASE4_review_pt1.md`

Each review must contain:

1. commit reviewed;
2. verdict:
   - accepted;
   - accepted with nonblocking follow-up;
   - changes required;
3. evidence inspected;
4. tests and commands run;
5. frozen-artifact status;
6. findings ordered by severity;
7. concrete Oracle examples;
8. required corrections;
9. acceptance tests for the next commit;
10. whether the phase may proceed.

Lead with the verdict.

Be explicit whether each finding affects:

- authoritative structured semantics;
- pair projection;
- execution semantics;
- provenance;
- documentation only.

Do not commit the review unless the user explicitly asks.

## Current Recommended Next Review

Look for a cleanup commit after `d0047e4`.

The cleanup commit should:

- restore `reports/coverage.md` to the prior richer coverage report, or regenerate it through the current documented pipeline with a clear rationale;
- fix `git diff --check 8dd2d7d..<cleanup-commit>`;
- preserve the accepted Phase 3c semantic records;
- pass:
  - `python -m hobkg.cli effect-build`
  - `python -m hobkg.cli effect-reconcile`
  - `pytest`
  - frozen-manifest checks;
- leave two serial `effect-build` outputs byte-identical.

If those hold, Phase 3 can be accepted and the executor may proceed to Phase 4.

## Later Phase Focus

After Phase 3 acceptance, continue the same workflow for:

- Phase 4: draw, discard, sacrifice, life, mill, search, counterspells, complete `SUPPLIES_RESOURCE` review, and `sac_schema` integration.
- Phase 5: exile, movement, delayed return, and play/cast permissions.
- Phase 6: final projection and ordered overlay/suppression integration.
- Phase 7: final dispositions, regression and negative tests, coverage reports, deterministic rebuild, provenance validation, documentation, and acceptance.

Do not assume passing tests proves semantic completeness. The authoritative question is whether generated structured records and projections faithfully represent Oracle clauses under the project's stated abstraction boundary.
