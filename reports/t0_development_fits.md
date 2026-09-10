# T0 raw outcome -- development fits for R0 and R1 (card 011)

The first row of the benchmark matrix, and the first real fits in the project. Target formulation **T0** (the raw game outcome `won` in {0, 1}) against the two representations phase 1 can supply: **R0** (skill only) and **R1** (skill + card identity). Both are fitted through `deckbench.estimator.fit_and_predict`; this card constructs no learner, grid, or folds of its own, and never opens the holdout.

> **`base_p` is not skill.** R0's single feature is the reliability-shrunk historical win-rate proxy `base_p`, a nuisance representation reproduced from the inherited implementation (card 005). It is not a measurement of player skill and is not described as one here.

## Regeneration history

These fits have been regenerated twice since card 011 first produced them. Neither regeneration changed the learner, the grid, the folds, the seed, or the population, and neither opened the holdout. Both are recorded here because the numbers below moved each time, and a metric that moves without a stated reason is not attributable.

1. **Card 014 -- skill-proxy fidelity correction.** The proxy's shrinkage target `mu` changed from a per-game mean to a per-draft mean, to match the R implementation being reproduced (`scripts/R/04_real_inference_refactored.R` line 324; `mu` 0.546211 -> 0.533339). R0 is `[base_p]` and R1 contains it, so both consumed the changed column and were refitted. See `reports/mu_fidelity_correction.md`.

2. **xgboost provenance correction.** Cards 011 and 014 recorded `xgboost_version` from the Python package's `__version__`, which read `3.4.1` while the compiled library that actually trained the boosters was `3.1.2` -- a false provenance string that survived two reviewer passes. The run record now takes the version from the library's own `XGBoostVersion()` and records the Python wrapper's version separately. Refitting under a matched 3.1.2 wrapper did **not** reproduce the earlier T0 boosters: R0 selected a different grid point (`max_depth` 3 -> 4, `subsample` and `colsample_bytree` 1.0 -> 0.8) and 367 -> 136 rounds, and the panel metrics moved in the fifth decimal. The T1 fits of card 015, which were produced under a matched wrapper, reproduced byte-identically in the same exercise. The artifacts described below are the reproducible ones; the card-011 and card-014 T0 artifacts were not reproducible in this environment and have been replaced.

## Fit order and elapsed time

R0 was fitted **first and completely**, and its run record written to disk, **before any R1 assembly or fitting began**. R0 is one feature and finishes in seconds; fitting it first proves the real path -- split-hash verification, fold alignment, out-of-fold prediction, run record -- at a point where failure costs nothing. R0 is also M0, the benchmark's own skill-only baseline, so it is not a throwaway warm-up.

- **R0 fit** (T0_R0): **79.9 s**, 194215 development rows x 1 feature.
- **R1 fit** (T0_R1): **387.2 s**, 194215 development rows x 194 features.

## Timing probe and the budget decision

Before the full R1 grid search, a probe fits a **single grid point on a single fold** at the capped iteration count (no early stopping). The full search performs `len(grid) * k` cross-validation fits, `k` out-of-fold fits, and one final refit.

- Probe (one grid point, one fold): **14.5 s**
- Single-booster fits in the full search: **21** (3 grid x 5 folds + 5 out-of-fold + 1 refit)
- Projected full-search total: **304.6 s** (5.1 min)
- Executor budget for R1: **5400 s** (90.0 min)

The projection was within budget, so the full R1 grid search was run. The measured R1 fit came in at 387.2 s, over the 304.6 s projection. The probe is only a rough guide, not a precise predictor: it times one grid point on one fold at the capped iteration count with no early stopping, whereas the real search runs all grid points (each early-stopped on the native metric, some to more rounds or a deeper tree than the probe's) plus a final refit on all development rows. The two need not agree closely; both are far inside the budget, which is the only decision the probe exists to make.

## Development metrics (diagnostic only -- no comparison concluded)

The card-010 panel applied to each model's **out-of-fold development** predictions, with `outcome_type = "bernoulli"`.

| Model | log_loss | brier | brier_skill_score | rmse | mae | auc | cal_intercept | cal_slope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T0 / R0 (skill only) | 0.666441 | 0.237157 | 0.037582 | 0.486987 | 0.474243 | 0.605327 | 0.001443 | 0.994568 |
| T0 / R1 (skill + identity) | 0.664381 | 0.236137 | 0.041720 | 0.485939 | 0.472685 | 0.613597 | 0.008871 | 1.009140 |

**These are development metrics, and they are diagnostic only.** They are computed on the same development rows whose folds selected each model's hyperparameters, so they are contaminated and cannot stand in for an honest generalization estimate. They are reported here only so that a first look confirms the pipeline produces sane probabilities in the unit interval rather than, say, 0.5 everywhere.

**No comparison between R0 and R1 is concluded from these numbers, in either direction.** Whether card identity adds information beyond the skill proxy is not a question development metrics can answer; the benchmark's design puts that answer on the untouched external holdout, opened exactly once at card 014, scored through this same panel with the paired cluster bootstrap carrying the uncertainty on the difference. Section 13 also forbids reading any null incremental result as an absence of a deck effect. So: look, record, and draw nothing.

## Provenance

- Split SHA256 (verified before each fit): `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`
- Seed: **20260908**; xgboost **3.1.2** (compiled library; Python package **3.1.2**), single-threaded (byte-identical determinism).
- R0 chosen hyperparameters: `{'max_depth': 4, 'eta': 0.1, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 1.0}`, 136 boosting rounds.
- R1 chosen hyperparameters: `{'max_depth': 5, 'eta': 0.05, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 2.0}`, 268 boosting rounds.
- Run records are tracked in git (`data/runs/*_run.json`); the prediction parquets and fitted boosters are gitignored and regenerable from the frozen split and the representation tables.
- The holdout partition was not read; `cycle/holdout_ledger.jsonl` is byte-identical (0 bytes) before and after this card.
