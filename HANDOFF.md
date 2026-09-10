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

**Cards 001-015 are all DONE.** Phase 1 is complete and phase 2's infrastructure
plus its first two target rows are built. Milestone `benchmark-p1` is detected but
**not yet confirmed** (`compact milestone <repo> benchmark-p1`).

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

  016  T2  -- bump against a CROSS-FITTED learned baseline         NOT WRITTEN
  017  the single holdout read, all models, paired bootstrap       NOT WRITTEN

**016 is SMALLER than this file used to claim.** The old warning said card 009's
estimator "may need an out-of-fold path it does not have". **It has one.**
`estimator._out_of_fold_predictions` predicts every development row from a
booster trained without that row's fold, using the frozen folds, and card 009's
docstring names T1/T2 as the reason it exists. More: T2's baseline is **already
fitted**. `m_hat_-i(S_i) = E[Y|S]` out-of-fold *is* `T0_R0`'s prediction vector
(`data/runs/T0_R0_predictions.parquet`, 194,215 rows, binary objective, S =
`[base_p]`, no NaN), and the full-data `m_hat(S)` for the final reconstruction
is `data/runs/T0_R0.xgb`. Verified 2026-09-10.

Three things card 016 must still decide, none of them blocking:
1. **Hyperparameter selection is not fold-honest.** The out-of-fold *training*
   is, but `chosen` was selected by CV over all dev folds, so fold k's baseline
   comes from a booster trained without fold k under hyperparameters informed by
   it. Section T2's requirement is about training; this is a mild standard leak.
   Decide strict nested CV vs accept-and-document, in the card.
2. **Two different `m_hat` are needed.** Out-of-fold for constructing the
   training residuals, full-data refit for the final `p_hat = m_hat(S) + B_hat`.
   Both exist; the card must not use one where the other belongs.
3. **Reuse T0_R0's artifacts or refit?** Reuse is cheaper and identical by
   construction, but couples 016 to card 011's outputs.

**017 is the one that answers the question** -- six models, one holdout read,
one ledger line, paired cluster bootstrap on the differences.

## Two things that keep going wrong -- read before authoring a card

**Dry-run every gate first.** `echo "n" | ... compact run <repo> <id>` costs
nothing, changes no state, and has caught five card-authoring defects: a check
placed under the 60s validation cap, a manifest path that only resolved from a
subdirectory, a missing manifest-coverage criterion, an undeclared file the card
had to modify, and lint/type gates aimed at legacy code that was never clean.

**A card whose work outlasts the executor's turn must finish it inline.**
compact's executor is a single `claude -p` call. Card 015 wrote its code, ran
its tests, launched the fit in the background and scheduled a wakeup — and when
the executor returned, the pipeline went straight to checks and the orphaned fit
died with the process. Never defer a card's real work to a wakeup that will
never fire.

**Verify a generated artifact against the artifact, not against another
self-report.** Cards 011 and 014 recorded `xgboost_version` from the Python
package's `__version__` while the compiled library that actually trained was a
different version; the record and the wrapper agreed with each other because
both came from the same wrong source, and a past session cross-checked exactly
that way and was reassured. The booster on disk embeds the truth. Two related
traps in the same family: information hand-added to a *generated* file (card
014's banner in the T0 report) survives only until the next regeneration, and
`ruff`/`mypy` are **not installed** in this environment despite earlier cards
recording those gates as clean.

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

- **Open design question, recorded not resolved:** the doc's T1 target is not
  the original's target. § T1 says "reproduce the original deck-bump formulation
  as closely as possible" and defines `B_i = Y_i - p_base,i` on the raw outcome,
  but the R being reproduced uses `p_post - base_p`, where `p_post` is a Beta
  posterior-mean win rate per stopped run, not a {0,1} game outcome
  (`scripts/R/04_real_inference_refactored.R` lines 311, 329). Card 015 matches
  the **doc**; the doc departs from the artifact it names. Changing T1's target
  would invalidate the card-015 fits, so this is a design decision, not a
  correction. See LABNOTEBOOK [2026-09-10 12:10]. (T1's use of
  `reg:squarederror` *is* faithful — the R uses it at line 502, which is why
  swapping in an `base_margin` log-odds offset would be an improvement on the
  original, not a reproduction of it.)

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
