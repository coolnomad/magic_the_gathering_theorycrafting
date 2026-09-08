# Modeling arm — current state

**There is no working modeling pipeline in this repository right now.** The arm is
between a discarded implementation and a rebuild that has not started.

## Status, 2026-09-07

Every Python script that produced the previous M0/M1 results was quarantined to
[`attic/haiku-2026-09-07/`](../attic/haiku-2026-09-07/), together with everything
it emitted (`results/`, `figures/`, `data/processed/`). That code did not follow
its specification reliably, so its outputs are untrusted; the reasoning and the
catalogue of known defects are in
[the attic README](../attic/haiku-2026-09-07/README.md), and the decision is
recorded in `LABNOTEBOOK.md`.

Do not cite the numbers that were previously reported here. They contradicted each
other across runs, and where an interval was computed it crossed zero.

Unaffected by the quarantine: `scripts/R/` (the earlier causal analysis, written
2025-12 to 2026-02) and the entire knowledge-graph arm.

## What survives

**The raw data.** `data/raw/game_data_public.HOB.PremierDraft.csv.gz` — the 17Lands
public game-level dataset, one row per game: 241,727 rows across 43,161 drafts,
1,165 columns, `draft_time` spanning 2026-08-11 to 2026-08-29. Deck composition is
carried by the `deck_*` columns; the 18 non-card columns include `draft_id`,
`draft_time`, `rank`, `opp_rank`, `on_play`, `num_turns`, `won`.

The file is not tracked in git (16 MB, binary, publicly re-downloadable). Its URL,
SHA256 and shape are in [`data/raw/source_manifest.json`](../data/raw/source_manifest.json).
Fetch it and verify the hash.

**Three findings**, established by the discarded work and worth carrying forward:

1. `identity_matrix_*` was a 43,160 × 6 rank-bucket indicator matrix, not a deck
   representation. The deck representation is
   `D_ij = count(card j in deck i) / deck_size_i`.
2. `rank` is a six-level skill bucket. This dataset has **no** persistent player
   identifier, which is why splitting must be by draft ID and leakage control is
   weaker than a player-grouped design would give.
3. The reliability-adjusted historical skill proxy — `hist_w` map, λ = 5,
   shrinkage in logit space toward μ — is reusable as the fixed baseline `p_base`.
   It is a nuisance representation and is not a measurement of skill.

## What governs the rebuild

[`MTG_Deck-Strength_Modeling_Benchmark.md`](./MTG_Deck-Strength_Modeling_Benchmark.md).
It supersedes `Model_Building.md` in full.

The design is two axes against frozen splits, one learner family, one metric panel:

- **Target formulation** — T0 raw outcome, T1 bump against the historical skill
  proxy, T2 bump against a cross-fitted learned skill model.
- **Deck representation** — R0 skill only, R1 card identity, R2 knowledge graph,
  R3 game script, R4/R5 combinations.

Its §17 fixes the first step and halts before any model is fit: audit the raw
game-level data, quantify how often deck configuration changes within a draft,
build the game-level table, verify the skill variables, freeze the splits, produce
an audit report, stop for review.

That step is a clean task card — every criterion is checkable, and no holdout is
opened. It is the next thing to do.

## Interpretive caution, carried forward

The 7-wins / 3-losses stopping rule concentrates the outcome distribution and puts
an irreducible binomial-sampling floor under the residual variance. A low R² here
is not comparable to R² from an unbounded-length outcome, and the ceiling is
unknown without the latent `p_i` distribution. Do not describe any observed R² as
approaching a theoretical maximum.

And per §13 of the benchmark: a null incremental R² does **not** establish that
deck composition has no causal effect on win probability. It supports only the
narrower claim that a given representation, learner and dataset failed to detect
one.
