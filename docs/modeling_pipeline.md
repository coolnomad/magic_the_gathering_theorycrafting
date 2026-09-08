# MTG Premier Draft Win-Rate Modeling Pipeline

The statistical arm of this repository: predict per-game win probability in HOB
Premier Draft from a skill proxy plus deck representation, so that increasingly
rich representations can be compared under a fixed outcome, split and metric set.

> **Status (2026-09-07): this pipeline is being rebuilt.** See
> [`Model_Building.md`](./Model_Building.md). The artifacts described below were
> produced before that spec was written and carry a known defect — the files named
> `identity_matrix_*` are a 43,160 x 6 **rank-bucket** indicator matrix, not a deck
> identity representation. The true representation is one row per draft, one column
> per card, value = card count in deck / deck size, recoverable from the `deck_*`
> columns of the raw CSV. Numbers in the Results section below should not be cited
> until the rebuild lands.

## Data

Input is the 17Lands public game-level dataset, one row per game:
`data/raw/game_data_public.HOB.PremierDraft.csv.gz` — 241,727 rows across 43,161
drafts, 1,165 columns, `draft_time` spanning 2026-08-11 to 2026-08-29.

The file is **not tracked in git** (16 MB, binary, publicly re-downloadable). Its
URL, SHA256 and shape are recorded in [`data/raw/source_manifest.json`](../data/raw/source_manifest.json);
fetch it and verify the hash before running the pipeline.

Derived artifacts under `data/processed/` are likewise untracked and regenerable;
`data/processed/MANIFEST.sha256` is tracked so a rebuild can be checked
byte-for-byte, the same role `frozen_manifest.json` plays for `data/graph_global`.

## Pipeline

| Steps | Script | Output |
|---|---|---|
| 1–3 | `scripts/build_model_table.py` † | `draft_model_table.parquet`, `deck_identity.parquet` |
| 4–5 | `scripts/00_outcome_and_split.py` | `split_indices.csv`, `outcome_definition.txt` |
| 6–7 | `scripts/01_fit_m0_m1.py` | `results/m0_skill_only.xgb`, `results/m1_skill_identity.xgb` |
| 8 | `scripts/02_comprehensive_metrics.py` | `results/bootstrap_ci.txt`, `calibration_analysis.txt`, `r2_analysis.txt`, `metrics_m0_m1.csv` |
| 9 | `scripts/03_model_comparison_and_plots.py` | `results/model_comparison.csv`, `figures/*.png` |

† **Two variants of this script exist and need reconciling.**
`scripts/build_model_table.py` is the newer one (adds NaN defaults for missing
`user_game_win_rate_bucket` / `user_n_games_bucket`); `src/data/build_model_table.py`
is the earlier one, but sits at the path [`Model_Building.md`](./Model_Building.md)
specifies in its Deliverables. Both are committed to preserve the state; pick one
during the rebuild rather than letting them drift.

```bash
python scripts/build_model_table.py
python scripts/00_outcome_and_split.py
python scripts/01_fit_m0_m1.py
python scripts/02_comprehensive_metrics.py
python scripts/03_model_comparison_and_plots.py
```

An R implementation of the earlier causal analysis lives in `scripts/R/`
(`01_simulate_arena.R` → `04_real_inference_refactored.R`).

## Method

**Outcome.** Grouped binomial: `wins_i ~ Binomial(games_i, p_i)` per draft,
implemented as weighted logistic (`label = wins/games`, `weight = games`) rather
than expanding to per-game rows.

**Skill proxy (`base_p`).** Reliability-adjusted historical win rate, shrunk in
logit space toward the population mean:

```
logit(base_p) = (hist_w * logit(base_p_raw) + lambda * logit(mu)) / (hist_w + lambda)
```

with `lambda = 5` and `hist_w` set by the games-played bucket. This is an interim
nuisance representation — it is *not* a measurement of true skill.

**Split.** Timestamp-based, ~75% development / ~25% holdout. The dataset carries no
persistent player identifier — `rank` is a six-level skill bucket, not a player ID —
so player-grouped splitting is unavailable and leakage control is correspondingly
weaker. This is a design limitation, not a choice.

**Models.** XGBoost, `binary:logistic`, sample-weighted.
M0 = `base_p` alone. M1 = `base_p` + normalized card fractions.
Planned: M2 = skill + KG representation, M3 = skill + identity + KG,
M4 = + game-script representation.

## Results (provisional — see Status)

Two runs currently disagree and neither is anchored to a pre-registered decision
rule, which is why the rebuild spec exists:

| Source | M0 R² | M1 R² | M1 − M0 |
|---|---|---|---|
| `results/model_comparison_report.txt` | −0.0001 | 0.0471 | +0.0472 |
| earlier README revision | 0.1594 | 0.1785 | +0.0191, 95% CI [−0.0062, +0.0436] |

Where a confidence interval was computed it **crosses zero**. The defensible
summary today is that deck composition has not been shown to add predictive value
over the skill proxy — not that it adds a little.

## Interpretive caution

The 7-wins / 3-losses stopping rule concentrates the outcome distribution and puts
an irreducible binomial-sampling floor under the residual variance. A low R² here
is therefore not directly comparable to R² from an unbounded-length outcome, and
the ceiling is unknown without the latent `p_i` distribution. Do not describe any
observed R² as approaching a theoretical maximum.
