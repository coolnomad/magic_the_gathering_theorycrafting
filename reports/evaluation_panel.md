# The evaluation panel — fixed before any model is scored (card 010)

This report states, in advance of a single model being fitted against it, every
choice the benchmark's evaluation panel makes: each metric's definition, the
weighting convention, the probability clip, the binning strategy, the smooth
calibration method, and the paired cluster bootstrap's seed and cluster level. It
is a pre-registration device. Once results exist, each of these choices becomes a
degree of freedom that can be steered toward a conclusion; fixing them here
removes that freedom. The panel is `src/deckbench/evaluation.py`; the tests that
pin its arithmetic are `tests/test_deckbench_evaluation.py`.

The concrete failure this prevents is in this repository's own history. The
quarantined pipeline (`attic/haiku-2026-09-07/`) produced a `KEY FINDINGS` block
asserting three checkmarked improvements next to a companion analysis whose
confidence interval crossed zero — two artifacts, one comparison, no way to
adjudicate. The panel exists so the adjudication is fixed in advance.

The panel governs `docs/MTG_Deck-Strength_Modeling_Benchmark.md` §§9–12.

---

## 0. What the panel is, and is not

The panel is a **pure function of arrays** `(y, p, weight, group)`. It:

- loads no parquet, reads no split, and never touches the holdout partition or
  its ledger;
- accepts **no partition label** — it scores exactly the rows it is handed and
  the caller is accountable for which rows those are;
- does not know which model produced the predictions, nor what representation was
  used;
- **fits nothing** and imports no learner — not `xgboost`, not `sklearn.ensemble`,
  nothing from `deckbench.estimator`. The single place a model is fit at all is
  the calibration intercept/slope, a two-parameter weighted logistic regression
  solved by hand with numpy alone (`_weighted_logistic_newton`).

Every metric weights by the observation weight passed in. An unweighted metric
silently answers a different question, so weighting is universal, not optional.

---

## 1. The scalar metrics

All are weighted by the passed observation weight `w`; write `W = Σ wᵢ`.

| Metric | Definition | Reported for |
| --- | --- | --- |
| **Log loss** | `−(1/W) Σ wᵢ [ yᵢ log p̃ᵢ + (1−yᵢ) log(1−p̃ᵢ) ]` | Bernoulli |
| **Brier score** | `(1/W) Σ wᵢ (pᵢ − yᵢ)²` | Bernoulli |
| **RMSE** | `√[ (1/W) Σ wᵢ (yᵢ − ŷᵢ)² ]` | both |
| **MAE** | `(1/W) Σ wᵢ \|yᵢ − ŷᵢ\|` | both |
| **AUC** | weighted Mann–Whitney statistic, ties at half credit | Bernoulli |
| **Weighted R²** | `1 − Σ wᵢ(yᵢ − ŷᵢ)² / Σ wᵢ(yᵢ − ȳ_w)²`, `ȳ_w` the weighted mean | **continuous only** |
| **Brier Skill Score** | `1 − BS / BS_ref`, `BS_ref` = Brier of the weighted base rate | **Bernoulli only** |

`p̃` denotes the clipped probability (§2). `ȳ_w` is the weighted mean of the
outcome.

Every metric is verified against a **hand-computed** value on a small fixture in
the tests, so each is checked against arithmetic rather than against its own
output. The degenerate cases are asserted directly: perfect predictions score log
loss 0 (to within the clip), Brier 0, and AUC 1; predicting the weighted base
rate everywhere scores weighted R² 0 and Brier Skill Score 0.

### The R² trap

Section 9 forbids reporting an ordinary regression R² on a raw Bernoulli outcome
without a name that marks what it is; the quarantined pipeline did exactly that.
The panel closes this: `evaluate_metrics(..., outcome_type="bernoulli")` returns
**no `r2` key at all**, and instead returns a `brier_skill_score` whose name
marks it as the probability-prediction analogue. The section-9 weighted R² is
reported only for a continuous bump/residual target
(`outcome_type="continuous"`), which is what that formula is for.

No R² produced here is described as approaching a theoretical ceiling. The
7-wins/3-losses draft stopping rule puts an irreducible binomial floor under the
residual variance, and the ceiling is unknown without the latent per-observation
win probability. AUC is reported only as a secondary discrimination metric; the
scientific interest is accurate win probabilities, not merely ranking.

---

## 2. The probability clip

Before any logarithm, probabilities are clipped to
`[PROBABILITY_CLIP, 1 − PROBABILITY_CLIP]` with

```
PROBABILITY_CLIP = 1e-12
```

declared as a named constant in the module. This keeps a confident-and-wrong
prediction finite (penalty `−log(1e-12) ≈ 27.6`) rather than infinite, and a
perfect prediction near zero (`−log(1 − 1e-12) ≈ 1e-12`) rather than exactly
zero. The clip is applied to log loss and to the logit used in calibration; it is
not applied to Brier, RMSE, MAE or AUC, which take no logarithm.

---

## 3. Calibration

### Intercept and slope (Cox calibration)

`calibration_intercept_slope(y, p, w)` fits, by weighted logistic regression,

```
logit( E[y] ) = intercept + slope · logit(p̃)
```

Ideal intercept is 0 and ideal slope is 1. A slope **below 1** indicates
predictions that are too extreme (over-confident); a slope **above 1** indicates
predictions that are too conservative (under-confident). The tests assert both
directions on constructed fixtures whose calibration relation is exact (each true
probability `q` encoded as two weighted rows, `(y=1, w=q)` and `(y=0, w=1−q)`, so
the weighted outcome is exactly `q` with no sampling noise): an over-confident
set recovers slope `0.5`, an under-confident set recovers slope `2.0`, and a
well-calibrated set recovers intercept `0`, slope `1`.

### Binned calibration — one strategy, every model

`binned_calibration(y, p, w)` uses **equal-width bins over [0, 1]**:

```
CALIBRATION_BINS = 10
edges = linspace(0, 1, 11)
```

Equal-width — not equal-count/quantile — is deliberate: the bin edges are then
**identical across every model**, regardless of each model's prediction
distribution. Quantile bins would move with the model and amount to silent
rebinning. The rightmost edge is inclusive so `p = 1` lands in the last bin. The
**edges are returned alongside the per-bin counts, weighted counts, mean
predicted probability, and observed frequency**, so a downstream plot cannot
silently rebin. Bins with no weight carry `NaN` for the two means and 0 for the
counts.

### Smooth calibration — free of bin boundaries

`smooth_calibration(y, p, w)` provides a curve that does not depend on where the
bins fall, so a conclusion cannot rest on arbitrary bin boundaries. It is a
**weighted Gaussian-kernel (Nadaraya–Watson) regression** of the outcome on the
predicted probability:

```
SMOOTH_CALIBRATION_POINTS    = 101   (grid = linspace(0, 1, 101))
SMOOTH_CALIBRATION_BANDWIDTH = 0.05  (Gaussian kernel, in probability units)
```

For each grid point `g`, the smoothed observed frequency is
`Σ wᵢ K(pᵢ; g) yᵢ / Σ wᵢ K(pᵢ; g)` with `K` the Gaussian kernel centred at `g`.
Grid points with no kernel support carry `NaN`.

**GAMLSS is not part of this panel.** If a distributional/smooth calibration
diagnostic built on GAMLSS is wanted later, it is added as a **separate**
diagnostic and never folded into the core panel (§10).

---

## 4. The paired cluster bootstrap

`paired_cluster_bootstrap(...)` carries the uncertainty for the incremental-value
analysis of §11 using the paired cluster bootstrap of §12.

```
cluster level               = draft_id
DEFAULT_BOOTSTRAP_SEED       = 20260908
DEFAULT_BOOTSTRAP_REPLICATES = 1000
DEFAULT_CI_LEVEL             = 0.95   (2.5th–97.5th percentile interval)
```

**Clustered on the draft, not the row.** Each replicate resamples `draft_id`s
with replacement and includes **every game of each sampled draft together**.
Card 003 measured that a draft contributes multiple games and that 19% of drafts
change deck between them; games within a draft share a player, a skill bucket and
usually a deck. Resampling rows would treat them as independent and understate
the variance of exactly the comparisons this benchmark reports. Card 006's split
already partitions at the draft level, so the two agree. A test asserts that
every game of a sampled draft appears together in the resample.

**Paired across models.** All models predict the same observations, so a **single
set of resample indices is drawn per replicate and every model is scored on
exactly those indices**. The interval on a difference is then the variance of the
difference, not the summed variance of two independent resamples — an unpaired
resample per model would inflate the interval on a difference and could hide a
real effect as easily as manufacture one. A test asserts pairing directly: two
identical models produce an exactly-zero difference in every replicate.

**Intervals on differences, not only levels.** The result carries a confidence
interval for each model's absolute metric **and** for each requested pairwise
**difference** `metric(model_a) − metric(model_b)` — the incremental-value
question of §11 cannot be answered by an absolute level alone. The comparisons of
interest include each representation against the skill-only and identity
baselines, and `KG − identity` and `script − identity` directly.

**Deterministic.** The bootstrap draws its resamples from
`np.random.default_rng(seed)`; two runs with the same seed produce byte-identical
intervals. A test asserts this.

AUC is undefined on a single-class resample; the panel returns `NaN` there and
the bootstrap uses a NaN-aware percentile, so a rare degenerate resample does not
crash the run. On the frozen dataset (241,561 games) this does not arise in
practice.

---

## 5. Interpretation guard

Per §13, a null incremental result is a limit of the representation, learner and
dataset — **never** evidence that deck composition does not affect win
probability. The panel computes the differences and their intervals; it does not
label a difference whose interval crosses zero as an effect, and it does not
label the absence of a detectable difference as the absence of a deck effect.

---

## 6. Where each choice lives

| Choice | Constant / function in `deckbench.evaluation` |
| --- | --- |
| Probability clip | `PROBABILITY_CLIP = 1e-12` |
| Outcome families | `OUTCOME_BERNOULLI`, `OUTCOME_CONTINUOUS` |
| Scalar panel | `evaluate_metrics` |
| Calibration line | `calibration_intercept_slope` → `CalibrationLine` |
| Binning | `CALIBRATION_BINS = 10`, `binned_calibration` → `BinnedCalibration` |
| Smooth curve | `SMOOTH_CALIBRATION_POINTS`, `SMOOTH_CALIBRATION_BANDWIDTH`, `smooth_calibration` |
| Bootstrap | `DEFAULT_BOOTSTRAP_SEED = 20260908`, cluster `draft_id`, `paired_cluster_bootstrap` |

Self-test: `python -m deckbench.evaluation --selftest`.
