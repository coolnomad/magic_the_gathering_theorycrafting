# HANDOFF — read this first

**Last updated 2026-09-10.** Everything below the "KNOWLEDGE-GRAPH ARM" heading
dates from 2026-08-17 and describes the KG arm only; it is still accurate for
that arm. Read this top section first — the project has a second arm and the
active work is there.

---

# CURRENT STATE (2026-09-10)

## Two arms

**1. Knowledge graph (HOB)** — frozen and complete through layer 3. Detail in
the KG section below. Layer 4 (capacity projection) is unbuilt. Nothing here
needs attention unless you are asked for it.

**2. Deck-strength modeling benchmark** — this is where the work is. Governed by
`docs/MTG_Deck-Strength_Modeling_Benchmark.md`, which **supersedes**
`docs/Model_Building.md` in full (that file carries a superseded banner).

## Where the modeling arm stands (2026-09-10)

**Cards 001-017 are all DONE. PHASE 2 IS COMPLETE.** All three target rows are
fitted, the holdout has been read once, and the benchmark has its answer.
Milestone `benchmark-p1` was **confirmed 2026-09-10**; `registry.md` carries
`status: MILESTONE_BENCHMARK_P1`. **Note the underscore:** `compact milestone`
normalises its tag with `tag.upper()` only, but the validator is
`^MILESTONE_[A-Z0-9_]+$` with no hyphen allowed, so confirming `benchmark-p1`
wrote `MILESTONE_BENCHMARK-P1`, which compact's own parser then rejects on every
read -- bricking all card operations until repaired by hand. **Confirming
`benchmark-p2` will do this again.** (Confirming a milestone is what rewrites
that field --
so if `registry.md` shows as modified and nobody edited it, that is compact, not
a stray write. It arrived mid-commit here and was swept in by a `git add -A`.)

The frozen dataset, all pinned by `data/processed/MANIFEST.sha256` (tracked; the
parquet blobs are gitignored):

| | |
|---|---|
| observational unit | **the game** (decks change within 19% of drafts) |
| population | **241,561 games across 43,102 drafts** |
| card features | 193, as normalized deck fractions |
| split | time-based, dev 194,215 / holdout 47,346, 5 folds, seed 20260908 |
| skill proxy | `base_p`, shrunk toward a **per-draft** `mu` = 0.533339, lambda=5 |
| player id | **none exists**; `rank` is a skill bucket, never a player id |

`base_p` is a nuisance proxy. **Never call it skill**, in code, columns or prose.

**The holdout is sealed and has never been read.** `cycle/holdout_ledger.jsonl`
is **0 bytes**. Access goes through `deckbench.holdout.load_holdout(card_id,
reason)`, which verifies a hash and appends a ledger line; `load_dev` is the
unsealed path for ordinary fitting. Do not bypass either.

## What phase 2 has built, and what remains

  009  representation-blind estimator (one grid, frozen folds)      DONE
  010  evaluation panel, built before anything was scored          DONE
  011  T0 raw outcome x R0/R1, development fits                    DONE
  012  suite stability -- the flaky graph writes                   DONE
  013  determinism harness + the PYTHONHASHSEED fix                DONE
  014  mu per draft (fidelity correction) + T0 refits              DONE

  015  T1  -- bump against the fixed skill proxy                   DONE
  016  T2  -- bump against a CROSS-FITTED learned baseline         DONE

  017  the single holdout read, all models, paired bootstrap       DONE

**THE HOLDOUT HAS BEEN READ.** `cycle/holdout_ledger.jsonl` is no longer 0
bytes -- it holds exactly one line, card 017, `is_repeat: false`,
2026-09-11T04:11:18Z. **It cannot be read again.** Any future card that wants an
honest generalisation estimate needs a fresh split, or must say plainly that it
is reusing a partition that has been read. This is the single most important
fact on this page.

**What the read found** (`reports/holdout_read.md`, LABNOTEBOOK [2026-09-11 04:11]):

1. **Card identity is detectable.** All three within-target `R1 - R0` increments
   exclude zero: Brier-skill +0.00465 / +0.00478 / +0.00491 for T0 / T1 / T2,
   every metric agreeing in sign. Skill-only reaches ~0.0323 Brier skill,
   skill-plus-identity ~0.0372 -- so of the small share of a game outcome that is
   predictable at all under this learner, roughly **87% goes to the skill proxy
   and 13% to card identity**. AUC 0.598 -> 0.607.
2. **H2 is NOT supported.** All nine difference-of-increment intervals include
   zero. Point estimates do fall in the predicted T2 > T1 > T0 order, but the
   uncertainty swamps it. Residualisation neither helped nor hurt detectably.
3. **H1 is supported.** Skill dominates.

**This is not a causal claim, and section 13 cuts both ways.** The ~13% is a
floor on detectability under R1, not a ceiling on how much deck composition
matters. Card identity as normalised fractions is a crude representation; phase
3's R2 (knowledge graph) and R3 (game script) exist because a functional
representation may recover more from the same games.

**The development metrics got the ordering wrong**, which is why they were
sealed off: development ordered T2 > T0 > T1, holdout orders T2 > T1 > T0.
Development also overstated the level -- T0_R1 Brier skill 0.041720 on
development against **0.036989** on holdout, optimistic by about the size of the
whole deck effect.

## PHASE 3 CANNOT START UNTIL THIS IS DECIDED

Spec section 16 puts phase 3 next: the representation benchmark,
`D_identity -> Z_KG -> Z_script -> combined` (R2-R5). **It is blocked on one
decision, and the decision must be made before any R2 feature is computed** --
because if a new split is being cut, it has to be cut before anyone looks at
anything.

### The holdout is spent, and what that actually means

It was read once, for six models, on comparisons declared in the card before the
seal broke. That is the cheapest possible way to spend a holdout: no iteration,
no peeking, no metric shopping. But **what leaked is real** -- we now know the
deck increment is about 0.005 and that target formulation does not matter.

The damage from a holdout is not done by reading it. It is done by **iterating
against it**: build R2, see it underperform, tweak, re-evaluate. Do that four
times and the partition is training data wearing a disguise.

So the status is not "destroyed", it is **"no longer independent of what we
know"**. Any future estimate from it is optimistically biased by an amount
nobody can quantify, and the bias grows with every further look.

### The four routes, and what each costs

**A -- Re-split the development partition.** 194,215 games across 34,482 drafts
is plenty to carve dev2/holdout2. **Catch:** to compare R1 against R2 fairly you
must **refit R0/R1 on dev2 as well**, because the current T0/T1/T2 models saw all
of dev. Phase 2's numbers would not transfer; you would re-run six fits to get a
comparable baseline. Cheap in compute and clean. Phase 2's conclusions still
stand as published -- they were honestly obtained on a sealed partition.

**B -- Use a different set entirely.** A fresh set is a genuinely virgin holdout,
and for this question it is scientifically *stronger*, not merely more
convenient: a knowledge-graph or game-script representation **should transfer
across sets**, while card identity cannot -- the 193 features do not exist in
another set. That converts "does R2 beat R1" into a generalisation question,
which is what a functional representation is actually claiming. **Catch:** the KG
is frozen on HOB, so R2 would need the graph extended. Ask whether that is on the
table, because if it is, it changes what phase 3 should be.

**C -- Reuse it, declared.** Second ledger line, state plainly that the estimate
is optimistically biased, apply a multiplicity correction. Defensible if honest;
most published work does this without saying so, and the ledger exists to make it
visible.

**D -- Pre-register, and do this regardless of A/B/C.** The leak comes from
*choices made after seeing results*. Fix R2's features, grid and comparisons in a
card before anything touches a holdout, and never revise them afterward. That
removes most of the adaptive-analysis problem even on a reused partition.

### Recommendation

**D always. Then A as the default, B if the KG arm can be extended.**

### The one thing not to do

Do not fit R2 on the current dev, evaluate on the current holdout, and report the
interval as if it meant what card 017's intervals meant. **Nothing in the tooling
will stop you** -- `load_holdout` will simply append a second line and hand over
the rows. The seal records reads; it does not judge them.

### Also inherited by phase 3

- **`phi_KG` is unspecified.** Spec section on R2 says "exact KG feature
  engineering will be specified separately", and that specification does not
  exist. R2 cannot be carded until someone decides what it computes, under the
  spec's own constraint that features must "describe functional/mechanistic
  structure rather than merely relabel card identities". A KG projection that is
  secretly a re-encoding of identity would test nothing.
- **R3 has a candidate feature list already** (curve-out probability, colour
  screw, wasted mana, reachability of KG motifs) and a sharp governing idea:
  **mechanism exists != mechanism is reliably reachable**.
- **The learner may be under-powered for this signal.** The attenuation result
  (`reports/run_level_calibration.md`) says the deck effect is understated by
  roughly 18% [3.5%, 31.6%] -- the signature of early-stopped boosting shrinking
  toward the mean. Check whether that is a grid limitation *before* concluding
  anything about representations, since an under-powered learner would understate
  R2 and R3 the same way it understated R1.
- **The strongest argument for R2/R3 is now empirical.** `base_p` is a historical
  win rate, so it carries the deck quality that travels with a player (section 13:
  "skill partially proxies expected deck quality because stronger players draft
  better decks"). If the skill proxy is absorbing deck quality, a better deck
  representation should claw some of it back. That is a testable prediction, not
  a hope.

## Two things that keep going wrong -- read before authoring a card

**Dry-run every gate first.** `echo "n" | ... compact run <repo> <id>` costs
nothing, changes no state, and has caught five card-authoring defects: a check
placed under the 60s validation cap, a manifest path that only resolved from a
subdirectory, a missing manifest-coverage criterion, an undeclared file the card
had to modify, and lint/type gates aimed at legacy code that was never clean.

**Estimate a card's runtime BEFORE writing it; if the work outlasts an executor
turn, put the action outside compact.** Card 017 demanded the executor finish
inline and the work simply did not fit: scoring six models over 194,215 rows
takes 8 s, but the 1000-replicate bootstrap over them takes **1581 s**. The
executor backgrounded it and was orphaned (seal intact -- the safe failure), and
the fault was the card's, not the executor's. Resampling dominates the scoring it
wraps by two orders of magnitude, so measure the cheap part and scale. The
sanctioned pattern is: perform the long action in a session, then `compact retry`
-- which does not invoke the executor, re-runs checks against the working tree,
and whose own success note reads "Retry completed successfully after manual
operator fixes". BLOCKED is the state that expects exactly this.

**The 60 s Output Validation cap is real and its failure looks like success.**
Card 017 put a 65 s test run under it and the audit recorded
`[FAIL] ... (60.1 s, exit code 0)` -- a timeout serialised as exit code 0,
sitting on a FAIL line. Moved to `## Checks` it ran 73.5 s and passed. Slow
commands go in Checks; the card now says so inline so nobody moves it back.

**A card whose work outlasts the executor's turn must finish it inline.**
compact's executor is a single `claude -p` call. Card 015 wrote its code, ran
its tests, launched the fit in the background and scheduled a wakeup — and when
the executor returned, the pipeline went straight to checks and the orphaned fit
died with the process. Never defer a card's real work to a wakeup that will
never fire.

**compact's executor and an interactive session are different Python
environments -- ALIGNED 2026-09-10, but not structurally.** compact runs in
`C:/GitHub/control_plane/.venv`; a session here runs `C:\Python314` + user site.
Their whole numerical stacks had drifted apart (xgboost 3.4.1 vs 3.1.2, numpy
2.5.1 vs 2.3.5, **pandas 3.0.3 vs 2.3.3**, pyarrow 25.0.1 vs 22.0.0, sklearn
1.9.0 vs 1.7.2, scipy 1.18.0 vs 1.16.3), and fits made in one did not reproduce
in the other. All six are now installed in control_plane's venv at the project's
versions, and **a T2 refit there reproduced all six committed artifacts
byte-for-byte** through the ordinary `--fit-t2` path. A fit now gives the same
bytes in either environment.

**The catch:** none of those six are declared dependencies of `control_plane`
(its `pyproject.toml` wants only `pydantic>=2`) -- they are incidental installs,
and this repo's `xgboost==3.1.2` pin does not bind that venv. A venv rebuild or
strict `uv sync` there would silently restore fresh versions. **Before card 017
fits anything, re-check the versions in both environments.** The durable fix is
to declare them in control_plane, or to make `deckbench` fail closed when the
environment does not match its pins; neither is done.

**Verify a generated artifact against the artifact, not against another
self-report -- and know which is which.** `Booster.save_raw()` re-serializes from
memory and stamps the *reading* library's version, so it is a fresh self-report,
not the artifact. Reading it produced a wrong diagnosis on 2026-09-10 (see
LABNOTEBOOK [2026-09-10 18:40]): boosters written by 3.4.1 read back as 3.1.2
purely because the reader was 3.1.2. The file's own bytes carry the writer's
version; `tests/test_deckbench_estimator.py::_booster_file_version` parses them.
Any method that loads an object before asking has already lost the evidence.
Related trap in the same family: information hand-added to a *generated* file
(card 014's banner in the T0 report) survives only until the next regeneration.

**Verify absence, not presence.** Three review FAILs on card 014 came from
checking that a corrected value was *present* rather than that the stale one was
*absent*. A stale value sitting beside a correct one passes the first test and
fails the second. When correcting a hash or an identifier, grep the whole repo
for the old value -- including `LABNOTEBOOK.md` -- and require zero hits.

Related: a card must not both regenerate an artifact under `## Checks` and
require a hash of that artifact to be written during execution. Checks run
*after* the executor writes its reports, so the hash is stale by construction.

## Hazards that cost real time — read these

- `python -m hobkg.cli ports` **with no arguments derives the 11-face pilot and
  overwrites the 210-face `card_ports.jsonl`.** Unrecognized flags are silently
  ignored, so `ports --help` destroys the artifact. Always pass `--all`.
- ~~`pytest` rewrites `data/review/*.jsonl` non-deterministically~~ **FIXED at
  card 013.** The cause was `PYTHONHASHSEED`: `phase3.py` built each record's
  lists from set operations, which iterate in hash order, randomized per process.
  `tools/determinism_audit.py --report` now checks all 69 derived artifacts
  across three seeds and exits non-zero if any is unstable. Run it after touching
  a writer.
- Compact applies **two different timeouts**: 300s for `## Checks`, **60s for
  `## Output Validation`**, neither documented in its GUIDE. Put slow commands
  in Checks. A validation timeout is serialized into the audit entry as
  `exit code 0`, which reads as success on a FAIL line.
- The gate displays skipped default checks as `[DEFAULT]` as though they will
  run. Display-only; `resolve_checks()` honours the skip.
- Append-only checks must compare **git blobs, not working copies** — `*
  text=auto` stores LF while the working copy is CRLF, so the naive comparison
  reports a violation on every append. `tools/check_append_only.py` does it
  correctly; use it rather than rolling your own.

## Loose ends

- **SETTLED 2026-09-10 — T1's target stays `won - base_p`. Do not reopen it.**
  § T1 is titled "Original bump" but the R it names builds its residual as
  `p_post - base_p`, a Beta posterior-mean win rate per stopped run, not a {0,1}
  game outcome (`scripts/R/04_real_inference_refactored.R` lines 311, 329). Card
  015 matches the **doc**; the doc departs from the artifact it names. Accepted
  deliberately: the doc is the spec, card 008 already chose the game as the unit
  against the R's draft level, and changing the target now would invalidate the
  card-015 fits and move T2's baseline before the single holdout read. See
  LABNOTEBOOK [2026-09-10 12:40] for the full reasoning.
  **Two things this obliges.** (1) Never describe T1 as a faithful reproduction
  of the original bump — it reproduces the arithmetic form on a *different
  outcome quantity and unit*. (2) T1 changes target, loss and link together, so
  an H2 T0-vs-T1 difference is a difference between **formulations as packages**;
  card 017 must not attribute it to the subtraction alone. (Substituting a
  `base_margin` log-odds offset to isolate the subtraction was considered and
  **rejected** — the R uses `reg:squarederror` at line 502, so that would be an
  improvement on the original, not a reproduction.)

- `control_plane` has local commits the operator assigned to another agent to
  investigate (`9a4b829` reviewer binary-file fix, `26eb892` a defects log entry).
  Its open defects are recorded in that repo's `SESSION_LOG.md`.
- **`git status` is not evidence of change in this repo; `git diff` is.** A full
  suite run can leave ~34 files "modified" (`data/graph_global/*`,
  `data/review/*.jsonl`) that are byte-identical to their blobs — `* text=auto`
  line-ending artifacts and stat-cache noise. This file used to warn about one
  such file; it is much broader than that. Always confirm with
  `git diff --name-only` before believing anything changed. (Card 013's
  determinism fix is holding; these are not real writes.)
- **The `modeling` extra pins `xgboost==3.1.2`** as of 2026-09-10. It is a pin,
  not a floor, because the fitted boosters are compared across target
  formulations in one irreversible holdout read. Changing it invalidates every
  artifact under `data/runs/`.
- The quarantined 2026-09-07 modeling pipeline is in `attic/haiku-2026-09-07/`.
  Its numbers are untrusted and must not be cited; its README explains why.

## How work is run

Cards under `tasks/`, executed by **compact** from the `control_plane` repo:

```
echo "n" | uv --directory C:/GitHub/control_plane run compact run <this repo> <id>   # gate dry run, no side effects
echo "y" | uv --directory C:/GitHub/control_plane run compact run <this repo> <id>   # real
uv --directory C:/GitHub/control_plane run compact review <this repo> <id>           # reviewer only
```

Dry-running the gate with `n` is free, changes no state, and has caught five
card-authoring defects. Do it every time. Note the executor may commit its own
work with trailers (card 013 did), so an empty `git diff` does not mean the card
produced nothing — check `git log` before concluding anything.

Commit trailers must be readable by git's own parser — see `INSTRUCTIONS.md` §8.

---

# KNOWLEDGE-GRAPH ARM (as of 2026-08-17)

The remainder of this file describes the KG build. Test counts here are stale
(the suite is now 718 tests, covering both arms); the KG facts are current.

## 1. Mandated project rules (always first)
- `CLAUDE.md` → it points to `INSTRUCTIONS.md`. **Read both fully.** They set the mission
  (mechanistic theory of Limited MTG; HOB KG build), the **append-only** discipline for
  `LABNOTEBOOK.md` and `CONVERSATION_LOG.md`, and the notebook entry format.

## 2. The build spec
- `docs/hob-knowledge-graph-build-spec.md` — authoritative plan: phases, semantic invariants,
  coverage-report and gold-set requirements. See §Completion criteria.

## 3. Current scientific state (most important for continuity)
- The **last ~5 entries of `LABNOTEBOOK.md`** (the tail runs Phase 6 v3 → v3.1 → v3.2 → v3.2.1
  → the **Phase 6 FREEZE decision**). This is where the "why" lives.
- Reviewer files: `docs/hob-kg-phase6-review-pt{1,2,3}.md`. Later Phase 6 reviews (v3.1, v3.2,
  v3.2.1, and the freeze) were **inline in chat**, summarized in the corresponding notebook entries.

## 4. Memory
Auto-loads via `MEMORY.md`. Flag the operational ones: `no-cd-in-bash.md` (avoid Bash
approval prompts), `phase3-llm-via-subagents.md`, `provenance-rigor.md`; and `phase4-frozen.md`
for the full build-phase status.

## Status
- **The HOB graph is FROZEN as the analytical reference implementation (at `8201109`).** ALL reviews
  **pt1–pt11 are resolved** (pt11 = clean bill of health, no blocking defect). Phases 0–6 + the
  full-spec re-scope + all completeness families + the executability (lifecycle) tier are built.
- **Two forward tracks, NOT part of the frozen analytical reference (each needs a go-ahead):**
  (a) **independent human semantic validation** — the one formal acceptance step for the existing
  spec (only a human can do it); (b) **portability** — extract the reusable engine + replace
  HOB-specific catalogues/patches (e.g. hand-authored `SAC_OUTLETS`) with deterministic extraction,
  declarative config, reusable rule templates, LLM escalation (`docs/portability_plan.md`; start with
  engine extraction + a small vertical slice, not another whole set). Deferred unless action-level
  simulation becomes near-term: per-card activation timing + payoff wiring (Snowslope-style).
- **227 tests pass, deterministic.** The frozen Phase 4 graph (`data/graph_global/{nodes,edges,
  conditions}.jsonl`) and Phase 5 projections are byte-stable; ALL other layers are purely additive.
- **Schema extension (recorded):** `assemble.GLOBAL_SIGNATURES` gained `TERMINATES`
  (`{Op,Event,State}→State`) and `HAS_ALTERNATIVE` (`Gate→{Gate,Cost,Op}`) for the lifecycle layer.
- **7th layer — executability (`lifecycle_*`, 16/68 + a projection).** Per Equipment host H a
  cause-specific `op:sacrifice:H` (`H HAS_ABILITY op:sacrifice:H` incoming; `MOVES_FROM battlefield`
  / `MOVES_TO graveyard` / `TERMINATES state:attachment:H` / `REFERENCES` the leave-battlefield
  invariant), and Stir's OR cost WIRED in (`ability:completeness:sac:{stir} REQUIRES gate:or-cost`
  `HAS_ALTERNATIVE {sac gate, cost:pay:{4}}`). `reproject-lifecycle` → **60
  `SACRIFICE_TERMINATES_ATTACHMENT`** executable bound traversals (`card:O → sac op → CONSUMES
  artifact ← HAS_TYPE ← face:P → op:sacrifice:P → TERMINATES state:attachment:P`). CLI: `lifecycle`
  / `reproject-lifecycle`. Union now **3,303 edges**; card-pair layer is now **7 tiers**.
- **pt5/pt8 LESSON (reinforced):** validate every projected path as a real, REACHABLE traversal
  (`step[i].target == step[i+1].source`, endpoints resolve to the cards, and — for lifecycle — the
  path reaches the claimed termination). Node existence ≠ executable connectivity.
- Card-pair layer = **7 separate tiers**: `card_pair_projection.jsonl` (5,278 mechanical),
  `_audit.jsonl` (3 llm_audit), `_repaired.jsonl` (8 graph_repair), `_mechanism.jsonl`
  (392 mechanism_repair — second-draw [all genuine drawers] / Dwarf-Equipment / noncreature-cast),
  `_equip.jsonl` (3,250 equip — continuous card→creature CAN_ATTACH_TO / MODIFIES_WHEN_ATTACHED /
  GRANTS_ABILITY_WHEN_ATTACHED), `_completeness.jsonl` (1,036 — token-entry ENABLES_TRIGGER /
  sac-outlet→dies ENABLES_TRIGGER / permanent-consumption SATISFIES_SACRIFICE_COST / IS_ELIGIBLE_SACRIFICE_TARGET),
  `_lifecycle.jsonl` (60 — executable SACRIFICE_TERMINATES_ATTACHMENT traversals).
- Additive graph layers (all origin-tagged, signature-valid, provenance-bearing): `legend_*` (58/113,
  CR 704.5j SBA); `mechanism_*` (3/111: `state:cards-drawn-this-turn` + `gate:second-draw` transition
  gate + `op:cast-noncreature-spell`); `equip_*` (107/173/16: per-Equipment `ability:equip:E`→
  `op:equip:E`→`state:attachment:E`, bound-creature effects via `obj:bound-creature:E HAS_TYPE creature`,
  ETB auto-attach distinct, `token:axe` covered, clause dispositions); `completeness_*` (28/101/3:
  `event:token-you-control-enters`, sac ops CAUSE death events, `gate:completeness:sac-cost:*` +
  `CONSUMES obj:type:{artifact,creature}` — dies edges gated by `cond:…-sacrificed-is-creature` for
  artifact+creature outlets; Stir's mutually-exclusive `gate:or-cost` is the SOLE causal parent of
  its sacrifice op — `ability REQUIRES gate:or-cost CAUSES {sac[or-sacrifice], op:pay[or-pay]}`, no
  direct ability→CAUSES→sac); `lifecycle_*` (14/65: cause-specific `op:sacrifice:H` reached via
  `CAN_UNDERGO`, `TERMINATES state:attachment:H`). Unified `coverage.json` = **3,306 edges / ~10,000 relations,
  0 provenance gaps, conditions_all_resolve=true**; `mechanism_modules.jsonl` (38 modules);
  `pair_index.jsonl` (37,249 pairs, 7 layers/columns); `structural_validation_set.jsonl`.
  `DEFERRED_INVARIANTS` empty; spec invariants #1–#17 modeled; schema extension predicates
  `TERMINATES` / `HAS_ALTERNATIVE` / `CAN_UNDERGO` recorded.
- **KEY LESSON (pt5):** a projected path must be validated as a real TRAVERSAL —
  `step[i].target == step[i+1].source` and `path[0]/path[-1]` resolve to the source/target cards —
  NOT just as a set of existing edges. `equip`/`completeness` `reproject()` self-gate this
  (`paths_continuous`/`paths_card_grounded`) and the tests assert it. Independently re-verify any
  new reprojection layer the same way.
- **Query CLI** (`src/hobkg/query.py`): `query-card` / `query-pair` / `query-mechanism` — any pair
  shows relation, direction, conditions, intermediate nodes, provenance, and inference origin
  across all 7 layers.
- **Build order for a full regen:** `assemble` → `project` → (audit) → `graph-repair`/`reproject` →
  `complete-mechanisms`/`reproject-mechanisms` → `equip`/`reproject-equip` →
  `completeness`/`reproject-completeness` → `lifecycle`/`reproject-lifecycle` → `modules` →
  `coverage` → `pair-index` → `structural-validation`.

## Remaining work for full-spec acceptance
1. **Independent human semantic validation** — the ONLY open item; a *human* hand-reviews a
   stratified sample (incl. ≥20 multi-edge pairs) per spec §Manual gold set. The automated
   `structural_validation_set` is deterministic assertions against the same graph, NOT a
   substitute (it is honestly labelled so). The query CLI gives a human everything needed.
- Housekeeping (pre-existing, non-blocking): `reports/coverage.md` has **two writers**
  (`pipeline.py` Phase 1 vs `coverage.py` Phase 6) that clobber each other — running full `pytest`
  leaves the Phase 1 version; regenerate with `python -m hobkg.cli coverage` for the Phase 6 one.
  Also `data/review/llm_{accepted,queued}.jsonl` reorder nondeterministically (set-iteration order);
  revert the spurious diff after running the suite.
- Possible future capability (not a spec gap): a separate capability/outcome projection layer.

## Operational gotchas
- `CONVERSATION_LOG.md` is appended by **hooks automatically** — do **not** hand-edit it.
- Run everything via `python -m hobkg.cli <cmd>` (package is pip-installed editable;
  **no `PYTHONPATH`, no leading `cd`** — those trigger Bash approval prompts).
- `LABNOTEBOOK.md` / `CONVERSATION_LOG.md` are **append-only**; corrections are new entries.
