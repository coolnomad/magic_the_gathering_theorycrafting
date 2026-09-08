# Magic: The Gathering — Theorycrafting

Building a **mechanistic theory of Limited Magic: The Gathering**, Draft first.

Mechanistic means models rather than heuristics: explicit, falsifiable statements
about *why* things work, grounded in game mechanics — mana, tempo, card advantage,
board state, curve, pack/pick dynamics — not in "this deck feels good."

**New here? Read [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) first.** It is the operating
contract for this repository and it binds humans and language models alike.

## The two arms

**1. A mechanistic knowledge graph** of *The Hobbit* (HOB) — a typed multigraph of
cards, faces, abilities, operations, conditions and gates, plus derived card-pair
projections. Built in four layers:

| Layer | What | Where |
|---|---|---|
| 1 | card text, normalized | `data/normalized/faces.jsonl` — 210 faces, 193 cards |
| 2 | per-card **ports** — what a card is, looks for, offers | `src/hobkg/ports.py` → `data/graph_global/card_ports.jsonl` |
| 3 | set-wide network (a *view*, never stored) | `src/hobkg/network.py` |
| 4 | capacity projection | planned |

Phases 0–6 of [`docs/hob-knowledge-graph-build-spec.md`](./docs/hob-knowledge-graph-build-spec.md)
are complete and frozen, with an effect-semantics overlay through Phase 4f.
Layer 2 derives ports for all 210 faces with zero unresolved abilities.

**2. A statistical modeling benchmark** over 43,161 real Premier Draft events
(241,727 games), estimating what deck construction contributes to win probability
once player skill is accounted for. The design is two axes held against frozen
splits, one learner family and one metric panel:

- **target formulation** — T0 raw outcome, T1 bump against the historical skill
  proxy, T2 bump against a cross-fitted learned skill model;
- **deck representation** — R0 skill only, R1 card identity, R2 knowledge graph,
  R3 game script, and their combinations.

The governing spec is
[`docs/MTG_Deck-Strength_Modeling_Benchmark.md`](./docs/MTG_Deck-Strength_Modeling_Benchmark.md);
the current pipeline state is [`docs/modeling_pipeline.md`](./docs/modeling_pipeline.md).
(`docs/Model_Building.md` is superseded and kept only as record.)

The arms meet at **R2**: whether the mechanistic graph carries predictive signal
that raw card identity does not is the load-bearing empirical test of this project.
R3 sharpens it further — knowing a mechanism *exists* is not the same as knowing
it is *reliably reachable* in a real game.

## The record

Three living documents, and **the first two are append-only** — never edited,
never reordered, never deleted. Corrections are new entries that reference the old
ones. Dead ends stay in the record; being wrong is part of the data.

- [`LABNOTEBOOK.md`](./LABNOTEBOOK.md) — the scientific record. Typed entries:
  `DEFINITION`, `HYPOTHESIS`, `EXPERIMENT`, `OBSERVATION`, `RESULT`, `MODEL`,
  `DECISION`, `QUESTION`, `CORRECTION`.
- [`CONVERSATION_LOG.md`](./CONVERSATION_LOG.md) — verbatim transcript of every
  exchange, appended automatically by hooks in `.claude/hooks/`.
- [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) — the rules.

## How work gets done

Bounded **task cards** under `tasks/`, run as a worker/reviewer handshake: a worker
implements and commits, a reviewer independently validates against the governing
spec and writes a structured verdict under `docs/`, repairs are new commits. State
transitions are recorded in `cycle/ledger.jsonl`.

Commits in this arc carry a machine-readable trailer block — `Role`, `Phase`,
`Iteration`, `Verdict` — that git's own parser can read. This is enforced by
`tests/test_commit_trailers.py` over every commit since epoch `0315399`, after the
discovery that 36 of 80 earlier commits had trailer blocks that *looked* correct
but were invisible to git because a blank line orphaned them. See `INSTRUCTIONS.md`
§8 before writing one.

## Layout

```
data/raw/          source snapshots (Scryfall, comprehensive rules, 17Lands)
data/normalized/   layer-1 card text
data/graph_global/ the knowledge graph + port records
data/vocabulary/   declared concepts, op map, selector grammar
data/processed/    derived modeling artifacts (untracked; MANIFEST.sha256 pins them)
src/hobkg/         the graph pipeline
src/data/          modeling data preparation
scripts/           modeling pipeline (Python) + scripts/R (earlier causal analysis)
tests/             pytest suite
docs/              build specs, review documents, protocols
reports/           generated reports and dashboards
tasks/             task cards
```

## Running

```bash
pip install -e .
python -m pytest -q
python -m hobkg.cli ports --all --validate
```

Raw 17Lands data is not tracked; fetch it per `data/raw/source_manifest.json`
before running the modeling pipeline.
