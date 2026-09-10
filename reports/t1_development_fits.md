# T1 bump against the fixed skill proxy -- development fits for R0 and R1 (card 015)

The benchmark's second target formulation. Where T0 predicts the game outcome directly, **T1 predicts the residual left after subtracting the fixed historical proxy**, then reconstructs a win probability from it:

```
B_i     = won_i - base_p_i      (the target actually fitted)
p_hat_i = base_p_i + B_hat_i    (the probability reconstructed from it)
```

The residual is fitted with the estimator's **regression** objective; T0 used the binary one. Same two representations phase 1 can supply -- **R0** (skill only) and **R1** (skill + card identity) -- through the same `deckbench.estimator.fit_and_predict`, the same grid, the same frozen folds and the same seed. This card constructs no learner, grid, or folds of its own, and never opens the holdout.

> **`base_p` is not skill.** R0's single feature is the reliability-shrunk historical win-rate proxy `base_p`, a nuisance representation reproduced from the inherited implementation (card 005). It is not a measurement of player skill and is not described as one here.

## Why T1, and what it does not decide

Section 2 of the benchmark observes that player skill may generate far more between-observation variation than deck quality, so direct prediction of the outcome can be dominated by skill even where deck quality matters. T1 subtracts the skill component up front so the model is asked only for what is left. Whether that actually helps recover deck signal is **H2** (section 14), which predicts an ordering across T0, T1 and T2. **H2 is a hypothesis, not an assumed result.** This card produces one row of the table that question needs; it does not test the ordering, and it draws no conclusion. The single holdout read at card 017 is where any comparison is made.

## R0's role under a residual target

It is fair to ask what a model can learn about `won - base_p` when its only feature is `base_p` itself -- the proxy has already been used to construct the target. Per benchmark section 4, this is a coherent question and not a degenerate one: `T1_R0` asks what **systematic structure the proxy leaves behind** -- miscalibration at the extremes, regression toward the mean, a reliability weighting that over- or under-shrinks particular buckets. A flat prediction near zero would itself be informative, saying the proxy has no exploitable residual structure. R0 is scored here for exactly that reason; nothing about it is read as skill, and its role in constructing the target is stated rather than hidden.

## Fit order and elapsed time

R0 was fitted **first and completely**, reconstructed, and its run record written to disk, **before any R1 assembly or fitting began** -- the same de-risking order T0 used, so the real path is proven where failure costs nothing.

- **R0 fit** (T1_R0): **52.5 s**, 194215 development rows x 1 feature.
- **R1 fit** (T1_R1): **406.0 s**, 194215 development rows x 194 features.

## Timing probe and the budget decision

Before the full R1 grid search, a probe fits a **single grid point on a single fold** at the capped iteration count (no early stopping), under the regression objective T1 uses.

- Probe (one grid point, one fold): **17.4 s**
- Single-booster fits in the full search: **21** (3 grid x 5 folds + 5 out-of-fold + 1 refit)
- Projected full-search total: **365.9 s** (6.1 min)
- Executor budget for R1: **5400 s** (90.0 min)

The projection was within budget, so the full R1 grid search was run. The probe is only a rough guide, not a precise predictor; the one decision it exists to make is whether the search fits inside the budget.

## Reconstruction and clipping (a measurement, not a nuisance)

`p_hat = base_p + B_hat` has no arithmetic guarantee of landing inside [0, 1]. The reconstruction is clipped into the unit interval using the panel's declared clip bound (`PROBABILITY_CLIP` = 1e-12) **only for scoring** -- the target itself is never clipped. How often the additive decomposition escapes the unit interval, and by how much, is direct evidence about whether the decomposition in section 2 holds on this data; a large clipped fraction would be a finding about the formulation, not a detail to suppress.

- **R0**: 358 of 194215 rows clipped (0.1843%) -- 358 below the lower bound, 0 above the upper. Raw reconstruction ranged [-0.020578, 0.984723] before clipping to [1e-12, 1 - 1e-12].
- **R1**: 307 of 194215 rows clipped (0.1581%) -- 307 below the lower bound, 0 above the upper. Raw reconstruction ranged [-0.191449, 0.974994] before clipping to [1e-12, 1 - 1e-12].

## Development metrics (diagnostic only -- no comparison concluded)

The card-010 panel is applied **twice** per model. The **continuous** view scores the bump prediction directly against the fitted residual `won - base_p`; the **Bernoulli** view scores the reconstructed, clipped probability against the raw `won` outcome, through the same panel T0 used. Both are out-of-fold development predictions.

### Reconstructed-probability view (`outcome_type = "bernoulli"`)

| Model | log_loss | brier | brier_skill_score | rmse | mae | auc | cal_intercept | cal_slope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 / R0 (skill only) | 0.666416 | 0.237153 | 0.037597 | 0.486984 | 0.474171 | 0.605422 | 0.002409 | 0.990592 |
| T1 / R1 (skill + identity) | 0.664523 | 0.236216 | 0.041401 | 0.486020 | 0.472797 | 0.613229 | 0.010340 | 1.005061 |

### Bump view (`outcome_type = "continuous"`)

| Model | rmse | mae | r2 |
| --- | --- | --- | --- |
| T1 / R0 (skill only) | 0.486984 | 0.474181 | 0.010845 |
| T1 / R1 (skill + identity) | 0.486028 | 0.472887 | 0.014725 |

**Only the reconstructed-probability metrics are comparable with T0.** T0 fits a probability and T1 fits a residual, so their native metrics answer different questions -- an R-squared on a bump and a log loss on a probability are not commensurable. The one thing both formulations produce for the same observation is a win probability, so the reconstructed probability is the only common ground, and it is what card 017 will compare. The continuous view is diagnostic for the T1 fit alone.

**These are development metrics, and they are diagnostic only.** They are computed on the same development rows whose folds selected each model's hyperparameters, so they are contaminated and cannot stand in for an honest generalization estimate. They confirm the pipeline produces sane numbers; they settle nothing.

**No comparison between R0 and R1, and none between T0 and T1, is concluded from these numbers, in any direction.** Card 011's prohibition stands unchanged and for the same reason: whether a representation or a target formulation adds information is not a question development metrics can answer. The benchmark's design puts that answer on the untouched external holdout, opened exactly once at card 017, scored through this same panel with the paired cluster bootstrap carrying the uncertainty on the difference. Section 13 forbids reading any null incremental result as an absence of a deck effect. So: look, record, and draw nothing.

## Provenance

- Split SHA256 (verified before each fit): `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`
- Seed: **20260908**; xgboost **3.1.2**, single-threaded (byte-identical determinism).
- Objective: **regression** (regression), for the continuous residual target -- distinct from T0's binary objective.
- R0 chosen hyperparameters: `{'max_depth': 4, 'eta': 0.1, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 1.0}`, 135 boosting rounds.
- R1 chosen hyperparameters: `{'max_depth': 5, 'eta': 0.05, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 2.0}`, 269 boosting rounds.
- Run records are tracked in git (`data/runs/*_run.json`); the prediction parquets, reconstruction parquets and fitted boosters are gitignored and regenerable from the frozen split and the representation tables.
- The holdout partition was not read; `cycle/holdout_ledger.jsonl` is byte-identical (0 bytes) before and after this card.
