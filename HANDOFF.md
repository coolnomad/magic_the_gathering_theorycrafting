# HANDOFF — read this first

A fresh session is picking up the HOB (The Hobbit) mechanistic knowledge-graph build.
Read the items below **in order**, then check the status line, then wait for direction.

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
