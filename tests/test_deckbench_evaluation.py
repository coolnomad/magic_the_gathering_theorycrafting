"""Tests for the evaluation panel (:mod:`deckbench.evaluation`).

The panel is a pre-registration device: it is written before any model is scored,
so the tests here pin the arithmetic and the guarantees that make a later
comparison adjudicable. Each metric is checked against a hand-computed value, not
against its own output; the degenerate cases are asserted; the R-squared trap is
closed; calibration slope moves in the known direction; the bootstrap clusters on
drafts, is paired across models, returns intervals on differences, and is
deterministic. Two structural properties are also enforced by reading the module
source: it imports no learner and nothing from :mod:`deckbench.estimator`, and it
reads no parquet, split or holdout.
"""

from __future__ import annotations

import ast
import math
import tokenize
from pathlib import Path

import numpy as np
import pytest

from deckbench import evaluation as ev

# --------------------------------------------------------------------------
# A single small fixture, with weights, whose every metric is hand-computable.
#
#   y = [1, 0, 1, 0]
#   p = [0.8, 0.3, 0.6, 0.4]
#   w = [1, 2, 1, 2]        (total weight 6)
# --------------------------------------------------------------------------

Y = [1.0, 0.0, 1.0, 0.0]
P = [0.8, 0.3, 0.6, 0.4]
W = [1.0, 2.0, 1.0, 2.0]
_WSUM = 6.0


def test_brier_matches_hand_arithmetic() -> None:
    # sum w*(p-y)^2 / sum w
    expected = (1 * 0.04 + 2 * 0.09 + 1 * 0.16 + 2 * 0.16) / _WSUM
    assert ev.brier_score(Y, P, W) == pytest.approx(expected)


def test_mae_matches_hand_arithmetic() -> None:
    expected = (1 * 0.2 + 2 * 0.3 + 1 * 0.4 + 2 * 0.4) / _WSUM
    assert ev.mae(Y, P, W) == pytest.approx(expected)


def test_rmse_matches_hand_arithmetic() -> None:
    expected = math.sqrt((1 * 0.04 + 2 * 0.09 + 1 * 0.16 + 2 * 0.16) / _WSUM)
    assert ev.rmse(Y, P, W) == pytest.approx(expected)


def test_log_loss_matches_hand_arithmetic() -> None:
    # -sum w*(y log p + (1-y) log(1-p)) / sum w, with the same clip the module uses.
    terms = (
        1 * (-math.log(0.8))
        + 2 * (-math.log(1 - 0.3))
        + 1 * (-math.log(0.6))
        + 2 * (-math.log(1 - 0.4))
    )
    assert ev.log_loss(Y, P, W) == pytest.approx(terms / _WSUM)


def test_weighted_r2_matches_hand_arithmetic() -> None:
    ybar = (1 * 1 + 2 * 0 + 1 * 1 + 2 * 0) / _WSUM  # 1/3
    ss_res = 1 * 0.04 + 2 * 0.09 + 1 * 0.16 + 2 * 0.16  # 0.70
    ss_tot = 1 * (1 - ybar) ** 2 + 2 * (0 - ybar) ** 2 + 1 * (1 - ybar) ** 2 + 2 * (0 - ybar) ** 2
    assert ev.weighted_r2(Y, P, W) == pytest.approx(1 - ss_res / ss_tot)


def test_brier_skill_score_matches_hand_arithmetic() -> None:
    ybar = 1 / 3
    bs = (1 * 0.04 + 2 * 0.09 + 1 * 0.16 + 2 * 0.16) / _WSUM
    bs_ref = (1 * (1 - ybar) ** 2 + 2 * ybar**2 + 1 * (1 - ybar) ** 2 + 2 * ybar**2) / _WSUM
    assert ev.brier_skill_score(Y, P, W) == pytest.approx(1 - bs / bs_ref)


def test_auc_matches_hand_arithmetic_unweighted() -> None:
    # positives p in {0.9, 0.3}, negatives p in {0.8, 0.4}. Concordant pairs:
    # (0.9>0.8), (0.9>0.4) win; (0.3>0.8), (0.3>0.4) lose. 2 of 4 -> 0.5.
    y = [1, 0, 1, 0]
    p = [0.9, 0.8, 0.3, 0.4]
    assert ev.auc(y, p) == pytest.approx(0.5)


def test_auc_handles_ties_with_half_credit() -> None:
    # One positive and one negative share p; that pair scores 0.5. The other
    # positive (0.9) beats both negatives. Pairs: pos0.9 vs {neg0.5, neg0.2} -> 2
    # wins; pos0.5 vs neg0.5 -> tie 0.5; pos0.5 vs neg0.2 -> win 1. Total 3.5/4.
    y = [1, 0, 1, 0]
    p = [0.9, 0.5, 0.5, 0.2]
    assert ev.auc(y, p) == pytest.approx(3.5 / 4)


def test_auc_is_weighted() -> None:
    # Same predictions as the unweighted 0.5 case, but weight the concordant
    # positive heavily so the weighted AUC exceeds 0.5.
    y = [1, 0, 1, 0]
    p = [0.9, 0.8, 0.3, 0.4]
    w = [10.0, 1.0, 1.0, 1.0]
    # pos weights: 0.9->10, 0.3->1 ; neg weights: 0.8->1, 0.4->1.
    # concordant weight = 10*(1+1) [0.9 beats both] + 1*0 [0.3 beats none] = 20.
    # total = (10+1)*(1+1) = 22. AUC = 20/22.
    assert ev.auc(y, p, w) == pytest.approx(20 / 22)


# --------------------------------------------------------------------------
# Degenerate cases, asserted directly.
# --------------------------------------------------------------------------


def test_perfect_predictions_score_zero_loss_and_unit_auc() -> None:
    y = [1.0, 0.0, 1.0, 0.0, 1.0]
    w = [1.0, 2.0, 3.0, 1.0, 2.0]
    assert ev.log_loss(y, y, w) < 1e-9
    assert ev.brier_score(y, y, w) == 0.0
    assert ev.auc(y, y, w) == 1.0


def test_base_rate_forecast_scores_zero_r2_and_zero_bss() -> None:
    y = [1.0, 0.0, 1.0, 0.0, 1.0]
    w = [1.0, 2.0, 3.0, 1.0, 2.0]
    base_rate = float(np.average(np.asarray(y), weights=np.asarray(w)))
    const = [base_rate] * len(y)
    assert ev.weighted_r2(y, const, w) == pytest.approx(0.0, abs=1e-12)
    assert ev.brier_skill_score(y, const, w) == pytest.approx(0.0, abs=1e-12)


def test_clip_constant_keeps_confident_wrong_finite() -> None:
    # A confidently-wrong prediction is penalised heavily but finitely, thanks to
    # the declared clip. Without clipping this would be +inf.
    assert math.isfinite(ev.log_loss([1.0], [0.0]))
    assert ev.log_loss([1.0], [0.0]) == pytest.approx(-math.log(ev.PROBABILITY_CLIP))


# --------------------------------------------------------------------------
# The R-squared trap: a Bernoulli outcome gets no unlabelled regression R^2.
# --------------------------------------------------------------------------


def test_bernoulli_panel_has_no_bare_r2_but_has_a_named_skill_score() -> None:
    panel = ev.evaluate_metrics(Y, P, W, outcome_type=ev.OUTCOME_BERNOULLI)
    assert ev.R2 not in panel
    assert ev.BRIER_SKILL_SCORE in panel
    assert set(panel) == {ev.LOG_LOSS, ev.BRIER, ev.RMSE, ev.MAE, ev.AUC,
                          ev.BRIER_SKILL_SCORE}


def test_continuous_panel_reports_the_section9_r2() -> None:
    # For a continuous bump target the section-9 weighted R^2 is the right thing.
    yhat = [0.9, 0.1, 0.7, 0.2]
    panel = ev.evaluate_metrics(Y, yhat, W, outcome_type=ev.OUTCOME_CONTINUOUS)
    assert set(panel) == {ev.RMSE, ev.MAE, ev.R2}
    assert panel[ev.R2] == pytest.approx(ev.weighted_r2(Y, yhat, W))


def test_unknown_outcome_type_is_rejected() -> None:
    with pytest.raises(ev.OutcomeTypeUnknown):
        ev.evaluate_metrics(Y, P, W, outcome_type="poisson")


# --------------------------------------------------------------------------
# Calibration intercept and slope move in the known direction.
#
# The fixture encodes an exact calibration relation with no sampling noise: for
# each true probability q, two rows -- (y=1, weight=q) and (y=0, weight=1-q) --
# make the weighted outcome exactly q. Predicted p is a monotone distortion of q.
# --------------------------------------------------------------------------


def _exact_calibration_fixture(distort: float) -> tuple[list[float], list[float], list[float]]:
    """Return (y, p, weight) with E[y | logit p] exactly logit(q)/distort.

    ``distort > 1`` makes the prediction more extreme than the truth
    (over-confident); ``distort < 1`` makes it more moderate (under-confident).
    """
    logits = np.linspace(-3.0, 3.0, 25)
    q = 1.0 / (1.0 + np.exp(-logits))
    p = 1.0 / (1.0 + np.exp(-distort * logits))
    y: list[float] = []
    pp: list[float] = []
    w: list[float] = []
    for qi, pi in zip(q.tolist(), p.tolist(), strict=True):
        y.extend([1.0, 0.0])
        pp.extend([pi, pi])
        w.extend([qi, 1.0 - qi])
    return y, pp, w


def test_overconfident_predictions_pull_slope_below_one() -> None:
    y, p, w = _exact_calibration_fixture(distort=2.0)  # predictions too extreme
    line = ev.calibration_intercept_slope(y, p, w)
    assert line.slope < 1.0
    # The exact construction recovers slope = 1/distort = 0.5.
    assert line.slope == pytest.approx(0.5, abs=1e-3)


def test_underconfident_predictions_pull_slope_above_one() -> None:
    y, p, w = _exact_calibration_fixture(distort=0.5)  # predictions too moderate
    line = ev.calibration_intercept_slope(y, p, w)
    assert line.slope > 1.0
    assert line.slope == pytest.approx(2.0, abs=1e-3)


def test_wellcalibrated_predictions_give_intercept_zero_slope_one() -> None:
    y, p, w = _exact_calibration_fixture(distort=1.0)
    line = ev.calibration_intercept_slope(y, p, w)
    assert line.intercept == pytest.approx(0.0, abs=1e-3)
    assert line.slope == pytest.approx(1.0, abs=1e-3)


# --------------------------------------------------------------------------
# Binned calibration: one strategy, identical edges for every model, edges
# returned so a plot cannot rebin.
# --------------------------------------------------------------------------


def test_binned_calibration_edges_are_identical_across_models() -> None:
    a = ev.binned_calibration([1, 0, 1], [0.05, 0.55, 0.95])
    b = ev.binned_calibration([0, 1], [0.5, 0.5])  # a very different distribution
    assert np.array_equal(a.edges, b.edges)
    assert a.edges.size == ev.CALIBRATION_BINS + 1
    assert a.edges[0] == 0.0 and a.edges[-1] == 1.0


def test_binned_calibration_counts_and_observed_are_correct() -> None:
    # Two predictions in bin 0 ([0.0,0.1)) with outcomes 1 and 0 -> observed 0.5;
    # one prediction in the last bin ([0.9,1.0]) with outcome 1 -> observed 1.0.
    y = [1, 0, 1]
    p = [0.05, 0.05, 0.95]
    binned = ev.binned_calibration(y, p)
    assert binned.count[0] == 2
    assert binned.count[-1] == 1
    assert binned.observed_frequency[0] == pytest.approx(0.5)
    assert binned.observed_frequency[-1] == pytest.approx(1.0)
    assert binned.mean_predicted[0] == pytest.approx(0.05)
    # Untouched bins carry NaN and zero count.
    assert binned.count[5] == 0
    assert math.isnan(binned.mean_predicted[5])


def test_binned_calibration_rightmost_edge_is_inclusive() -> None:
    binned = ev.binned_calibration([1], [1.0])
    assert binned.count[-1] == 1


# --------------------------------------------------------------------------
# Smooth calibration: a curve free of bin boundaries.
# --------------------------------------------------------------------------


def test_smooth_calibration_tracks_identity_on_calibrated_data() -> None:
    y, p, w = _exact_calibration_fixture(distort=1.0)
    smooth = ev.smooth_calibration(y, p, w)
    assert smooth.grid.size == ev.SMOOTH_CALIBRATION_POINTS
    interior = (smooth.grid >= 0.2) & (smooth.grid <= 0.8)
    diff = np.abs(smooth.observed[interior] - smooth.grid[interior])
    assert np.nanmax(diff) < 0.05


# --------------------------------------------------------------------------
# The paired cluster bootstrap.
# --------------------------------------------------------------------------


def _bootstrap_data(
    n_drafts: int = 30, games: int = 3
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(3)
    groups = np.array(
        [f"draft{d:03d}" for d in range(n_drafts) for _ in range(games)], dtype=object
    )
    n = groups.size
    weight = rng.uniform(0.5, 1.5, size=n)
    logit = rng.normal(size=n)
    q = 1.0 / (1.0 + np.exp(-logit))
    y = (rng.uniform(size=n) < q).astype(np.float64)
    p_good = q
    p_bad = np.full(n, float(np.average(y, weights=weight)))  # base-rate forecast
    return groups, y, weight, p_good, p_bad


def test_resample_draws_whole_drafts_together() -> None:
    groups, *_ = _bootstrap_data()
    reps = ev.bootstrap_replicate_indices(groups, n_replicates=5, seed=42)
    row_group = groups
    for idx in reps:
        sampled = row_group[idx]
        # For every draft that appears, each of its member rows appears the same
        # number of times -- i.e. drafts are resampled whole, never row by row.
        for draft in set(sampled.tolist()):
            member_rows = np.nonzero(row_group == draft)[0]
            counts = np.array(
                [int(np.count_nonzero(idx == r)) for r in member_rows]
            )
            assert counts.min() == counts.max() and counts.min() >= 1


def test_replicate_indices_are_deterministic_under_seed() -> None:
    groups, *_ = _bootstrap_data()
    a = ev.bootstrap_replicate_indices(groups, n_replicates=7, seed=99)
    b = ev.bootstrap_replicate_indices(groups, n_replicates=7, seed=99)
    assert all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))


def test_bootstrap_is_paired_identical_models_give_zero_difference() -> None:
    groups, y, weight, p_good, _ = _bootstrap_data()
    result = ev.paired_cluster_bootstrap(
        {"a": p_good, "b": p_good},
        y,
        groups,
        metrics=[ev.BRIER, ev.LOG_LOSS],
        comparisons=[("a", "b")],
        outcome_type=ev.OUTCOME_BERNOULLI,
        weight=weight,
        n_replicates=100,
    )
    key = ev._comparison_key("a", "b")
    for metric in (ev.BRIER, ev.LOG_LOSS):
        ci = result.differences[key][metric]
        assert ci.point == 0.0 and ci.lo == 0.0 and ci.hi == 0.0


def test_bootstrap_scores_every_model_on_the_same_replicate_indices() -> None:
    # The result exposes the per-replicate indices; independently regenerating them
    # from the declared seed reproduces exactly what the bootstrap used -- the same
    # indices fed every model.
    groups, y, weight, p_good, p_bad = _bootstrap_data()
    result = ev.paired_cluster_bootstrap(
        {"a": p_good, "b": p_bad},
        y,
        groups,
        metrics=[ev.BRIER],
        comparisons=[("a", "b")],
        outcome_type=ev.OUTCOME_BERNOULLI,
        weight=weight,
        n_replicates=20,
        seed=1234,
    )
    regenerated = ev.bootstrap_replicate_indices(groups, n_replicates=20, seed=1234)
    assert len(result.replicate_indices) == len(regenerated)
    assert all(
        np.array_equal(x, y) for x, y in zip(result.replicate_indices, regenerated, strict=True)
    )


def test_bootstrap_returns_intervals_for_models_and_for_differences() -> None:
    groups, y, weight, p_good, p_bad = _bootstrap_data()
    result = ev.paired_cluster_bootstrap(
        {"good": p_good, "bad": p_bad},
        y,
        groups,
        metrics=[ev.BRIER],
        comparisons=[("good", "bad")],
        outcome_type=ev.OUTCOME_BERNOULLI,
        weight=weight,
        n_replicates=200,
    )
    # Absolute intervals for each model.
    assert result.model_metrics["good"][ev.BRIER].lo <= result.model_metrics["good"][ev.BRIER].hi
    # And an interval on the difference, distinct from the two absolute ones.
    diff = result.differences[ev._comparison_key("good", "bad")][ev.BRIER]
    assert diff.lo <= diff.point <= diff.hi
    assert result.cluster_level == "draft_id"


def test_bootstrap_is_deterministic_under_seed() -> None:
    groups, y, weight, p_good, p_bad = _bootstrap_data()
    kwargs = dict(
        metrics=[ev.BRIER, ev.LOG_LOSS],
        comparisons=[("a", "b")],
        outcome_type=ev.OUTCOME_BERNOULLI,
        weight=weight,
        n_replicates=100,
        seed=2026,
    )
    first = ev.paired_cluster_bootstrap({"a": p_good, "b": p_bad}, y, groups, **kwargs)
    second = ev.paired_cluster_bootstrap({"a": p_good, "b": p_bad}, y, groups, **kwargs)
    key = ev._comparison_key("a", "b")
    for metric in (ev.BRIER, ev.LOG_LOSS):
        assert first.differences[key][metric].lo == second.differences[key][metric].lo
        assert first.differences[key][metric].hi == second.differences[key][metric].hi


def test_bootstrap_rejects_a_metric_not_reported_for_the_outcome() -> None:
    groups, y, weight, p_good, p_bad = _bootstrap_data()
    with pytest.raises(KeyError):
        ev.paired_cluster_bootstrap(
            {"a": p_good, "b": p_bad},
            y,
            groups,
            metrics=[ev.R2],  # not reported for a Bernoulli outcome
            comparisons=[("a", "b")],
            outcome_type=ev.OUTCOME_BERNOULLI,
            weight=weight,
            n_replicates=5,
        )


# --------------------------------------------------------------------------
# Structural guarantees. These read the module's *code*, not its prose: imports
# are inspected with the ast, and identifiers with the tokenizer, so a docstring
# that names xgboost to say it is absent cannot trip the check.
# --------------------------------------------------------------------------


def _imported_modules() -> set[str]:
    tree = ast.parse(Path(ev.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def _code_identifiers() -> set[str]:
    """The set of NAME tokens in the source -- code identifiers, no strings/comments."""
    with tokenize.open(ev.__file__) as handle:
        return {
            tok.string
            for tok in tokenize.generate_tokens(handle.readline)
            if tok.type == tokenize.NAME
        }


def test_module_imports_no_learner_and_nothing_from_the_estimator() -> None:
    imported = _imported_modules()
    forbidden_roots = ("xgboost", "sklearn", "torch", "lightgbm", "catboost")
    for module in imported:
        root = module.split(".")[0]
        assert root not in forbidden_roots, f"the panel imports a learner: {module!r}"
        assert module != "deckbench.estimator" and not module.startswith("deckbench.estimator"), (
            f"the panel imports the estimator: {module!r}"
        )
    # Never imported means never called; there is nothing from the estimator to call.
    assert "estimator" not in _code_identifiers()


def test_module_reads_no_parquet_no_split_no_holdout() -> None:
    # No file/parquet/holdout reader is referenced anywhere in the code.
    identifiers = _code_identifiers()
    for forbidden in ("read_table", "read_parquet", "ParquetFile", "load_holdout",
                      "load_dev", "open", "Path", "read_text", "read_bytes"):
        assert forbidden not in identifiers, f"the panel references {forbidden!r}"
    assert not any(m.split(".")[0] in {"pyarrow", "pandas"} for m in _imported_modules())


def test_module_takes_no_partition_argument() -> None:
    # The panel scores whatever arrays it is handed; it must not accept a
    # partition label and decide for itself which rows to score.
    assert "partition" not in _code_identifiers()


# --------------------------------------------------------------------------
# The self-test entry point runs clean.
# --------------------------------------------------------------------------


def test_selftest_runs_and_returns_zero() -> None:
    assert ev.main(["--selftest"]) == 0
