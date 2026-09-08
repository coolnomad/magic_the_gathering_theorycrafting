# Skill proxy `base_p` -- reliability-adjusted historical win rate

Card 005. `deckbench.skill` reproduces the benchmark's nuisance skill representation `base_p`: the R0 representation and T1's fixed baseline (benchmark sections 3-4). It is a closed-form shrinkage of two columns of the game-level model table; it fits nothing, tunes nothing, and reads no outcome.

> **`base_p` is not a measurement of skill.** It is an interim nuisance representation reproduced verbatim from the inherited R implementation so that the T1-vs-T2 comparison stays interpretable (benchmark section 3). Nothing here -- code, column names, or prose -- calls it skill, true skill, or player strength.

Source table: `data/processed/model_table.parquet`
Output: `data/processed/skill_features.parquet`

## The estimator

```
base_p = invlogit( (hist_w * logit(base_p_raw) + LAMBDA * logit(mu))
                   / (hist_w + LAMBDA) )
```

- `base_p_raw` -- the historical game-win-rate bucket, column `user_game_win_rate_bucket`.
- `hist_w` -- reliability weight set by the games-played bucket (`user_n_games_bucket`) through the inherited map below.
- `mu` -- the mean of `base_p_raw` over the estimation population (defined below); computed here as **0.546211**.
- `LAMBDA` -- shrinkage strength toward `logit(mu)`, fixed at **5**.

The `hist_w` map is kept as **data, not arithmetic**, so the inherited seven-entry assumption is visible and changeable in one place:

| games-played bucket | hist_w |
| --- | --- |
| 1 | 1 |
| 5 | 2 |
| 10 | 3 |
| 50 | 6 |
| 100 | 8 |
| 500 | 12 |
| 1000 | 14 |

A games-played bucket absent from this map fails the run naming the value; it is never defaulted, rounded to a neighbour, or dropped. The buckets observed in this file are all present in the map.

## Clipping

Every probability is clipped symmetrically into `[CLIP_EPS, 1 - CLIP_EPS]` with **CLIP_EPS = 1e-07** before any logit, so a bucket of exactly 0 or 1 is representable. The clip is symmetric on purpose: an asymmetric clip would bias the logit and the bias would survive the shrinkage.

## Estimation population and `mu`

The estimation population for `mu` is **every observation that carries a historical win-rate bucket**: 241561 of 241727 game-level rows. `mu` is their per-observation (per-game) mean of `base_p_raw` = **0.546211**. No row is excluded on any outcome-dependent criterion, and `won` is never read to select the population.

`mu` is a per-game mean, so a draft with more games weights `mu` more heavily; because the historical bucket is constant within a draft (see below), this is the only weighting choice that arises, and it is stated rather than hidden.

## Missing historical win-rate buckets -- a finding, and a documented deviation

**166 of 241727 observations carry an empty historical win-rate bucket** (66 at games-played bucket 1, 100 at games-played bucket 5). Every one sits in the lowest games-played buckets: these are players with too few recorded games to have an established historical win rate yet. The audit (`reports/modeling_data_audit.json`) did not count them; this card surfaces them.

The quarantined pipeline filled exactly this gap with `0.5` (see `attic/haiku-2026-09-07/README.md`), inserting a fabricated average player at the centre of the distribution and -- because `mu` is the mean of the same column -- dragging the shrinkage target itself. This card does the opposite: a missing historical bucket is **never imputed** with 0.5, the mean, or any placeholder. It is recorded as **null** in both `base_p_raw` and `base_p`, and **excluded from the estimation population** so it cannot move `mu`.

This is a deliberate, documented deviation from the letter of the card's "a missing bucket fails the run" criterion, made per the benchmark's rule that any deviation is documented rather than silently changed (section 5). The run fails loudly on every *unexpected* bucket state (an unmapped games bucket, a missing games bucket, a non-empty bucket that will not parse); it treats only the *structurally-absent* historical win rate of a near-new player as a known, characterised null. The final disposition of these rows -- keep with a null proxy, or exclude from the modelling set -- is an operator decision that belongs to the phase-1 review at card 007, with this count now in front of it.

## Within-draft variation of the skill columns

The audit reports the two buckets this card uses are **constant within every draft** (`user_game_win_rate_bucket` non-constant in 0 drafts, `user_n_games_bucket` in 0). The proxy is computed per observation directly from that observation's own row, so no within-draft reconciliation rule is needed: each game inherits its player's buckets unchanged. (`rank`, which this card does not use, varies within 5420 drafts.)

## Outputs and provenance

- `skill_features.parquet` -- columns `obs_id`, `base_p_raw`, `base_p`. **Both** the input bucket and the shrunk value are saved, not just the shrunk value. Keyed on the observation id; it joins to `model_table.parquet` on that id with no unmatched rows in either direction (every model-table row is present; the null-proxy rows are present too).
- The proxy is emitted as its own table rather than mutating `model_table.parquet`, so card 004's artifact stays byte-stable and the provenance stays legible.
- `MANIFEST.sha256` is rewritten with repository-root-relative paths over card 004's three artifacts and this card's, so `sha256sum -c data/processed/MANIFEST.sha256` verifies from the repository root.

## Determinism

The transform is closed-form Python arithmetic in a fixed row order (the model table's order), so two consecutive runs produce a byte-identical parquet. The hash is pinned in `data/processed/MANIFEST.sha256`.
