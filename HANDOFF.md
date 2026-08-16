# HANDOFF — read this first

A fresh session is picking up the HOB (The Hobbit) mechanistic knowledge-graph build.
Read the items below **in order**, then check the status line, then wait for direction.

## 1. Mandated project rules (always first)
- `CLAUDE.md` → it points to `INSTRUCTIONS.md`. **Read both fully.** They set the mission
  (mechanistic theory of Limited MTG; HOB KG build), the **append-only** discipline for
  `LABNOTEBOOK.md` and `CONVERSATION_LOG.md`, and the notebook entry format.

## 2. The build spec
- `docs/hob-knowledge-graph-build-spec.md` — authoritative plan: phases, semantic invariants,
  coverage-report and gold-set requirements.

## 3. Current scientific state (most important for continuity)
- The **last ~4 entries of `LABNOTEBOOK.md`** (~1080 lines; the tail runs graph-repair →
  Phase 6 v1 → v2 → v3 → **v3.1**). This is where the "why" lives.
- Reviewer files: `docs/hob-kg-phase6-review-pt1.md` and `-pt2.md`.
  The **v3.1 review was inline, not a file** — it is summarized in the v3.1 notebook entry.

## 4. Memory
Auto-loads via `MEMORY.md`. Flag the operational ones: `no-cd-in-bash.md` (avoid Bash
approval prompts), `phase3-llm-via-subagents.md`, `provenance-rigor.md`.

## Status
- **Phase 6 v3.1 committed at `197e314`, awaiting external review.**
- Phases 4, 5 (Parts 1+2), and graph-repair are **frozen/accepted**.
- **166 tests pass, deterministic.** The frozen Phase 4 graph and Phase 5 projections are
  byte-stable; the legend layer (`data/graph_global/legend_{nodes,edges}.jsonl`) is purely additive.
- **Deferred, reviewer-acknowledged — item 6:** Dáin's Company (Dwarf/Equipment) and
  Bothersome Noisemaker (noncreature-cast) need a *fresh audit → repair → reprojection round*
  (new primitive producer/consumer edges), **not** discovery. **Do not start without a go-ahead.**

## What v3.1 changed (the last review's six findings)
1. Renamed `gold_set` → `structural_validation_set` (`.jsonl` + `reports/structural_validation.md`,
   CLI `structural-validation`, old name aliased). Report states plainly it is NOT an independent
   human gold set — deterministic structural assertions against the same graph.
2. De-tautologized Saga (requires `REFERENCES_RULE rule:saga` or a `counter:lore` state) and
   self-pair (reflexive effect must not route through an `obj:another*/obj:other*` class).
3. Multi-edge sampler now draws combos from the **union of all three projection layers**;
   test checks distinct **combinations**, not pair-IDs.
4. Substantive #11: legend rule materialized as a state constraint (55 `state:legend:{name}`
   States, `max_controlled=1`), surfaced as `module:legend-rule`.
5. Substantive #12: all 31 self-pair metaedges verified reflexive (`participant_status: resolved`,
   no another/other routing), per relation.
6. Strengthened #2: graph correctly refuses a Recruit→Councillors edge (second-draw ordering is
   unmodeled), verified both directions across all three projection layers.

## Operational gotchas
- `CONVERSATION_LOG.md` is appended by **hooks automatically** — do **not** hand-edit it.
- Run everything via `python -m hobkg.cli <cmd>` (package is pip-installed editable;
  **no `PYTHONPATH`, no leading `cd`** — those trigger Bash approval prompts).
- `LABNOTEBOOK.md` / `CONVERSATION_LOG.md` are **append-only**; corrections are new entries.
