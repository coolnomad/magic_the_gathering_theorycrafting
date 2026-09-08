# Skill proxy `base_p` -- reliability-adjusted historical win rate

Card 005 (re-frozen at card 008). `deckbench.skill` reproduces the benchmark's nuisance skill representation `base_p`: the R0 representation and T1's fixed baseline (benchmark sections 3-4). It is a closed-form shrinkage of two columns of the game-level model table; it fits nothing, tunes nothing, and reads no outcome.

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
- `mu` -- the mean of `base_p_raw` over the modeling population (defined below); computed here as **0.546211**.
- `LAMBDA` -- shrinkage strength toward `logit(mu)`, fixed at **5**.

## Games-played buckets -- observed set and inherited weights

The set of games-played buckets the run accepts is **derived from the data**: the population contains buckets `{1, 5, 10, 50, 100, 500}`, and the run processes exactly those. The *weight* attached to each is the inherited modeling assumption, kept as **data, not arithmetic**, so it is visible and changeable in one place:

| games-played bucket | hist_w |
| --- | --- |
| 1 | 1 |
| 5 | 2 |
| 10 | 3 |
| 50 | 6 |
| 100 | 8 |
| 500 | 12 |

A games-played bucket observed with no declared weight fails the run naming the value; it is never defaulted, rounded to a neighbour, or dropped. At card 008 the inherited `1000` entry was removed from the map: it declared a weight for a bucket this dataset does not contain and so was never exercised. The map's keys are now exactly the buckets the population presents.

## Clipping

Every probability is clipped symmetrically into `[CLIP_EPS, 1 - CLIP_EPS]` with **CLIP_EPS = 1e-07** before any logit, so a bucket of exactly 0 or 1 is representable. The clip is symmetric on purpose: an asymmetric clip would bias the logit and the bias would survive the shrinkage.

## Modeling population and `mu`

Every one of the **241561** population rows carries a historical win-rate bucket -- the null-win-rate games were excluded upstream at card 008, at the point the model table defines the population. So `mu` is the per-observation (per-game) mean of `base_p_raw` over the **whole population** = **0.546211**. No row is excluded on any outcome-dependent criterion, and `won` is never read to select the population.

This value is unchanged from the pre-008 freeze (`mu = 0.546211`). That is expected, not a coincidence: card 005 already computed `mu` over the rows that carried a bucket -- the same 241,561 rows that now constitute the whole population -- so removing the 166 null-bucket games removed exactly the rows that were never in the mean. The old and new `mu` coincide by construction.

`mu` is a per-game mean, so a draft with more games weights `mu` more heavily; because the historical bucket is constant within a draft (see below), this is the only weighting choice that arises, and it is stated rather than hidden.

## No null win-rate buckets (card 008 removed the carve-out)

Card 005 permitted a structurally-absent historical win-rate bucket as a counted null, because failing on it would have made that card's own output unsatisfiable. Card 008 excluded those games from the modeling population upstream, so the branch is unreachable -- and unreachable safety behaviour is worse than none. It is **removed**: a null win-rate bucket in the population is now a defect that stops the run naming the observation, restoring the original intent of card 005's criterion that any null in the population is a defect. The quarantined pipeline filled exactly this gap with `0.5` (see `attic/haiku-2026-09-07/README.md`), dragging the shrinkage target with a fabricated average player; nothing here imputes a missing bucket with 0.5, the mean, or any placeholder.

## Within-draft variation of the skill columns

The audit reports the two buckets this card uses are **constant within every draft** (`user_game_win_rate_bucket` non-constant in 0 drafts, `user_n_games_bucket` in 0). The proxy is computed per observation directly from that observation's own row, so no within-draft reconciliation rule is needed: each game inherits its player's buckets unchanged. (`rank`, which this card does not use, varies within 5420 drafts.)

## Outputs and provenance

- `skill_features.parquet` -- columns `obs_id`, `base_p_raw`, `base_p`. **Both** the input bucket and the shrunk value are saved, not just the shrunk value. Keyed on the observation id; it joins to `model_table.parquet` on that id with no unmatched rows in either direction -- both tables carry exactly the modeling population, and neither `base_p_raw` nor `base_p` contains a null.
- The proxy is emitted as its own table rather than mutating `model_table.parquet`, so card 004's artifact stays byte-stable and the provenance stays legible.
- `MANIFEST.sha256` is rewritten with repository-root-relative paths over card 004's three artifacts and this card's, so `sha256sum -c data/processed/MANIFEST.sha256` verifies from the repository root.

## Determinism

The transform is closed-form Python arithmetic in a fixed row order (the model table's order), so two consecutive runs produce a byte-identical parquet. The hash is pinned in `data/processed/MANIFEST.sha256`.
