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
- **ALL named build phases (0–6) are FROZEN** (Phase 6 accepted at `9cac50a`); the reviewer's
  **full-spec** re-scope AND all **completeness** families (gold-set + pt4/pt5/pt6) are now built.
  Reviews resolved through **pt6** (Equip path accepted); the completeness batch (`526bbb0`) awaits review.
  Only **independent human semantic validation** remains for full-spec acceptance.
- **218 tests pass, deterministic.** The frozen Phase 4 graph (`data/graph_global/{nodes,edges,
  conditions}.jsonl`) and Phase 5 projections are byte-stable; ALL other layers are purely additive.
- Card-pair layer = **6 separate tiers**: `card_pair_projection.jsonl` (5,278 mechanical),
  `_audit.jsonl` (3 llm_audit), `_repaired.jsonl` (8 graph_repair), `_mechanism.jsonl`
  (392 mechanism_repair — second-draw [all genuine drawers] / Dwarf-Equipment / noncreature-cast),
  `_equip.jsonl` (3,250 equip — continuous card→creature CAN_ATTACH_TO / MODIFIES_WHEN_ATTACHED /
  GRANTS_ABILITY_WHEN_ATTACHED), `_completeness.jsonl` (1,036 — token-entry ENABLES_TRIGGER /
  sac-outlet→dies ENABLES_TRIGGER / permanent-consumption SATISFIES_SACRIFICE_COST).
- Additive graph layers (all origin-tagged, signature-valid, provenance-bearing): `legend_*` (58/113,
  CR 704.5j SBA); `mechanism_*` (3/111: `state:cards-drawn-this-turn` + `gate:second-draw` transition
  gate + `op:cast-noncreature-spell`); `equip_*` (107/173/16: per-Equipment `ability:equip:E`→
  `op:equip:E`→`state:attachment:E`, bound-creature effects via `obj:bound-creature:E HAS_TYPE creature`,
  ETB auto-attach distinct, `token:axe` covered, clause dispositions); `completeness_*` (28/101/3:
  `event:token-you-control-enters`, sac ops CAUSE death events, `gate:completeness:sac-cost:*` +
  `CONSUMES obj:type:{artifact,creature}`). Unified `coverage.json` = **3,235 edges / 9,967 relations,
  0 provenance gaps, conditions_all_resolve=true**; `mechanism_modules.jsonl` (38 modules);
  `pair_index.jsonl` (37,249 pairs, 6 layers/columns); `structural_validation_set.jsonl`.
  `DEFERRED_INVARIANTS` empty; spec invariants #1–#17 modeled.
- **KEY LESSON (pt5):** a projected path must be validated as a real TRAVERSAL —
  `step[i].target == step[i+1].source` and `path[0]/path[-1]` resolve to the source/target cards —
  NOT just as a set of existing edges. `equip`/`completeness` `reproject()` self-gate this
  (`paths_continuous`/`paths_card_grounded`) and the tests assert it. Independently re-verify any
  new reprojection layer the same way.
- **Query CLI** (`src/hobkg/query.py`): `query-card` / `query-pair` / `query-mechanism` — any pair
  shows relation, direction, conditions, intermediate nodes, provenance, and inference origin
  across all 6 layers.
- **Build order for a full regen:** `assemble` → `project` → (audit) → `graph-repair`/`reproject` →
  `complete-mechanisms`/`reproject-mechanisms` → `equip`/`reproject-equip` →
  `completeness`/`reproject-completeness` → `modules` → `coverage` → `pair-index` → `structural-validation`.

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
