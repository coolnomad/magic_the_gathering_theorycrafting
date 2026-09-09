"""The evaluation panel every benchmark model is judged by (card 010).

Governed by ``docs/MTG_Deck-Strength_Modeling_Benchmark.md``. Sections 9-12 fix
the metrics, the calibration diagnostics, the incremental-value differences and
the paired cluster bootstrap that carries their uncertainty. This module is that
panel, and it is written **before a single model has been fitted against it** --
which is the point of the card. A metric chosen after seeing results is a degree
of freedom that can be steered toward a conclusion; fixing every choice here, in
advance, removes it. The concrete failure this prevents is in
``attic/haiku-2026-09-07/``: a ``KEY FINDINGS`` block asserting three checkmarked
improvements next to a companion analysis whose confidence interval crossed
zero, with no way to adjudicate between them.

What this module is, precisely:

* **A pure function of arrays.** Every entry point takes ``(y, p, weight,
  group)`` arrays and nothing else. It loads no parquet, never reads the split or
  the holdout, accepts no partition label, and does not know which model produced
  the predictions or what representation was used. The caller is accountable for
  which rows it is handed; the panel scores exactly those.
* **It fits nothing.** No learner is imported -- not xgboost, not
  ``sklearn.ensemble``, nothing from :mod:`deckbench.estimator`. The one place a
  model is fit at all is the calibration intercept/slope, which is a two-parameter
  weighted logistic regression solved by hand in :func:`_weighted_logistic_newton`
  with numpy alone; there is no learner library behind it.

The design decisions the benchmark pins, decided here rather than at reporting:

* **Weighting is universal.** Every metric weights by the passed observation
  weight; an unweighted metric silently answers a different question (section 9).
* **Probabilities are clipped before any logarithm** to :data:`PROBABILITY_CLIP`,
  a named constant recorded in ``reports/evaluation_panel.md``.
* **The R-squared trap is closed.** For a continuous bump/residual target the
  section-9 weighted R-squared is reported. For a Bernoulli outcome that formula
  is *not* reported unlabelled; the panel returns a :data:`BRIER_SKILL_SCORE`
  instead, whose name marks what it is. The wrong thing is made hard to say.
* **The bootstrap clusters on ``draft_id`` and is paired across models**
  (section 12). Resampling rows would treat a draft's several games as
  independent and understate the variance of exactly the comparisons the
  benchmark exists to make; an unpaired resample per model would inflate the
  interval on a *difference*. Both are structural here.
* **GAMLSS is not part of the panel.** A distributional/smooth calibration
  diagnostic built on it, if ever wanted, is added separately -- never folded
  into the core panel (section 10).

Run it with::

    python -m deckbench.evaluation --selftest

which exercises every entry point on small synthetic arrays, checks the
degenerate cases (perfect predictions score log loss 0 / Brier 0 / AUC 1;
predicting the weighted base rate scores R-squared 0), and confirms the bootstrap
is deterministic -- touching no file.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from collections.abc import Sequence

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

# --------------------------------------------------------------------------
# Declared constants. Every one of these is recorded in the report so a plot or
# a comparison cannot silently choose a different value.
# --------------------------------------------------------------------------

# Probabilities are clipped to [PROBABILITY_CLIP, 1 - PROBABILITY_CLIP] before any
# logarithm, so a confident-and-wrong prediction gets a large-but-finite penalty
# rather than an infinity, and a perfect prediction scores ~0 rather than exactly
# 0. Declared here, recorded in reports/evaluation_panel.md.
PROBABILITY_CLIP: float = 1e-12

# The two outcome families. A raw game outcome is Bernoulli; a bump/residual
# target is continuous. The caller declares which; the panel never infers it.
OUTCOME_BERNOULLI = "bernoulli"
OUTCOME_CONTINUOUS = "continuous"
OUTCOME_TYPES = (OUTCOME_BERNOULLI, OUTCOME_CONTINUOUS)

# Metric key names. Kept as constants so callers and the bootstrap refer to one
# spelling. Note there is deliberately no bare "r2" key for a Bernoulli outcome.
LOG_LOSS = "log_loss"
BRIER = "brier"
RMSE = "rmse"
MAE = "mae"
AUC = "auc"
R2 = "r2"
BRIER_SKILL_SCORE = "brier_skill_score"

# Binned calibration uses ONE declared strategy for every model: equal-width bins
# over [0, 1]. Equal-width (not equal-count) is the choice that makes the bin
# edges identical across models -- quantile bins would move with each model's
# prediction distribution, which is exactly the silent rebinning this forbids.
CALIBRATION_BINS: int = 10

# The smooth calibration curve is a weighted Nadaraya-Watson kernel regression of
# the outcome on the predicted probability, evaluated on this fixed grid with this
# fixed Gaussian bandwidth. It exists so a conclusion cannot rest on arbitrary bin
# boundaries.
SMOOTH_CALIBRATION_POINTS: int = 101
SMOOTH_CALIBRATION_BANDWIDTH: float = 0.05

# The paired cluster bootstrap: its cluster level is the draft, its default
# replicate count, seed and central interval are declared here and recorded in the
# report. Two runs with the same seed produce identical intervals.
DEFAULT_BOOTSTRAP_REPLICATES: int = 1000
DEFAULT_BOOTSTRAP_SEED: int = 20260908
DEFAULT_CI_LEVEL: float = 0.95


class OutcomeTypeUnknown(ValueError):
    """Raised when the caller names an outcome type that is not supported."""


class RSquaredOnBernoulli(ValueError):
    """Raised if an ordinary regression R-squared is requested on a Bernoulli outcome.

    Section 9 forbids reporting an unlabelled regression R-squared on a raw
    outcome; the quarantined pipeline did exactly that. The panel names the
    right quantity (a Brier Skill Score) and refuses the wrong one.
    """


# --------------------------------------------------------------------------
# Array hygiene.
# --------------------------------------------------------------------------


def _as_float(values: Sequence[float] | FloatArray) -> FloatArray:
    return np.asarray(values, dtype=np.float64)


def _weights(weight: Sequence[float] | FloatArray | None, n: int) -> FloatArray:
    """Return a length-n weight vector, defaulting to ones, validated non-negative."""
    if weight is None:
        return np.ones(n, dtype=np.float64)
    w = _as_float(weight)
    if w.shape != (n,):
        raise ValueError(f"weight must have shape ({n},); got {w.shape}.")
    if np.any(w < 0.0):
        raise ValueError("weights must be non-negative.")
    return w


def _check_lengths(y: FloatArray, p: FloatArray, w: FloatArray) -> None:
    if not (y.shape == p.shape == w.shape) or y.ndim != 1:
        raise ValueError(
            f"y, p and weight must be 1-D and share a length; got {y.shape}, "
            f"{p.shape}, {w.shape}."
        )
    if y.size == 0:
        raise ValueError("cannot evaluate an empty array.")


def _clip_prob(p: FloatArray) -> FloatArray:
    """Clip probabilities away from 0 and 1 before any logarithm."""
    return np.clip(p, PROBABILITY_CLIP, 1.0 - PROBABILITY_CLIP)


def _weighted_mean(values: FloatArray, w: FloatArray) -> float:
    total = float(np.sum(w))
    if total <= 0.0:
        raise ValueError("total weight must be positive.")
    return float(np.sum(w * values) / total)


# --------------------------------------------------------------------------
# The scalar metrics. Each is weighted; each is checked against hand arithmetic
# in the tests rather than against its own output.
# --------------------------------------------------------------------------


def log_loss(y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
             weight: Sequence[float] | FloatArray | None = None) -> float:
    """Weighted binary cross-entropy, with probabilities clipped first."""
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    pc = _clip_prob(p_)
    per_obs = -(y_ * np.log(pc) + (1.0 - y_) * np.log(1.0 - pc))
    return _weighted_mean(per_obs, w)


def brier_score(y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
                weight: Sequence[float] | FloatArray | None = None) -> float:
    """Weighted mean squared error between predicted probability and outcome."""
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    return _weighted_mean((p_ - y_) ** 2, w)


def rmse(y: Sequence[float] | FloatArray, yhat: Sequence[float] | FloatArray,
         weight: Sequence[float] | FloatArray | None = None) -> float:
    """Weighted root mean squared error."""
    y_, yhat_ = _as_float(y), _as_float(yhat)
    w = _weights(weight, y_.size)
    _check_lengths(y_, yhat_, w)
    return float(np.sqrt(_weighted_mean((y_ - yhat_) ** 2, w)))


def mae(y: Sequence[float] | FloatArray, yhat: Sequence[float] | FloatArray,
        weight: Sequence[float] | FloatArray | None = None) -> float:
    """Weighted mean absolute error -- less sensitive to a few large misses."""
    y_, yhat_ = _as_float(y), _as_float(yhat)
    w = _weights(weight, y_.size)
    _check_lengths(y_, yhat_, w)
    return _weighted_mean(np.abs(y_ - yhat_), w)


def auc(y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
        weight: Sequence[float] | FloatArray | None = None) -> float:
    """Weighted area under the ROC curve (weighted Mann-Whitney statistic).

    Ties in ``p`` are given half credit. Returns NaN when the sample carries only
    one outcome class, where AUC is undefined -- the bootstrap tolerates this with
    a NaN-aware percentile rather than crashing on a rare degenerate resample.
    """
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    pos = y_ == 1.0
    neg = y_ == 0.0
    if not np.all(pos | neg):
        raise ValueError("AUC requires a binary outcome in {0, 1}.")
    wpos_total = float(np.sum(w[pos]))
    wneg_total = float(np.sum(w[neg]))
    if wpos_total <= 0.0 or wneg_total <= 0.0:
        return float("nan")
    order = np.argsort(p_, kind="mergesort")
    ps, ys, ws = p_[order], y_[order], w[order]
    auc_sum = 0.0
    cum_neg = 0.0  # negative weight strictly below the current tie group
    i = 0
    n = ps.size
    while i < n:
        j = i
        while j < n and ps[j] == ps[i]:
            j += 1
        group_pos_w = float(np.sum(ws[i:j] * (ys[i:j] == 1.0)))
        group_neg_w = float(np.sum(ws[i:j] * (ys[i:j] == 0.0)))
        # Positives in this group beat every negative strictly below, and tie with
        # the negatives sharing their probability (half credit).
        auc_sum += group_pos_w * (cum_neg + 0.5 * group_neg_w)
        cum_neg += group_neg_w
        i = j
    return auc_sum / (wpos_total * wneg_total)


def weighted_r2(y: Sequence[float] | FloatArray, yhat: Sequence[float] | FloatArray,
                weight: Sequence[float] | FloatArray | None = None) -> float:
    """Weighted R-squared, the section-9 formula for a continuous target.

    ``1 - SS_res / SS_tot`` with the weighted mean of ``y`` as the baseline.
    Predicting that weighted mean everywhere scores exactly 0. This is the right
    quantity for a continuous bump/residual target; it is NOT reported unlabelled
    on a Bernoulli outcome (see :func:`evaluate_metrics`).
    """
    y_, yhat_ = _as_float(y), _as_float(yhat)
    w = _weights(weight, y_.size)
    _check_lengths(y_, yhat_, w)
    ybar = _weighted_mean(y_, w)
    ss_res = float(np.sum(w * (y_ - yhat_) ** 2))
    ss_tot = float(np.sum(w * (y_ - ybar) ** 2))
    if ss_tot <= 0.0:
        raise ValueError("R-squared is undefined when the weighted outcome variance is 0.")
    return 1.0 - ss_res / ss_tot


def brier_skill_score(y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
                      weight: Sequence[float] | FloatArray | None = None) -> float:
    """The Bernoulli-appropriate skill score: 1 - BS / BS(base rate).

    The reference forecast predicts the weighted base rate everywhere. Predicting
    that base rate scores exactly 0; a perfect forecast scores 1. This is the
    named probability-prediction analogue section 9 asks for in place of an
    ordinary regression R-squared on a raw outcome.
    """
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    base_rate = _weighted_mean(y_, w)
    bs = _weighted_mean((p_ - y_) ** 2, w)
    bs_ref = _weighted_mean((base_rate - y_) ** 2, w)
    if bs_ref <= 0.0:
        raise ValueError(
            "Brier Skill Score is undefined when the base-rate reference Brier is 0."
        )
    return 1.0 - bs / bs_ref


def evaluate_metrics(
    y: Sequence[float] | FloatArray,
    p: Sequence[float] | FloatArray,
    weight: Sequence[float] | FloatArray | None = None,
    *,
    outcome_type: str,
) -> dict[str, float]:
    """The scalar metric panel for one set of predictions.

    For :data:`OUTCOME_BERNOULLI` the panel reports log loss, Brier, RMSE, MAE,
    AUC and a :data:`BRIER_SKILL_SCORE` -- and deliberately no ``r2`` key, because
    an unlabelled regression R-squared on a raw outcome is forbidden by section 9.
    For :data:`OUTCOME_CONTINUOUS` (a bump/residual target) it reports RMSE, MAE
    and the section-9 weighted ``r2``; log loss, Brier and AUC do not apply to a
    continuous target and are not reported.
    """
    if outcome_type not in OUTCOME_TYPES:
        raise OutcomeTypeUnknown(
            f"outcome_type {outcome_type!r} is not supported; choose one of "
            f"{OUTCOME_TYPES}."
        )
    if outcome_type == OUTCOME_BERNOULLI:
        return {
            LOG_LOSS: log_loss(y, p, weight),
            BRIER: brier_score(y, p, weight),
            RMSE: rmse(y, p, weight),
            MAE: mae(y, p, weight),
            AUC: auc(y, p, weight),
            BRIER_SKILL_SCORE: brier_skill_score(y, p, weight),
        }
    return {
        RMSE: rmse(y, p, weight),
        MAE: mae(y, p, weight),
        R2: weighted_r2(y, p, weight),
    }


# --------------------------------------------------------------------------
# Calibration.
# --------------------------------------------------------------------------


def _sigmoid(z: FloatArray) -> FloatArray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def _weighted_logistic_newton(
    design: FloatArray, y: FloatArray, w: FloatArray, *, max_iter: int = 100,
    tol: float = 1e-10,
) -> FloatArray:
    """Fit a weighted logistic regression by Newton-Raphson, numpy only.

    Solves for the coefficients of ``design`` against binary ``y`` with
    observation weights ``w``. This is the whole of the "fitting" the panel does;
    it imports no learner. A tiny ridge keeps the Hessian invertible under
    near-separation without materially moving a well-conditioned solution.
    """
    n_params = design.shape[1]
    beta = np.zeros(n_params, dtype=np.float64)
    ridge = 1e-10 * np.eye(n_params)
    for _ in range(max_iter):
        eta = design @ beta
        mu = _sigmoid(eta)
        variance = w * mu * (1.0 - mu)
        gradient = design.T @ (w * (y - mu))
        hessian = design.T @ (design * variance[:, None]) + ridge
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            break
    return beta


@dataclass(frozen=True)
class CalibrationLine:
    """The Cox calibration intercept and slope. Ideal: intercept 0, slope 1.

    A slope below 1 indicates predictions that are too extreme (over-confident); a
    slope above 1 indicates predictions that are too conservative (under-confident).
    """

    intercept: float
    slope: float


def calibration_intercept_slope(
    y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
    weight: Sequence[float] | FloatArray | None = None,
) -> CalibrationLine:
    """Weighted Cox calibration: regress the outcome on ``logit(p)``.

    Fits ``logit(E[y]) = intercept + slope * logit(p)`` by weighted logistic
    regression. The slope moves below 1 for over-confident predictions and above 1
    for under-confident ones, in the known direction.
    """
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    pc = _clip_prob(p_)
    logit = np.log(pc / (1.0 - pc))
    design = np.column_stack([np.ones_like(logit), logit])
    beta = _weighted_logistic_newton(design, y_, w)
    return CalibrationLine(intercept=float(beta[0]), slope=float(beta[1]))


@dataclass(frozen=True)
class BinnedCalibration:
    """Binned calibration under one declared strategy, with the edges returned.

    The edges are returned so a plot cannot silently rebin. Bins with no weight
    carry NaN for the two means and 0 for the counts.
    """

    edges: FloatArray
    mean_predicted: FloatArray
    observed_frequency: FloatArray
    weight_sum: FloatArray
    count: IntArray


def binned_calibration(
    y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
    weight: Sequence[float] | FloatArray | None = None, *, n_bins: int = CALIBRATION_BINS,
) -> BinnedCalibration:
    """Equal-width binned calibration over [0, 1] -- one strategy, every model.

    The bin edges are ``linspace(0, 1, n_bins + 1)`` regardless of the prediction
    distribution, so every model is binned identically and the edges are returned
    alongside the counts.
    """
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    edges = np.linspace(0.0, 1.0, n_bins + 1, dtype=np.float64)
    # Assign each prediction to a bin in [0, n_bins-1]; the rightmost edge is
    # inclusive so p == 1 lands in the last bin.
    idx = np.clip(np.searchsorted(edges, p_, side="right") - 1, 0, n_bins - 1)
    mean_predicted = np.full(n_bins, np.nan, dtype=np.float64)
    observed = np.full(n_bins, np.nan, dtype=np.float64)
    weight_sum = np.zeros(n_bins, dtype=np.float64)
    count = np.zeros(n_bins, dtype=np.int64)
    for b in range(n_bins):
        mask = idx == b
        count[b] = int(np.count_nonzero(mask))
        wb = float(np.sum(w[mask]))
        weight_sum[b] = wb
        if wb > 0.0:
            mean_predicted[b] = float(np.sum(w[mask] * p_[mask]) / wb)
            observed[b] = float(np.sum(w[mask] * y_[mask]) / wb)
    return BinnedCalibration(
        edges=edges,
        mean_predicted=mean_predicted,
        observed_frequency=observed,
        weight_sum=weight_sum,
        count=count,
    )


@dataclass(frozen=True)
class SmoothCalibration:
    """A smooth calibration curve, free of bin boundaries.

    ``grid`` is the set of predicted-probability values at which the smoothed
    observed frequency is evaluated; ``observed`` is that frequency.
    """

    grid: FloatArray
    observed: FloatArray
    bandwidth: float


def smooth_calibration(
    y: Sequence[float] | FloatArray, p: Sequence[float] | FloatArray,
    weight: Sequence[float] | FloatArray | None = None, *,
    n_points: int = SMOOTH_CALIBRATION_POINTS, bandwidth: float = SMOOTH_CALIBRATION_BANDWIDTH,
) -> SmoothCalibration:
    """Weighted Gaussian-kernel (Nadaraya-Watson) calibration curve.

    For each grid point ``g`` the observed frequency is the kernel- and
    weight-weighted mean of ``y`` over all observations, with the Gaussian kernel
    centred at ``g``. It depends on a bandwidth, not on bin boundaries, so a
    conclusion cannot rest on where the bins happened to fall. Grid points with no
    kernel support carry NaN.
    """
    y_, p_ = _as_float(y), _as_float(p)
    w = _weights(weight, y_.size)
    _check_lengths(y_, p_, w)
    if bandwidth <= 0.0:
        raise ValueError("bandwidth must be positive.")
    grid = np.linspace(0.0, 1.0, n_points, dtype=np.float64)
    observed = np.full(n_points, np.nan, dtype=np.float64)
    for k, g in enumerate(grid):
        kernel = np.exp(-0.5 * ((p_ - g) / bandwidth) ** 2)
        denom = float(np.sum(w * kernel))
        if denom > 0.0:
            observed[k] = float(np.sum(w * kernel * y_) / denom)
    return SmoothCalibration(grid=grid, observed=observed, bandwidth=bandwidth)


# --------------------------------------------------------------------------
# The paired cluster bootstrap.
# --------------------------------------------------------------------------


def bootstrap_replicate_indices(
    groups: Sequence[object] | NDArray[np.object_],
    n_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> list[IntArray]:
    """Resample DRAFTS (clusters), not rows; return the row indices per replicate.

    Each replicate samples ``n_drafts`` draft ids with replacement and includes
    *every* row of each sampled draft, so games from one draft are never split
    apart -- resampling rows would treat them as independent and understate the
    variance of every comparison the benchmark reports (section 12). Deterministic
    in ``seed``: two calls with the same seed return identical index arrays.
    """
    group_arr = np.asarray(groups, dtype=object)
    unique = list(dict.fromkeys(group_arr.tolist()))  # first-seen order, stable
    rows_of: dict[object, IntArray] = {
        g: np.nonzero(group_arr == g)[0].astype(np.int64) for g in unique
    }
    n_drafts = len(unique)
    if n_drafts == 0:
        raise ValueError("cannot bootstrap an empty set of groups.")
    rng = np.random.default_rng(seed)
    replicates: list[IntArray] = []
    for _ in range(n_replicates):
        picks = rng.integers(0, n_drafts, size=n_drafts)
        chunks = [rows_of[unique[int(pick)]] for pick in picks]
        replicates.append(np.concatenate(chunks).astype(np.int64))
    return replicates


@dataclass(frozen=True)
class ConfidenceInterval:
    """A point estimate on the full sample and a percentile interval from replicates."""

    point: float
    lo: float
    hi: float


@dataclass(frozen=True)
class BootstrapResult:
    """Paired-cluster-bootstrap intervals for each model and each model difference."""

    model_metrics: dict[str, dict[str, ConfidenceInterval]]
    differences: dict[str, dict[str, ConfidenceInterval]]
    n_replicates: int
    seed: int
    ci_level: float
    cluster_level: str = "draft_id"
    replicate_indices: list[IntArray] = field(default_factory=list, repr=False)


def _percentile_ci(point: float, samples: list[float], ci_level: float) -> ConfidenceInterval:
    arr = np.asarray(samples, dtype=np.float64)
    alpha = (1.0 - ci_level) / 2.0
    lo = float(np.nanpercentile(arr, 100.0 * alpha))
    hi = float(np.nanpercentile(arr, 100.0 * (1.0 - alpha)))
    return ConfidenceInterval(point=point, lo=lo, hi=hi)


def paired_cluster_bootstrap(
    models: dict[str, Sequence[float] | FloatArray],
    y: Sequence[float] | FloatArray,
    groups: Sequence[object] | NDArray[np.object_],
    *,
    metrics: Sequence[str],
    comparisons: Sequence[tuple[str, str]],
    outcome_type: str,
    weight: Sequence[float] | FloatArray | None = None,
    n_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    ci_level: float = DEFAULT_CI_LEVEL,
) -> BootstrapResult:
    """Paired cluster bootstrap over drafts; intervals for each model and difference.

    Every model predicts the same observations, so a single set of resample
    indices is drawn per replicate and *every* model is scored on exactly those
    indices (the pairing of section 12). The interval on a difference is therefore
    the variance of the difference, not the summed variance of two independent
    resamples. Clustering is at the draft (section 12); the same seed reproduces
    the intervals byte for byte.

    ``comparisons`` are ``(model_a, model_b)`` pairs; the reported difference is
    ``metric(model_a) - metric(model_b)`` per requested metric. Confidence
    intervals are returned both for each model's absolute metric and for each
    difference -- an absolute level alone cannot answer the incremental-value
    question of section 11.
    """
    if outcome_type not in OUTCOME_TYPES:
        raise OutcomeTypeUnknown(
            f"outcome_type {outcome_type!r} is not supported; choose one of "
            f"{OUTCOME_TYPES}."
        )
    y_ = _as_float(y)
    w = _weights(weight, y_.size)
    preds = {name: _as_float(p) for name, p in models.items()}
    for p in preds.values():
        _check_lengths(y_, p, w)
    for a, b in comparisons:
        if a not in preds or b not in preds:
            raise KeyError(f"comparison ({a!r}, {b!r}) names a model not in `models`.")
    for metric in metrics:
        # A metric requested on a target formulation that does not report it is a
        # caller error, caught once here rather than per replicate.
        available = evaluate_metrics(
            y_, next(iter(preds.values())), w, outcome_type=outcome_type
        )
        if metric not in available:
            raise KeyError(
                f"metric {metric!r} is not reported for outcome_type "
                f"{outcome_type!r}; available: {sorted(available)}."
            )

    def metrics_for(p: FloatArray, idx: IntArray | None) -> dict[str, float]:
        if idx is None:
            full = evaluate_metrics(y_, p, w, outcome_type=outcome_type)
        else:
            full = evaluate_metrics(y_[idx], p[idx], w[idx], outcome_type=outcome_type)
        return {m: full[m] for m in metrics}

    # Point estimates on the full (unresampled) sample.
    point_model = {name: metrics_for(p, None) for name, p in preds.items()}

    replicates = bootstrap_replicate_indices(groups, n_replicates, seed)

    model_samples: dict[str, dict[str, list[float]]] = {
        name: {m: [] for m in metrics} for name in preds
    }
    diff_samples: dict[str, dict[str, list[float]]] = {
        _comparison_key(a, b): {m: [] for m in metrics} for a, b in comparisons
    }
    for idx in replicates:
        # One resample, scored by every model -- this is the pairing.
        per_model = {name: metrics_for(p, idx) for name, p in preds.items()}
        for name, scored in per_model.items():
            for m in metrics:
                model_samples[name][m].append(scored[m])
        for a, b in comparisons:
            key = _comparison_key(a, b)
            for m in metrics:
                diff_samples[key][m].append(per_model[a][m] - per_model[b][m])

    model_metrics = {
        name: {
            m: _percentile_ci(point_model[name][m], model_samples[name][m], ci_level)
            for m in metrics
        }
        for name in preds
    }
    differences = {
        _comparison_key(a, b): {
            m: _percentile_ci(
                point_model[a][m] - point_model[b][m],
                diff_samples[_comparison_key(a, b)][m],
                ci_level,
            )
            for m in metrics
        }
        for a, b in comparisons
    }
    return BootstrapResult(
        model_metrics=model_metrics,
        differences=differences,
        n_replicates=n_replicates,
        seed=seed,
        ci_level=ci_level,
        replicate_indices=replicates,
    )


def _comparison_key(a: str, b: str) -> str:
    return f"{a}__minus__{b}"


# --------------------------------------------------------------------------
# Self-test: exercise every entry point on synthetic arrays, touching no file.
# --------------------------------------------------------------------------


def _selftest() -> int:
    rng = np.random.default_rng(0)
    n = 600
    groups = np.array([f"draft{i // 3:03d}" for i in range(n)], dtype=object)
    weight = rng.uniform(0.5, 1.5, size=n)
    logit = rng.normal(size=n)
    q = _sigmoid(logit)
    y = (rng.uniform(size=n) < q).astype(np.float64)

    # Degenerate cases: perfect predictions and the base-rate forecast.
    perfect = evaluate_metrics(y, y, weight, outcome_type=OUTCOME_BERNOULLI)
    assert perfect[LOG_LOSS] < 1e-9, perfect[LOG_LOSS]
    assert perfect[BRIER] == 0.0
    assert perfect[AUC] == 1.0
    base_rate = _weighted_mean(y, _weights(weight, n))
    bss0 = brier_skill_score(y, np.full(n, base_rate), weight)
    assert abs(bss0) < 1e-12, bss0
    r2_0 = weighted_r2(y, np.full(n, base_rate), weight)
    assert abs(r2_0) < 1e-12, r2_0

    # The R-squared trap: no bare r2 for a Bernoulli outcome; a BSS instead.
    panel = evaluate_metrics(y, q, weight, outcome_type=OUTCOME_BERNOULLI)
    assert R2 not in panel and BRIER_SKILL_SCORE in panel

    # Calibration direction: over-confident -> slope < 1; under-confident -> > 1.
    over = _sigmoid(2.0 * logit)
    under = _sigmoid(0.5 * logit)
    assert calibration_intercept_slope(y, over, weight).slope < 1.0
    assert calibration_intercept_slope(y, under, weight).slope > 1.0

    binned = binned_calibration(y, q, weight)
    assert binned.edges.size == CALIBRATION_BINS + 1
    smooth = smooth_calibration(y, q, weight)
    assert smooth.grid.size == SMOOTH_CALIBRATION_POINTS

    # The bootstrap is paired (identical models -> zero difference) and deterministic.
    boot = paired_cluster_bootstrap(
        {"a": q, "b": q},
        y,
        groups,
        metrics=[BRIER, LOG_LOSS],
        comparisons=[("a", "b")],
        outcome_type=OUTCOME_BERNOULLI,
        weight=weight,
        n_replicates=50,
    )
    diff = boot.differences[_comparison_key("a", "b")][BRIER]
    assert diff.lo == 0.0 and diff.hi == 0.0 and diff.point == 0.0
    again = paired_cluster_bootstrap(
        {"a": q, "b": q},
        y,
        groups,
        metrics=[BRIER, LOG_LOSS],
        comparisons=[("a", "b")],
        outcome_type=OUTCOME_BERNOULLI,
        weight=weight,
        n_replicates=50,
    )
    assert boot.model_metrics["a"][BRIER].lo == again.model_metrics["a"][BRIER].lo

    print(
        "evaluation selftest OK: weighted metrics, the degenerate cases, the "
        "R-squared trap, calibration direction, binned + smooth calibration, and "
        "a paired deterministic cluster bootstrap -- no file touched."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="exercise every entry point on synthetic arrays and check invariants.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.selftest:
        return _selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
