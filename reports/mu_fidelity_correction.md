# `mu` computed per draft — a fidelity correction to the skill proxy (card 014)

`mu`, the shrinkage target in the skill proxy `base_p` (`deckbench.skill`), was
the mean of `base_p_raw` over **games**. The R implementation this proxy
reproduces computes it over **drafts**. Card 014 changes ours to match and
carries the change through everything that depends on it.

This is a correction to **fidelity**, not an improvement to skill estimation.
Benchmark section 3 is explicit that the proxy is *reproduced, not improved*, so
the target-formulation experiment (T0/T1/T2) is isolated from changes in skill
estimation. A per-game `mu` is not the proxy the earlier work used, so the
implementation prior to this card quietly failed that requirement. The argument
for the change is that the benchmark asked for a reproduction and this was not
one — **not** that the numbers were badly wrong. They are not: the shrinkage
target moves by 0.0129 and any individual `base_p` by at most about 0.011.

## What the R implementation does

`base_p` is inherited verbatim from
`scripts/R/04_real_inference_refactored.R`. There the data frame `x` is built at
**draft/event level** — one row per Arena run:

- `x[, A := as.integer(event_match_wins)]` (line ~302) and the surrounding block
  assemble `x` from `decks.parquet`, whose grain is the draft.
- `mu <- mean(x$base_p_raw)` (**line 324**) is therefore a mean over drafts, one
  value per draft.

Our modeling table is at **game** grain (benchmark section 6: the deck changes
within a draft, so the game is the observational unit). Averaging that table's
`base_p_raw` directly is a per-game mean, which is not what line 324 computes.
Card 014 groups the rows by `draft_id` and averages one value per draft instead.

The per-draft value is well defined because the historical win-rate bucket is
**constant within every draft** (the audit records it non-constant in 0 drafts).
`deckbench.skill` verifies this and stops the run if any draft ever presents two
different buckets, rather than silently picking one.

## The two values

| quantity | value |
| --- | --- |
| `mu`, per game (replaced) | **0.546211** |
| `mu`, per draft (used, matches R line 324) | **0.533339** |
| difference (per game − per draft) | **+0.012872** |

Measured on the frozen card-008 population: **241,561 games across 43,102
distinct drafts**, unchanged by this card (no row added, dropped, or
reweighted). `base_p_raw` is unchanged for every row; only `base_p` moves.

## Why they differ: stronger players play more games

Under the Arena 7-wins / 3-losses run structure, a good run is up to ten games
and a bad one as few as three, so a player's game count rises with their
historical win rate. Measured on the frozen population, mean games per draft by
historical win-rate bucket:

| historical win-rate bucket | mean games / draft | drafts |
| --- | --- | --- |
| < 0.45 | 4.46 | 7,242 |
| 0.45–0.55 | 5.38 | 16,089 |
| 0.55–0.66 | 6.09 | 15,741 |
| 0.66–0.86 | 6.66 | 3,944 |
| ≥ 0.86 | 6.65 | 86 |

A per-game average therefore over-samples the strong players and pulls the
shrinkage target upward. Averaging per draft gives every draft equal weight and
removes that bias — which is exactly the reproduced estimator's behaviour.

## The bias lands where the proxy does the most work

`mu` only matters when `hist_w` is small, i.e. for the near-new players the
shrinkage exists to protect. Measured change in `base_p` (per-draft minus
per-game `mu`), by games-played bucket:

| games-played bucket | `hist_w` | mean Δ`base_p` | rows |
| --- | --- | --- | --- |
| 1 | 1 | −0.0085 | 1,236 |
| 5 | 2 | −0.0090 | 6,625 |
| 10 | 3 | −0.0080 | 77,934 |
| 50 | 6 | −0.0058 | 73,471 |
| 100 | 8 | −0.0049 | 80,480 |
| 500 | 12 | −0.0037 | 1,815 |

Across all rows the mean shift is −0.0063 and the maximum magnitude is 0.0108.
So a player with one game of history was previously credited about a percentage
point more than the reproduced proxy gives them, and a seasoned player about a
third of that. Every `base_p` moves down (the shrinkage target dropped), and the
move is largest exactly where the proxy leans hardest on `mu`.

## What was re-emitted, and why the cascade stops where it does

- **`data/processed/skill_features.parquet`** re-emitted. `base_p_raw` unchanged;
  only `base_p` moves. SHA256 `4ac7ee8e…` → `8e86df3a…`;
  `data/processed/MANIFEST.sha256` regenerated (root-relative paths;
  `sha256sum -c` passes from the repository root). The other four manifest
  members — `model_table.parquet`, `deck_identity.parquet`,
  `card_identity_manifest.csv`, and `model_split.parquet` — do not depend on
  `base_p` and are byte-identical; **only the skill hash changed** (the manifest
  otherwise matches the committed `card-004/005/006` five-member form).
- **`deckbench.skill` now keeps `model_split.parquet` pinned.** The proxy stage
  runs before the split stage, so on a fresh build it writes a four-member
  manifest and `deckbench.split` later adds the split as the fifth. But when the
  split already exists — as here, re-emitting the proxy — `deckbench.skill` now
  includes it, writing the canonical five-member manifest **byte-identically** to
  what `deckbench.split` writes. Without this, running the skill build alone
  would silently un-pin `model_split.parquet` from the integrity manifest and
  leave the working tree inconsistent with the committed state.
- **`data/runs/T0_R0*` and `data/runs/T0_R1*`** refitted. R0 is `[base_p]` and R1
  is `base_p` plus the 193 card fractions, so both consumed the changed column
  and card 011's fits were stale the moment `mu` moved. The refit goes through
  `deckbench.estimator.fit_and_predict` unchanged, same seed (20260908), same
  frozen split. The recorded `split_sha256` is still
  `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`, matching
  `data/splits/split_manifest.json`. The chosen hyperparameters and round counts
  shifted with the new feature (R0 325 → 367 rounds; R1 to a different grid point,
  194 → 267 rounds); `reports/t0_development_fits.md` was regenerated.
- **The split does not move.** `model_split.parquet` is keyed on `draft_id` and
  `draft_time`, neither of which depends on `base_p`, so its hash is unchanged and
  no re-split is needed.

**Why now rather than after T1/T2.** T1 is the bump against this specific
baseline and T2 the bump against a learned one; the whole point of that axis is
that the baselines differ in a controlled way. If `mu` changed after T1 and T2
were fitted, both would be void. The cost of the correction today is one
re-emission and two refits; after T2 it would be every fit in the phase.

## What is *not* concluded

No comparison between R0 and R1 is drawn from the refitted development metrics —
card 011's prohibition stands unchanged and for the same reason: those metrics
are contaminated by the folds that selected the hyperparameters. The benchmark's
answer is given once, on the untouched external holdout, at the holdout-opening
card. **This card does not open the holdout**; `cycle/holdout_ledger.jsonl` is
byte-identical (0 bytes) before and after. `base_p` is not described as skill
anywhere here.
