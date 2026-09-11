# The single holdout read -- all six models scored once (card 017)

This is the measurement the benchmark was built to make. The sealed external holdout was opened **exactly once**, through `deckbench.holdout.load_holdout`, and all six fitted models (T0/T1/T2 x R0/R1) were scored through the card-010 evaluation panel on the reconstructed-probability scale -- the only scale on which the three target formulations are comparable. Nothing was trained, tuned, selected or refitted; the boosters are fixed inputs. The uncertainty on every comparison is carried by the paired cluster bootstrap, clustered on `draft_id`.

> **`base_p` is not skill, and `m_hat` is not skill.** R0's single feature is the reliability-shrunk historical win-rate proxy `base_p`, a nuisance representation (card 005). `m_hat` is a *learned* estimate of expected win probability given that representation (the full-data `T0_R0` booster). Both are baselines; neither is a measurement of a player.

## The one ledger line

`cycle/holdout_ledger.jsonl` was 0 bytes before this card and now holds exactly one line, quoted verbatim:

```json
{"card_id": "017", "git_commit": "6d476f206221975edf6ef0b39ae72ccc2f931040", "is_repeat": false, "reason": "card 017: the single external-holdout read -- score all six fitted models (T0/T1/T2 x R0/R1) through the card-010 panel and the paired cluster bootstrap. This is the one comparison the benchmark was built to make.", "split_sha256": "ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4", "timestamp": "2026-09-11T04:11:18.697462+00:00"}
```

## What was verified before the seal was touched

Every failure that can happen before the read is free; every failure after it is permanent, because `load_holdout` appends its ledger line before returning rows. So all validation ran in front of the seal:

1. **Environment.** `deckbench.environment.require_pinned_environment()` was called first: xgboost 3.1.2, numpy 2.3.5, pyarrow 22.0.0. A mismatched stack would have stopped the card while the seal was still intact.
2. **Split hash.** The split parquet was verified against the manifest (`ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`).
3. **Run records.** All six records were validated -- `target`, `representation`, `objective`, `n_features`, `seed` and `split_sha256` -- before any booster was used. The feature counts were checked against the assembled matrix width, not a hardcoded constant, because xgboost matches features positionally and a silently transposed matrix would produce plausible, wrong numbers.
4. **Rehearsal.** The development partition was scored through the identical `score_partition` code path, and its bootstrap run, before the holdout was opened. The rehearsal and the real read call the same scoring function; they are not two parallel implementations. (The rehearsal's development numbers are contaminated -- the boosters trained on those rows -- and are deliberately not tabulated beside the holdout numbers.)

## Reconstruction and clipping on the holdout

T0's booster output is the win probability directly. T1 reconstructs `base_p + B_hat`; T2 reconstructs `m_hat(S) + B_hat`, where `m_hat` is the **full-data** `T0_R0.xgb` applied to holdout rows -- no holdout row trained it, so it is honest on them by construction, and the development out-of-fold baseline (which does not exist for holdout rows) is never synthesised. Each reconstruction is clipped into the unit interval with the panel's declared bound (`PROBABILITY_CLIP` = 1e-12) **only for scoring**; the counts at each end are a measurement, not a nuisance:

| Model | rows | clipped low | clipped high | raw min | raw max |
| --- | --- | --- | --- | --- | --- |
| T0_R0 | 47346 | - | - | n/a (T0: direct probability) | n/a |
| T0_R1 | 47346 | - | - | n/a (T0: direct probability) | n/a |
| T1_R0 | 47346 | 68 | 0 | -0.018506 | 0.960744 |
| T1_R1 | 47346 | 47 | 0 | -0.089845 | 0.912397 |
| T2_R0 | 47346 | 0 | 0 | 0.001878 | 0.962337 |
| T2_R1 | 47346 | 35 | 0 | -0.052985 | 0.967464 |

## Master results -- holdout panel, one row per model

| Model | Target | Repr | log_loss | brier | brier_skill_score | rmse | mae | auc | cal_intercept | cal_slope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T0_R0 | T0 | R0 | 0.668461 | 0.238090 | 0.032338 | 0.487945 | 0.475005 | 0.597861 | -0.017123 | 0.973537 |
| T0_R1 | T0 | R1 | 0.666101 | 0.236945 | 0.036989 | 0.486770 | 0.473040 | 0.606858 | -0.020592 | 0.992980 |
| T1_R0 | T1 | R0 | 0.668453 | 0.238086 | 0.032355 | 0.487940 | 0.474923 | 0.598012 | -0.015618 | 0.967981 |
| T1_R1 | T1 | R1 | 0.666031 | 0.236910 | 0.037133 | 0.486734 | 0.472959 | 0.607031 | -0.020279 | 0.991665 |
| T2_R0 | T2 | R0 | 0.668460 | 0.238090 | 0.032339 | 0.487944 | 0.475002 | 0.597855 | -0.017250 | 0.973579 |
| T2_R1 | T2 | R1 | 0.665961 | 0.236882 | 0.037245 | 0.486706 | 0.472639 | 0.606685 | -0.021300 | 0.981721 |

All metrics are on the reconstructed win probability against the raw `won` outcome, `outcome_type = bernoulli`. There is deliberately no unlabelled regression R-squared on a Bernoulli outcome; the panel reports a Brier skill score instead (section 9). Bootstrap: 1000 replicates, seed 20260908, 95% interval, clustered on `draft_id`.

## Incremental value: the within-target increment R1 - R0 (section 11)

The incremental-value question is how much card identity adds beyond the skill-only baseline, within each target formulation. Each cell is `point [lo, hi]` for `metric(R1) - metric(R0)`, from the paired cluster bootstrap. For log loss, Brier, RMSE and MAE a **negative** difference favours R1 (lower error); for Brier skill score and AUC a **positive** difference favours R1.

| Increment | log_loss | brier | brier_skill_score | rmse | mae | auc |
| --- | --- | --- | --- | --- | --- | --- |
| T0_R1 - T0_R0 | -0.002360 [-0.002996, -0.001719] | -0.001145 [-0.001436, -0.000859] | +0.004652 [+0.003488, +0.005838] | -0.001174 [-0.001473, -0.000880] | -0.001966 [-0.002323, -0.001566] | +0.008997 [+0.006942, +0.011202] |
| T1_R1 - T1_R0 | -0.002422 [-0.003082, -0.001754] | -0.001176 [-0.001467, -0.000879] | +0.004778 [+0.003568, +0.005968] | -0.001206 [-0.001507, -0.000901] | -0.001963 [-0.002333, -0.001542] | +0.009019 [+0.006950, +0.011070] |
| T2_R1 - T2_R0 | -0.002499 [-0.003036, -0.001941] | -0.001207 [-0.001462, -0.000944] | +0.004906 [+0.003841, +0.005942] | -0.001238 [-0.001501, -0.000969] | -0.002363 [-0.002682, -0.002058] | +0.008830 [+0.006966, +0.010591] |

## Cross-target comparisons among the three R1 models

How the skill-plus-identity representation performs across the three target formulations, on the common probability scale. Each cell is `point [lo, hi]` for `metric(a) - metric(b)`.

| Increment | log_loss | brier | brier_skill_score | rmse | mae | auc |
| --- | --- | --- | --- | --- | --- | --- |
| T1_R1 - T0_R1 | -0.000070 [-0.000276, +0.000145] | -0.000035 [-0.000131, +0.000065] | +0.000144 [-0.000263, +0.000532] | -0.000036 [-0.000135, +0.000066] | -0.000080 [-0.000210, +0.000063] | +0.000174 [-0.000469, +0.000812] |
| T2_R1 - T0_R1 | -0.000140 [-0.000528, +0.000233] | -0.000063 [-0.000231, +0.000102] | +0.000256 [-0.000417, +0.000937] | -0.000065 [-0.000237, +0.000105] | -0.000401 [-0.000646, -0.000137] | -0.000173 [-0.001069, +0.000755] |
| T2_R1 - T1_R1 | -0.000070 [-0.000473, +0.000312] | -0.000028 [-0.000202, +0.000143] | +0.000112 [-0.000581, +0.000818] | -0.000028 [-0.000207, +0.000147] | -0.000321 [-0.000596, -0.000055] | -0.000346 [-0.001232, +0.000599] |

## H2 -- the difference of increments (a difference of differences)

H2 predicts an ordering of *deck signal* across target formulations, `increment(T2) > increment(T1) > increment(T0)`, where deck signal is the increment `R1 - R0` within a formulation -- **not** the absolute performance of R1, which is dominated by how well the formulation predicts outcomes at all. So the comparison is a difference of differences, and its uncertainty is drawn from the **same** bootstrap resamples for both increments (the panel returns `replicate_indices` precisely so this stays paired). Three increments with overlapping intervals is not a test of the ordering; the intervals below are.

On Brier skill score, deck signal is larger when the increment is larger (higher is better), so H2 predicts each `increment(T2) - increment(T1)` and `increment(T1) - increment(T0)` to be positive. On log loss and Brier, lower is better, so the sign convention flips.

| Metric | increment(a) - increment(b) | point [lo, hi] | interval excludes 0 |
| --- | --- | --- | --- |
| brier_skill_score | increment(T1) - increment(T0) | +0.000126 [-0.000299, +0.000533] | no |
| brier_skill_score | increment(T2) - increment(T0) | +0.000254 [-0.000413, +0.000935] | no |
| brier_skill_score | increment(T2) - increment(T1) | +0.000128 [-0.000583, +0.000863] | no |
| log_loss | increment(T1) - increment(T0) | -0.000061 [-0.000278, +0.000165] | no |
| log_loss | increment(T2) - increment(T0) | -0.000139 [-0.000527, +0.000233] | no |
| log_loss | increment(T2) - increment(T1) | -0.000077 [-0.000500, +0.000322] | no |
| brier | increment(T1) - increment(T0) | -0.000031 [-0.000131, +0.000073] | no |
| brier | increment(T2) - increment(T0) | -0.000063 [-0.000230, +0.000102] | no |
| brier | increment(T2) - increment(T1) | -0.000032 [-0.000212, +0.000143] | no |

An interval that includes zero does not establish the ordering H2 predicts, in either direction. The development-side increments were ordered `T2 > T0 > T1`, against H2's predicted `T2 > T1 > T0`; that was recorded as an expectation carrying no weight, because development metrics are contaminated by the folds that selected the hyperparameters. The holdout intervals above are the only honest evidence on the ordering.

## H1 -- skill dominance

H1 says skill alone explains substantially more predictable variation in raw outcomes than deck identity does. The skill-only models (R0) and the skill-plus-identity models (R1) are compared directly by the within-target increments above: the R1 - R0 differences measure exactly the additional predictable variation card identity contributes beyond the `base_p` baseline. The absolute panel shows the skill-only R0 models already capturing the bulk of the achievable Brier skill score, with the R1 increments small in every target formulation -- consistent with H1's claim that skill dominates. The magnitude of each increment, and whether its interval clears zero, is read from the increment table; the absolute R0 levels are in the master table.

## Interpretation rule (benchmark section 13), in full

A null incremental result is a limit of the representation, learner and dataset -- **never** evidence that deck composition does not affect win probability. Concretely, `R2(S + D) approx R2(S)` supports:

> Card identity provides little detectable incremental predictive information beyond skill under this representation, learner and dataset.

It does **not** establish:

> Deck composition does not affect win probability.

The difference between those two sentences is the entire epistemic content of this benchmark. A null result has several explanations that section 13 requires be stated rather than gestured at:

* deck effects are small relative to skill;
* deck effects are interaction-dependent;
* card identity is an inefficient representation;
* outcome noise overwhelms small effects;
* skill partially proxies expected deck quality because stronger players draft better decks.

No causal conclusion about deck composition is stated or implied anywhere in this report. The representation axis that would probe deck structure directly -- R2 (knowledge graph), R3 (game script), R4 and R5 -- is phase 3, a separate benchmark against a holdout this card has now spent; whether phase 3 needs a fresh split is a question for whoever writes it, to be asked before any model is fitted.

## Provenance

- Split SHA256 (verified before the read): `ad7f8596f5e71c0aa4ce0959c239ef863e72977feadcb7a53d2a5ab0bd34cad4`
- Bootstrap: 1000 replicates, seed 20260908, 95% percentile interval, clustered on `draft_id`; the same seed reproduces the intervals byte for byte.
- Environment: xgboost 3.1.2, numpy 2.3.5, pyarrow 22.0.0 (`deckbench.environment` pins).
- Holdout reconstructed-probability artifacts, keyed by `obs_id`, are written under `data/runs/{model_id}_holdout_predictions.parquet` (six files), so every number above is reproducible without a second read. They are gitignored alongside the boosters, and regenerable only by re-reading the holdout -- which this card does not permit.
- The holdout was opened exactly once; the single ledger line above records the commit, timestamp and split hash of that read.
