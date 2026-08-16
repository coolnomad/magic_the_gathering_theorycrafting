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
- **ALL named build phases (0–6) are FROZEN.** Phase 6 (higher-order mechanism assembly) was
  accepted at **`9cac50a`**. The HOB mechanistic KG is complete per the spec's completion criteria.
- **167 tests pass, deterministic.** The frozen Phase 4 graph (`data/graph_global/{nodes,edges,
  conditions}.jsonl`) and Phase 5 projections are byte-stable; the graph-repair and legend layers
  are purely additive.
- Card-pair layer = 3 separate tiers: `card_pair_projection.jsonl` (5,278 mechanical),
  `card_pair_projection_audit.jsonl` (3 llm_audit), `card_pair_projection_repaired.jsonl` (8 graph_repair).
- Phase 6 deliverables: `mechanism_modules.jsonl` (37 modules), the additive legend-rule SBA layer
  `legend_{nodes,edges}.jsonl` (58 nodes / 113 edges, CR 704.5j), unified `coverage.json`
  (2,850 edges), `pair_index.jsonl` (37,249 pairs), `structural_validation_set.jsonl`.

## Remaining work — follow-on capability only, NOT gaps in the frozen graph (each needs a go-ahead)
1. **Invariant #2** — Recruit → second-draw → Master's Councillors: needs a turn-scoped
   cards-drawn-this-turn count state/gate (recorded in `coverage.DEFERRED_INVARIANTS`).
2. **Dwarf/Equipment → Dáin's Company** — targeted audit → repair → reprojection round
   (same machinery as the 8 already repaired).
3. **Noncreature cast → Bothersome Noisemaker** — targeted audit → repair → reprojection round.
4. **Independent human semantic validation** — distinct from the automated structural checks
   (the "structural validation set" is explicitly NOT an independent human gold set).
- Housekeeping (pre-existing, non-blocking): `reports/coverage.md` has **two writers**
  (`pipeline.py` Phase 1 vs `coverage.py` Phase 6) that clobber each other — running full `pytest`
  leaves the Phase 1 version; regenerate with `python -m hobkg.cli coverage` for the Phase 6 one.
  Also `data/review/llm_{accepted,queued}.jsonl` reorder nondeterministically (set-iteration order);
  revert the spurious diff after running the suite.

## Operational gotchas
- `CONVERSATION_LOG.md` is appended by **hooks automatically** — do **not** hand-edit it.
- Run everything via `python -m hobkg.cli <cmd>` (package is pip-installed editable;
  **no `PYTHONPATH`, no leading `cd`** — those trigger Bash approval prompts).
- `LABNOTEBOOK.md` / `CONVERSATION_LOG.md` are **append-only**; corrections are new entries.
