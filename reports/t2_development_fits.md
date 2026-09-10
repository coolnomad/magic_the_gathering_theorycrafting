# T2 bump against a cross-fitted learned baseline -- development fits for R0 and R1 (card 016)

The benchmark's third and last target formulation. T1 subtracted a **fixed** historical proxy; **T2 subtracts a learned one, cross-fitted so that no observation ever helps train the model that produces its own baseline**, then reconstructs a win probability from the residual:

```
m_hat_-i(S_i)              the cross-fitted baseline, E[Y|S] out of fold
B_i     = won_i - m_hat_-i(S_i)   (the target actually fitted)
p_hat_i = m_hat_-i(S_i) + B_hat_i (the probability reconstructed from it)
```

The residual is fitted with the estimator's **regression** objective. Same two representations phase 1 can supply -- **R0** (skill only) and **R1** (skill + card identity) -- through the same `deckbench.estimator.fit_and_predict`, the same grid, the same frozen folds and the same seed. This card constructs no learner, grid, or folds of its own, and never opens the holdout.

> **Neither `base_p` nor `m_hat` is skill.** R0's single feature is the reliability-shrunk historical win-rate proxy `base_p`, a nuisance representation (card 005). `m_hat` is a *learned* estimate of expected win probability given that representation. Both are baselines; neither is a measurement of a player, and neither is described as skill here.

## The baseline is reused from T0_R0, not refitted

`m(S) = E[Y|S]` fitted on R0 with the binary objective and predicted out of fold is exactly what card 011 produced as `T0_R0`. This card **reuses that artifact and refits nothing**: refitting an identical model would burn time to reproduce the same numbers and would let T2's baseline drift from the `T0_R0` card 017 also scores, which is the one thing that would make the T0/T2 contrast unreadable. Before the predictions were used, the `T0_R0` run record was validated -- target, representation, objective, feature count, seed and split hash all had to match -- so the residual is never formed against the wrong baseline.

Baseline artifact consumed, so the residual is reproducible from the record alone:

- Out-of-fold `m_hat_-i` predictions: `data/runs/T0_R0_predictions.parquet`
- `T0_R0` chosen hyperparameters: `{'colsample_bytree': 0.8, 'eta': 0.1, 'max_depth': 4, 'min_child_weight': 1.0, 'subsample': 0.8}`, 136 boosting rounds, objective **binary**, seed **20260908**.
- Full-data `m_hat` booster (**not** used here; card 017's): `data/runs/T0_R0.xgb`.

## Two baselines, two places -- and why development uses the out-of-fold one

The **development** reconstruction here adds the **out-of-fold** `m_hat_-i`, the same vector that formed the training residual. Using the full-data refit `m_hat(S)` to reconstruct development rows would add a baseline fitted **on those same rows**, injecting a leak that flatters T2 against T0 and T1 for no reason other than leakage and makes T2's development numbers incomparable with theirs. The full-data `m_hat(S)` (`T0_R0.xgb`) is **card 017's**, where it reconstructs holdout rows it never trained on and is honest by construction. The two must not be swapped, and they are not.

## R0 is a cross-fitting diagnostic, not a result

Under T2 the R0 features are the same `S` the baseline was fitted on, so `E[B|S] = E[Y|S] - m_hat(S)` is approximately zero by construction and `T2_R0` should predict close to nothing. That makes it the most informative check in the card, not a model: if its predictions carry substantial systematic structure, the cross-fitting leaked or the baseline underfit. R0 contains no deck information at all, so a small non-zero value is **not** deck signal -- it is read only as a check on the machinery.

- **R0** (T2_R0): out-of-fold `B_hat` mean **+0.000018**, std **0.000682**, range [-0.006288, +0.008895].
- **R1** (T2_R1): out-of-fold `B_hat` mean **-0.001203**, std **0.031270**, range [-0.197308, +0.158243].

A mean near zero with a small spread is the expected, healthy reading: the out-of-fold baseline left no exploitable systematic structure in `S`. A large systematic departure from zero would indicate leakage or baseline misfit and would be a finding about the machinery, not recovered signal.

## A bounded, recorded leak: hyperparameter selection is not fold-honest

The out-of-fold **training** is honest: each fold's baseline comes from a booster trained on the other four folds. But the grid point `chosen` was selected by cross-validation over **all** development folds, so fold k's baseline is produced by a booster trained without fold k under hyperparameters informed by it. Section T2's critical requirement governs *training*, which is fold-honest; this residual leak is a choice among the grid's three points, is bounded, and is **recorded here rather than hidden**. Strict nested cross-validation would remove it at a cost this first benchmark does not need to pay; the decision to accept and document it is deliberate.

## Fit order and elapsed time

R0 was fitted **first and completely**, reconstructed, and its run record written to disk, **before any R1 assembly or fitting began** -- the same de-risking order T0 and T1 used, so the real path is proven where failure costs nothing.

- **R0 fit** (T2_R0): **7.6 s**, 194215 development rows x 1 feature.
- **R1 fit** (T2_R1): **233.5 s**, 194215 development rows x 194 features.

## Timing probe and the budget decision

Before the full R1 grid search, a probe fits a **single grid point on a single fold** at the capped iteration count (no early stopping), under the regression objective T2 uses.

- Probe (one grid point, one fold): **13.9 s**
- Single-booster fits in the full search: **21** (3 grid x 5 folds + 5 out-of-fold + 1 refit)
- Projected full-search total: **291.0 s** (4.9 min)
- Executor budget for R1: **5400 s** (90.0 min)

The projection was within budget, so the full R1 grid search was run. The probe is only a rough guide, not a precise predictor; the one decision it exists to make is whether the search fits inside the budget.

## Reconstruction and clipping (a measurement, not a nuisance)

`p_hat = m_hat_-i + B_hat` has no arithmetic guarantee of landing inside [0, 1]. The reconstruction is clipped into the unit interval using the panel's declared clip bound (`PROBABILITY_CLIP` = 1e-12) **only for scoring** -- the target itself is never clipped. How often the additive decomposition escapes the unit interval, and by how much, is direct evidence about whether the decomposition in section 2 holds on this data; a large clipped fraction would be a finding about the formulation, not a detail to suppress.

- **R0**: 0 of 194215 rows clipped (0.0000%) -- 0 below the lower bound, 0 above the upper. Raw reconstruction ranged [0.001964, 0.973934] before clipping to [1e-12, 1 - 1e-12].
- **R1**: 241 of 194215 rows clipped (0.1241%) -- 234 below the lower bound, 7 above the upper. Raw reconstruction ranged [-0.133856, 1.068684] before clipping to [1e-12, 1 - 1e-12].

## Development metrics (diagnostic only -- no comparison concluded)

The card-010 panel is applied **twice** per model. The **continuous** view scores the bump prediction directly against the fitted residual `won - m_hat_-i`; the **Bernoulli** view scores the reconstructed, clipped probability against the raw `won` outcome, through the same panel T0 and T1 used. Both are out-of-fold development predictions.

### Reconstructed-probability view (`outcome_type = "bernoulli"`)

| Model | log_loss | brier | brier_skill_score | rmse | mae | auc | cal_intercept | cal_slope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T2 / R0 (skill only) | 0.666463 | 0.237165 | 0.037547 | 0.486996 | 0.474243 | 0.605329 | 0.001631 | 0.993468 |
| T2 / R1 (skill + identity) | 0.664317 | 0.236018 | 0.042204 | 0.485816 | 0.471922 | 0.613462 | 0.010093 | 0.978445 |

### Bump view (`outcome_type = "continuous"`)

| Model | rmse | mae | r2 |
| --- | --- | --- | --- |
| T2 / R0 (skill only) | 0.486996 | 0.474243 | -0.000037 |
| T2 / R1 (skill + identity) | 0.485820 | 0.471966 | 0.004789 |

**Only the reconstructed-probability metrics are comparable across T0, T1 and T2.** Each target fits a different quantity -- a probability (T0), a residual against a fixed proxy (T1), a residual against a learned baseline (T2) -- so their native metrics answer different questions and an R-squared on a bump is not commensurable with a log loss on a probability. The one thing all three formulations produce for the same observation is a win probability, so the reconstructed probability is the only common ground, and it is what card 017 will compare. The continuous view is diagnostic for the T2 fit alone.

**These are development metrics, and they are diagnostic only.** They are computed on the same development rows whose folds selected each model's hyperparameters, so they are contaminated and cannot stand in for an honest generalization estimate. They confirm the pipeline produces sane numbers; they settle nothing.

**No comparison between R0 and R1, and none among T0, T1 and T2, is concluded from these numbers, in any direction.** H2 (section 14) predicts an ordering T2 > T1 > T0 in recovered deck signal; **producing T2's row is not testing that ordering, and this card does not test it.** Whether a representation or a target formulation adds information is not a question development metrics can answer. The benchmark's design puts that answer on the untouched external holdout, opened exactly once at card 017, scored through this same panel with the paired cluster bootstrap carrying the uncertainty on the difference. Section 13 forbids reading any null incremental result as an absence of a deck effect. So: look, record, and draw nothing.

## Provenance

- Split SHA256 (verified before each fit): `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`
- Seed: **20260908**; xgboost **3.1.2** (compiled library; Python package **3.1.2**), single-threaded (byte-identical determinism).
- Objective: **regression** (regression), for the continuous residual target -- distinct from T0's binary objective.
- R0 chosen hyperparameters: `{'max_depth': 5, 'eta': 0.05, 'subsample': 0.8, 'colsample_bytree': 0.8, 'min_child_weight': 2.0}`, 1 boosting rounds.
- R1 chosen hyperparameters: `{'max_depth': 3, 'eta': 0.1, 'subsample': 1.0, 'colsample_bytree': 1.0, 'min_child_weight': 1.0}`, 211 boosting rounds.
- Run records are tracked in git (`data/runs/*_run.json`); the prediction parquets, reconstruction parquets and fitted boosters are gitignored and regenerable from the frozen split, the representation tables and the reused `T0_R0` baseline.
- The holdout partition was not read; `cycle/holdout_ledger.jsonl` is byte-identical (0 bytes) before and after this card.
