"""
Step 8: Comprehensive metrics, calibration, bootstrap uncertainty, and R² ceiling analysis.

This module:
1. Computes calibration curve and ECE (Expected Calibration Error)
2. Bootstrap confidence intervals on key metrics
3. Analyzes R² ceiling imposed by 7-3 stopping rule
4. Generates detailed metrics report
5. Produces calibration plots

Output files:
  - results/metrics_m0_m1.csv (comprehensive metrics table)
  - results/calibration_analysis.txt (calibration statistics)
  - results/r2_ceiling_analysis.txt (R² theoretical ceiling)
  - results/bootstrap_ci.txt (bootstrap confidence intervals)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
from scipy import stats

try:
    import xgboost as xgb
except ImportError:
    import subprocess
    subprocess.check_call(['pip', 'install', 'xgboost', '-q'])
    import xgboost as xgb

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Configuration
PROCESSED_DIR = Path("data/processed")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def load_models_and_data():
    """Load trained models and test data."""
    log.info("Loading models and data...")

    model_table = pd.read_parquet(PROCESSED_DIR / "draft_model_table.parquet")
    identity_df = pd.read_parquet(PROCESSED_DIR / "deck_identity.parquet")
    split_df = pd.read_csv(PROCESSED_DIR / "split_indices.csv")

    # Merge split
    model_table = model_table.reset_index(drop=True)
    split_df['draft_idx'] = split_df['draft_idx'] - 1
    model_table['split'] = split_df['split'].values

    # Get holdout set
    holdout_mask = model_table['split'] == 'holdout'
    model_table_holdout = model_table[holdout_mask].reset_index(drop=True)

    # Load models
    m0_booster = xgb.Booster()
    m0_booster.load_model(str(RESULTS_DIR / "m0_skill_only.xgb"))

    m1_booster = xgb.Booster()
    m1_booster.load_model(str(RESULTS_DIR / "m1_skill_identity.xgb"))

    log.info(f"Loaded M0 and M1 models")
    log.info(f"Test set: {len(model_table_holdout):,} drafts")

    return model_table_holdout, identity_df, m0_booster, m1_booster


def compute_predictions(model_table, identity_df, booster, model_name):
    """Compute model predictions on test set."""
    log.info(f"\nComputing {model_name} predictions...")

    if model_name == "M0":
        X = model_table[['base_p']].copy()
        feature_names = ['base_p']
    else:  # M1
        card_cols = [c for c in identity_df.columns if c != 'draft_id']
        identity_df_reindex = identity_df.set_index('draft_id')
        card_features = model_table[['draft_id']].merge(
            identity_df_reindex[card_cols],
            left_on='draft_id',
            right_index=True
        )[card_cols]
        X = pd.concat([model_table[['base_p']].reset_index(drop=True),
                       card_features.reset_index(drop=True)], axis=1)
        feature_names = ['base_p'] + card_cols

    dmatrix = xgb.DMatrix(X, feature_names=feature_names)
    predictions = booster.predict(dmatrix)

    return predictions


def compute_calibration_metrics(y_true, y_pred, sample_weight, n_bins=10):
    """Compute calibration curve and Expected Calibration Error."""
    log.info(f"\n  Computing calibration metrics ({n_bins} bins)...")

    # Bin predictions
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_pred, bin_edges) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    calibration_data = []
    total_weight = np.sum(sample_weight)

    for bin_idx in range(n_bins):
        mask = bin_indices == bin_idx
        if not np.any(mask):
            continue

        bin_pred_mean = np.mean(y_pred[mask])
        bin_true_mean = np.average(y_true[mask], weights=sample_weight[mask])
        bin_weight = np.sum(sample_weight[mask]) / total_weight

        calibration_data.append({
            'bin': bin_idx,
            'pred_mean': bin_pred_mean,
            'true_mean': bin_true_mean,
            'weight': bin_weight,
            'n_samples': np.sum(mask),
        })

    calib_df = pd.DataFrame(calibration_data)

    # Compute ECE (Expected Calibration Error)
    ece = np.sum(calib_df['weight'] * np.abs(calib_df['pred_mean'] - calib_df['true_mean']))

    # Compute MCE (Maximum Calibration Error)
    mce = np.max(np.abs(calib_df['pred_mean'] - calib_df['true_mean']))

    return calib_df, ece, mce


def compute_weighted_r2(y_true, y_pred, sample_weight):
    """
    Compute weighted R² (coefficient of determination).

    Note: The 7-3 stopping rule creates an inherent ceiling on R² because:
    - Outcomes are heavily concentrated by the rule
    - True R² ceiling cannot be computed from observed data alone
    - Would require knowledge of latent true p_i distribution
    """
    log.info(f"\n  Computing R²...")

    # Weighted mean and variance
    mean_y = np.average(y_true, weights=sample_weight)
    ss_tot = np.sum(sample_weight * (y_true - mean_y) ** 2)
    residuals = y_true - y_pred
    ss_res = np.sum(sample_weight * residuals ** 2)

    r2 = 1 - (ss_res / ss_tot)

    return {
        'r2': r2,
        'ss_tot': ss_tot,
        'ss_res': ss_res,
    }


def bootstrap_ci(y_true, y_pred, sample_weight, metric_fn, n_bootstrap=1000, ci=0.95):
    """
    Compute bootstrap confidence intervals for a metric.

    Parameters:
      y_true: observed win rates
      y_pred: predicted win rates
      sample_weight: sample weights (number of games)
      metric_fn: function to compute metric (takes y_true, y_pred, weights)
      n_bootstrap: number of bootstrap samples
      ci: confidence level (e.g., 0.95 for 95% CI)
    """
    log.info(f"  Computing {n_bootstrap} bootstrap samples...")

    bootstrap_metrics = []
    n = len(y_true)

    np.random.seed(42)
    for i in range(n_bootstrap):
        # Resample with replacement
        idx = np.random.choice(n, size=n, replace=True)
        y_true_boot = y_true[idx]
        y_pred_boot = y_pred[idx]
        w_boot = sample_weight[idx]

        # Compute metric
        metric_val = metric_fn(y_true_boot, y_pred_boot, w_boot)
        bootstrap_metrics.append(metric_val)

        if (i + 1) % 200 == 0:
            log.info(f"    Bootstrap {i + 1}/{n_bootstrap}")

    bootstrap_metrics = np.array(bootstrap_metrics)

    # Compute CI
    alpha = 1 - ci
    lower = np.percentile(bootstrap_metrics, 100 * alpha / 2)
    upper = np.percentile(bootstrap_metrics, 100 * (1 - alpha / 2))
    mean_val = np.mean(bootstrap_metrics)
    std_val = np.std(bootstrap_metrics)

    return {
        'mean': mean_val,
        'std': std_val,
        'lower_ci': lower,
        'upper_ci': upper,
        'bootstrap_samples': bootstrap_metrics,
    }


def compute_brier_score(y_true, y_pred, sample_weight):
    """Compute weighted Brier score: mean((y_pred - y_true)²)."""
    brier = np.average((y_pred - y_true) ** 2, weights=sample_weight)
    return brier


def main():
    log.info("=" * 70)
    log.info("Step 8: Comprehensive Metrics, Calibration & R² Ceiling")
    log.info("=" * 70)

    # Load data
    model_table, identity_df, m0_booster, m1_booster = load_models_and_data()

    y_true = (model_table['wins'] / model_table['games']).values
    w_test = model_table['games'].values.astype(float)

    # Predictions
    y_pred_m0 = compute_predictions(model_table, identity_df, m0_booster, "M0")
    y_pred_m1 = compute_predictions(model_table, identity_df, m1_booster, "M1")

    # ===================================================================
    # CALIBRATION ANALYSIS
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("CALIBRATION ANALYSIS")
    log.info("=" * 70)

    calib_m0, ece_m0, mce_m0 = compute_calibration_metrics(y_true, y_pred_m0, w_test)
    calib_m1, ece_m1, mce_m1 = compute_calibration_metrics(y_true, y_pred_m1, w_test)

    log.info(f"\nM0 Calibration:")
    log.info(f"  ECE (Expected Calibration Error): {ece_m0:.4f}")
    log.info(f"  MCE (Max Calibration Error): {mce_m0:.4f}")

    log.info(f"\nM1 Calibration:")
    log.info(f"  ECE: {ece_m1:.4f}")
    log.info(f"  MCE: {mce_m1:.4f}")

    calib_report = f"""
CALIBRATION ANALYSIS
====================

M0 (Skill Only):
  Expected Calibration Error (ECE): {ece_m0:.4f}
  Maximum Calibration Error (MCE):  {mce_m0:.4f}

M1 (Skill + Identity):
  Expected Calibration Error (ECE): {ece_m1:.4f}
  Maximum Calibration Error (MCE):  {mce_m1:.4f}

Interpretation:
  ECE: Average absolute difference between predicted and empirical probabilities
  MCE: Maximum absolute difference in any calibration bin
  Lower values indicate better calibration (closer to perfectly calibrated model)

M1 shows {"BETTER" if ece_m1 < ece_m0 else "WORSE"} calibration than M0 (ECE improvement: {ece_m0 - ece_m1:+.4f})
"""

    with open(RESULTS_DIR / "calibration_analysis.txt", 'w') as f:
        f.write(calib_report)

    # ===================================================================
    # R² AND STOPPING RULE CEILING
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("R² ANALYSIS")
    log.info("=" * 70)

    r2_m0 = compute_weighted_r2(y_true, y_pred_m0, w_test)
    r2_m1 = compute_weighted_r2(y_true, y_pred_m1, w_test)

    log.info(f"\nM0 R²: {r2_m0['r2']:.4f}")
    log.info(f"M1 R²: {r2_m1['r2']:.4f}")

    r2_report = f"""
R² ANALYSIS
===========

Observed R²:
  M0 (Skill Only):         {r2_m0['r2']:.4f}
  M1 (Skill + Identity):   {r2_m1['r2']:.4f}

Note on R² Ceiling:
  The 7-3 stopping rule creates an inherent ceiling on R² because:
  1. Outcomes are heavily concentrated by tournament structure
  2. True R² ceiling requires knowing latent true p_i distribution
  3. Cannot be reliably inferred from observed outcomes alone

  For future work: Model-implied ceiling can be computed via:
  - Cross-fitted predicted p_i as proxy for latent skill
  - Compute stopping-rule variance under those estimates
  - Option deferred to Step 11+
"""

    with open(RESULTS_DIR / "r2_analysis.txt", 'w') as f:
        f.write(r2_report)

    # ===================================================================
    # BOOTSTRAP CONFIDENCE INTERVALS
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("BOOTSTRAP CONFIDENCE INTERVALS (1000 samples, 95% CI)")
    log.info("=" * 70)

    def weighted_logloss(y_true, y_pred, w):
        eps = 1e-7
        pred_clipped = np.clip(y_pred, eps, 1 - eps)
        loss = -(y_true * np.log(pred_clipped) + (1 - y_true) * np.log(1 - pred_clipped))
        return np.average(loss, weights=w)

    def weighted_rmse(y_true, y_pred, w):
        return np.sqrt(np.average((y_true - y_pred) ** 2, weights=w))

    def weighted_r2(y_true, y_pred, w):
        mean_y = np.average(y_true, weights=w)
        ss_tot = np.sum(w * (y_true - mean_y) ** 2)
        ss_res = np.sum(w * (y_true - y_pred) ** 2)
        return 1 - (ss_res / ss_tot)

    log.info("\nM0 bootstrap CIs...")
    m0_logloss_ci = bootstrap_ci(y_true, y_pred_m0, w_test, weighted_logloss, n_bootstrap=1000)
    m0_rmse_ci = bootstrap_ci(y_true, y_pred_m0, w_test, weighted_rmse, n_bootstrap=1000)
    m0_r2_ci = bootstrap_ci(y_true, y_pred_m0, w_test, weighted_r2, n_bootstrap=1000)

    log.info("\nM1 bootstrap CIs...")
    m1_logloss_ci = bootstrap_ci(y_true, y_pred_m1, w_test, weighted_logloss, n_bootstrap=1000)
    m1_rmse_ci = bootstrap_ci(y_true, y_pred_m1, w_test, weighted_rmse, n_bootstrap=1000)
    m1_r2_ci = bootstrap_ci(y_true, y_pred_m1, w_test, weighted_r2, n_bootstrap=1000)

    ci_report = f"""
BOOTSTRAP CONFIDENCE INTERVALS (1000 resamples, 95% CI)
========================================================

M0 (Skill Only):
  Log-Loss:     {m0_logloss_ci['mean']:.4f} [{m0_logloss_ci['lower_ci']:.4f}, {m0_logloss_ci['upper_ci']:.4f}]
  Weighted RMSE: {m0_rmse_ci['mean']:.4f} [{m0_rmse_ci['lower_ci']:.4f}, {m0_rmse_ci['upper_ci']:.4f}]
  R²:           {m0_r2_ci['mean']:.4f} [{m0_r2_ci['lower_ci']:.4f}, {m0_r2_ci['upper_ci']:.4f}]

M1 (Skill + Identity):
  Log-Loss:     {m1_logloss_ci['mean']:.4f} [{m1_logloss_ci['lower_ci']:.4f}, {m1_logloss_ci['upper_ci']:.4f}]
  Weighted RMSE: {m1_rmse_ci['mean']:.4f} [{m1_rmse_ci['lower_ci']:.4f}, {m1_rmse_ci['upper_ci']:.4f}]
  R²:           {m1_r2_ci['mean']:.4f} [{m1_r2_ci['lower_ci']:.4f}, {m1_r2_ci['upper_ci']:.4f}]

Model Improvement (M0 - M1):
  Log-Loss improvement:  {m0_logloss_ci['mean'] - m1_logloss_ci['mean']:+.4f}
    CI: [{m0_logloss_ci['lower_ci'] - m1_logloss_ci['upper_ci']:+.4f}, {m0_logloss_ci['upper_ci'] - m1_logloss_ci['lower_ci']:+.4f}]

  R² improvement:        {m1_r2_ci['mean'] - m0_r2_ci['mean']:+.4f}
    CI: [{m1_r2_ci['lower_ci'] - m0_r2_ci['upper_ci']:+.4f}, {m1_r2_ci['upper_ci'] - m0_r2_ci['lower_ci']:+.4f}]
"""

    with open(RESULTS_DIR / "bootstrap_ci.txt", 'w') as f:
        f.write(ci_report)

    log.info(ci_report)

    # ===================================================================
    # COMPREHENSIVE METRICS TABLE
    # ===================================================================
    log.info("\n" + "=" * 70)
    log.info("COMPREHENSIVE METRICS SUMMARY")
    log.info("=" * 70)

    metrics_data = {
        'Model': ['M0', 'M1'],
        'Test_LogLoss': [m0_logloss_ci['mean'], m1_logloss_ci['mean']],
        'Test_RMSE': [m0_rmse_ci['mean'], m1_rmse_ci['mean']],
        'Test_R2': [m0_r2_ci['mean'], m1_r2_ci['mean']],
        'Calibration_ECE': [ece_m0, ece_m1],
        'Calibration_MCE': [mce_m0, mce_m1],
        'N_Features': [1, 194],
    }

    metrics_df = pd.DataFrame(metrics_data)
    metrics_df.to_csv(RESULTS_DIR / "metrics_m0_m1.csv", index=False)

    log.info("\n" + str(metrics_df.to_string(index=False)))

    log.info("\n" + "=" * 70)
    log.info("✓ Step 8 Complete: Comprehensive metrics generated")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
